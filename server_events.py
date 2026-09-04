"""
server_events.py — Server Events & RSVP System for GKR Bot.

Features:
  • /event create   — Create a server event with time, description, RSVP
  • /event list     — List upcoming events
  • /event cancel   — Cancel an event
  • /event rsvp     — Toggle RSVP to an event
  • Auto reminder 15 minutes before an event starts
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import datetime
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from gkr_ui import C, embed_error, embed_success, embed_info, embed_warning, embed_action  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "server_events.sqlite3")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class EventDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_id TEXT,
                    host_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    cancelled INTEGER DEFAULT 0,
                    reminded INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rsvps (
                    event_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    PRIMARY KEY (event_id, user_id),
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def create(self, guild_id: int, channel_id: int, host_id: int,
               title: str, description: str, starts_at: datetime.datetime) -> int:
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO events (guild_id, channel_id, host_id, title, description, starts_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (str(guild_id), str(channel_id), str(host_id), title, description, starts_at.isoformat()))
            conn.commit()
            return cur.lastrowid

    def update_message_id(self, event_id: int, message_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE events SET message_id=? WHERE id=?", (str(message_id), event_id))
            conn.commit()

    def get(self, event_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            return dict(row) if row else None

    def get_upcoming(self, guild_id: int) -> list[dict]:
        now_iso = datetime.datetime.utcnow().isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM events
                WHERE guild_id=? AND cancelled=0 AND starts_at > ?
                ORDER BY starts_at ASC
            """, (str(guild_id), now_iso)).fetchall()
            return [dict(r) for r in rows]

    def get_pending_reminders(self) -> list[dict]:
        now = datetime.datetime.utcnow()
        remind_cutoff = (now + datetime.timedelta(minutes=16)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM events
                WHERE cancelled=0 AND reminded=0 AND starts_at <= ?
            """, (remind_cutoff,)).fetchall()
            return [dict(r) for r in rows]

    def mark_reminded(self, event_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE events SET reminded=1 WHERE id=?", (event_id,))
            conn.commit()

    def cancel(self, event_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE events SET cancelled=1 WHERE id=?", (event_id,))
            conn.commit()

    def toggle_rsvp(self, event_id: int, user_id: int) -> bool:
        """Returns True if added, False if removed."""
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM rsvps WHERE event_id=? AND user_id=?",
                (event_id, str(user_id))
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM rsvps WHERE event_id=? AND user_id=?", (event_id, str(user_id)))
                conn.commit()
                return False
            else:
                conn.execute("INSERT INTO rsvps (event_id, user_id) VALUES (?, ?)", (event_id, str(user_id)))
                conn.commit()
                return True

    def get_rsvp_count(self, event_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as c FROM rsvps WHERE event_id=?", (event_id,)).fetchone()
            return row["c"] if row else 0

    def get_rsvps(self, event_id: int) -> list[int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT user_id FROM rsvps WHERE event_id=?", (event_id,)).fetchall()
            return [int(r["user_id"]) for r in rows]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class EventView(discord.ui.View):
    def __init__(self, cog: "EventCog", event_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.event_id = event_id

    @discord.ui.button(label="✅ RSVP", style=discord.ButtonStyle.secondary, custom_id="event_rsvp")
    async def rsvp(self, interaction: discord.Interaction, button: discord.ui.Button):
        ev = self.cog.db.get(self.event_id)
        if not ev or ev["cancelled"]:
            await interaction.response.send_message(embed=embed_error("This event has been cancelled."), ephemeral=True)
            return

        added = self.cog.db.toggle_rsvp(self.event_id, interaction.user.id)
        count = self.cog.db.get_rsvp_count(self.event_id)

        if added:
            await interaction.response.send_message(embed=embed_info("RSVP Added", f"You are going! ({count} attending)"), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed_info("RSVP Removed", f"You removed your RSVP. ({count} attending)"), ephemeral=True)

        # Refresh embed
        try:
            ev_fresh = self.cog.db.get(self.event_id)
            embed = self.cog.build_embed(ev_fresh, count)
            await interaction.message.edit(embed=embed)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class EventCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = EventDatabase()
        self.db.initialize()
        self._reminder_loop.start()

    def cog_unload(self):
        self._reminder_loop.cancel()

    def build_embed(self, ev: dict, rsvp_count: int) -> discord.Embed:
        starts_at = datetime.datetime.fromisoformat(ev["starts_at"])
        embed = discord.Embed(
            title=f"📅  {ev['title']}",
            description=ev["description"],
            color=C.NEUTRAL if ev["cancelled"] else C.BRAND
        )
        embed.add_field(name="🕐 When", value=f"<t:{int(starts_at.timestamp())}:F> (<t:{int(starts_at.timestamp())}:R>)", inline=False)
        embed.add_field(name="👥 Attending", value=str(rsvp_count), inline=True)
        embed.add_field(name="🎙️ Hosted by", value=f"<@{ev['host_id']}>", inline=True)
        embed.set_footer(text=f"Event ID: {ev['id']} | Click ✅ RSVP to attend")
        return embed

    @tasks.loop(minutes=1)
    async def _reminder_loop(self):
        pending = self.db.get_pending_reminders()
        for ev in pending:
            guild = self.bot.get_guild(int(ev["guild_id"]))
            if not guild:
                continue
            channel = guild.get_channel(int(ev["channel_id"]))
            if not channel:
                continue

            # Ping RSVPs
            rsvps = self.db.get_rsvps(ev["id"])
            starts_at = datetime.datetime.fromisoformat(ev["starts_at"])
            mention_str = " ".join(f"<@{uid}>" for uid in rsvps) if rsvps else "everyone"

            try:
                await channel.send(
                    f"⏰ **Reminder!** The event **{ev['title']}** starts <t:{int(starts_at.timestamp())}:R>!\n"
                    f"Attending: {mention_str}"
                )
            except Exception:
                pass
            self.db.mark_reminded(ev["id"])

    @_reminder_loop.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    # ── Commands ────────────────────────────────────────────────────────────

    event = app_commands.Group(name="event", description="Server event commands")

    @event.command(name="create", description="Create a new server event")
    @app_commands.describe(
        title="Event title",
        description="What is this event about?",
        when="When does it start? (e.g. 2h, 1d, or ISO datetime)"
    )
    @app_commands.default_permissions(manage_events=True)
    async def create(self, interaction: discord.Interaction, title: str, description: str, when: str) -> None:
        total_secs = 0
        for val, unit in re.findall(r"(\d+)([dhm])", when.lower()):
            val = int(val)
            if unit == "d": total_secs += val * 86400
            elif unit == "h": total_secs += val * 3600
            elif unit == "m": total_secs += val * 60

        if total_secs < 300:
            await interaction.response.send_message(embed=embed_error("Event must be at least 5 minutes in the future."), ephemeral=True)
            return

        starts_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=total_secs)
        event_id = self.db.create(
            interaction.guild.id, interaction.channel.id, interaction.user.id,
            title, description, starts_at
        )

        ev = self.db.get(event_id)
        embed = self.build_embed(ev, 0)
        view = EventView(self, event_id)

        await interaction.response.send_message(embed=embed_success("Event Created", "The event has been posted!"), ephemeral=True)
        msg = await interaction.channel.send(embed=embed, view=view)
        self.db.update_message_id(event_id, msg.id)

    @event.command(name="list", description="List upcoming events")
    async def list_events(self, interaction: discord.Interaction) -> None:
        events = self.db.get_upcoming(interaction.guild.id)
        if not events:
            await interaction.response.send_message(embed=embed_info("Events", "No upcoming events!"), ephemeral=True)
            return

        embed = discord.Embed(title=f"📅  Upcoming Events — {interaction.guild.name}", color=C.BRAND)
        for ev in events[:10]:
            starts_at = datetime.datetime.fromisoformat(ev["starts_at"])
            rsvp_count = self.db.get_rsvp_count(ev["id"])
            embed.add_field(
                name=f"ID {ev['id']}: {ev['title']}",
                value=f"<t:{int(starts_at.timestamp())}:F> | {rsvp_count} attending",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @event.command(name="cancel", description="Cancel an event")
    @app_commands.describe(event_id="The ID of the event to cancel")
    @app_commands.default_permissions(manage_events=True)
    async def cancel(self, interaction: discord.Interaction, event_id: int) -> None:
        ev = self.db.get(event_id)
        if not ev or ev["guild_id"] != str(interaction.guild.id):
            await interaction.response.send_message(embed=embed_error("Event not found."), ephemeral=True)
            return
        self.db.cancel(event_id)
        await interaction.response.send_message(embed=embed_success("Event Cancelled", f"Event **{ev['title']}** has been cancelled."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventCog(bot))
