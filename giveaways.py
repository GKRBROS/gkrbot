"""
giveaways.py — Giveaway System for GKR Bot.

Features:
  • /giveaway start  — Button-based entry, multiple winners, role/level requirements
  • /giveaway end    — End early and pick winners
  • /giveaway reroll — Reroll winners for a finished giveaway
  • /giveaway list   — List active giveaways
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import datetime
import random
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands, tasks
from gkr_ui import C, embed_error, embed_success, embed_info, embed_warning, embed_action  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "giveaways.sqlite3")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class GiveawayDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_id TEXT,
                    prize TEXT NOT NULL,
                    winners INTEGER DEFAULT 1,
                    host_id TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    ended INTEGER DEFAULT 0,
                    required_role_id TEXT,
                    required_level INTEGER DEFAULT 0,
                    winner_ids TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    giveaway_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    PRIMARY KEY (giveaway_id, user_id),
                    FOREIGN KEY(giveaway_id) REFERENCES giveaways(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def create(self, guild_id: int, channel_id: int, host_id: int, prize: str,
               winners: int, ends_at: datetime.datetime,
               required_role_id: Optional[int], required_level: int) -> int:
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO giveaways (guild_id, channel_id, host_id, prize, winners, ends_at, required_role_id, required_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(guild_id), str(channel_id), str(host_id), prize, winners,
                  ends_at.isoformat(),
                  str(required_role_id) if required_role_id else None,
                  required_level))
            conn.commit()
            return cur.lastrowid

    def update_message_id(self, giveaway_id: int, message_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE giveaways SET message_id=? WHERE id=?", (str(message_id), giveaway_id))
            conn.commit()

    def get(self, giveaway_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM giveaways WHERE id=?", (giveaway_id,)).fetchone()
            return dict(row) if row else None

    def get_by_message(self, message_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM giveaways WHERE message_id=?", (str(message_id),)).fetchone()
            return dict(row) if row else None

    def get_active(self, guild_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM giveaways WHERE guild_id=? AND ended=0 ORDER BY ends_at ASC",
                (str(guild_id),)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_active(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM giveaways WHERE ended=0").fetchall()
            return [dict(r) for r in rows]

    def end(self, giveaway_id: int, winner_ids: list[int]) -> None:
        with self._conn() as conn:
            winner_str = ",".join(str(w) for w in winner_ids)
            conn.execute("UPDATE giveaways SET ended=1, winner_ids=? WHERE id=?", (winner_str, giveaway_id))
            conn.commit()

    def add_entry(self, giveaway_id: int, user_id: int) -> bool:
        """Returns True if entry added, False if already entered."""
        try:
            with self._conn() as conn:
                conn.execute("INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?)",
                             (giveaway_id, str(user_id)))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_entry(self, giveaway_id: int, user_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM giveaway_entries WHERE giveaway_id=? AND user_id=?",
                               (giveaway_id, str(user_id)))
            conn.commit()
            return cur.rowcount > 0

    def get_entries(self, giveaway_id: int) -> list[int]:
        with self._conn() as conn:
            rows = conn.execute("SELECT user_id FROM giveaway_entries WHERE giveaway_id=?",
                                (giveaway_id,)).fetchall()
            return [int(r["user_id"]) for r in rows]

    def get_entry_count(self, giveaway_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as c FROM giveaway_entries WHERE giveaway_id=?",
                               (giveaway_id,)).fetchone()
            return row["c"] if row else 0


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class GiveawayView(discord.ui.View):
    def __init__(self, cog: "GiveawayCog", giveaway_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="🎉 Enter", style=discord.ButtonStyle.secondary, custom_id="giveaway_enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = self.cog.db.get(self.giveaway_id)
        if not gw or gw["ended"]:
            await interaction.response.send_message(embed=embed_error("This giveaway has already ended."), ephemeral=True)
            return

        # Check requirements
        member = interaction.user
        if gw["required_role_id"]:
            role = interaction.guild.get_role(int(gw["required_role_id"]))
            if role and role not in member.roles:
                await interaction.response.send_message(embed=embed_error(f"You need the {role.mention} role to enter."), ephemeral=True)
                return

        added = self.cog.db.add_entry(self.giveaway_id, interaction.user.id)
        count = self.cog.db.get_entry_count(self.giveaway_id)

        if added:
            await interaction.response.send_message(embed=embed_info("Entered", f"You have entered the giveaway! Total entries: **{count:,}**"), ephemeral=True)
        else:
            # Toggle out
            self.cog.db.remove_entry(self.giveaway_id, interaction.user.id)
            count = self.cog.db.get_entry_count(self.giveaway_id)
            await interaction.response.send_message(embed=embed_info("Left", f"You have left the giveaway. Total entries: **{count:,}**"), ephemeral=True)

        # Update the embed entry count
        await self.cog.refresh_giveaway_embed(interaction.message, gw, count)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class GiveawayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = GiveawayDatabase()
        self.db.initialize()
        self._check_giveaways.start()

    def cog_unload(self):
        self._check_giveaways.cancel()

    def build_embed(self, gw: dict, entry_count: int) -> discord.Embed:
        ends_at = datetime.datetime.fromisoformat(gw["ends_at"])
        embed = discord.Embed(
            title=f"🎉  GIVEAWAY — {gw['prize']}",
            description=(
                f"Click the button below to enter!\n\n"
                f"**Winners:** {gw['winners']}\n"
                f"**Entries:** {entry_count:,}\n"
                f"**Ends:** <t:{int(ends_at.timestamp())}:R> (<t:{int(ends_at.timestamp())}:f>)\n"
                f"**Hosted by:** <@{gw['host_id']}>"
            ),
            color=C.PURPLE
        )
        if gw["required_role_id"]:
            embed.add_field(name="Required Role", value=f"<@&{gw['required_role_id']}>", inline=True)
        embed.set_footer(text=f"Giveaway ID: {gw['id']}")
        return embed

    async def refresh_giveaway_embed(self, message: discord.Message, gw: dict, entry_count: int):
        try:
            embed = self.build_embed(gw, entry_count)
            await message.edit(embed=embed)
        except Exception:
            pass

    async def conclude_giveaway(self, gw: dict):
        guild = self.bot.get_guild(int(gw["guild_id"]))
        if not guild:
            return

        channel = guild.get_channel(int(gw["channel_id"]))
        if not channel:
            return

        entries = self.db.get_entries(gw["id"])
        num_winners = min(gw["winners"], len(entries))

        if entries and num_winners > 0:
            winners = random.sample(entries, num_winners)
        else:
            winners = []

        self.db.end(gw["id"], winners)

        # Update the original embed
        if gw["message_id"]:
            try:
                msg = await channel.fetch_message(int(gw["message_id"]))
                end_embed = discord.Embed(
                    title=f"🎉  GIVEAWAY ENDED — {gw['prize']}",
                    description=(
                        f"**Winners:** {', '.join(f'<@{w}>' for w in winners) if winners else 'No valid entries!'}\n"
                        f"**Total Entries:** {len(entries):,}\n"
                        f"**Hosted by:** <@{gw['host_id']}>"
                    ),
                    color=C.NEUTRAL
                )
                await msg.edit(embed=end_embed, view=None)
            except Exception:
                pass

        # Announce winners
        if winners:
            winner_mentions = " ".join(f"<@{w}>" for w in winners)
            await channel.send(
                f"🎉 Congratulations {winner_mentions}! You won **{gw['prize']}**!\n"
                f"(Giveaway ID: `{gw['id']}` — `/giveaway reroll {gw['id']}` to reroll)"
            )
        else:
            await channel.send(f"😔 The giveaway for **{gw['prize']}** ended with no valid entries.")

    @tasks.loop(seconds=30)
    async def _check_giveaways(self):
        active = self.db.get_all_active()
        now = datetime.datetime.utcnow()
        for gw in active:
            ends_at = datetime.datetime.fromisoformat(gw["ends_at"])
            if now >= ends_at:
                await self.conclude_giveaway(gw)

    @_check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Commands ────────────────────────────────────────────────────────────

    giveaway = app_commands.Group(name="giveaway", description="Giveaway commands")

    @giveaway.command(name="start", description="Start a new giveaway")
    @app_commands.describe(
        prize="What is being given away",
        duration="Duration (e.g. 1h, 30m, 1d)",
        winners="Number of winners",
        required_role="Role required to enter (optional)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def start(self, interaction: discord.Interaction, prize: str, duration: str,
                    winners: int = 1, required_role: Optional[discord.Role] = None) -> None:
        # Parse duration
        total_secs = 0
        import re
        for val, unit in re.findall(r"(\d+)([dhm])", duration.lower()):
            val = int(val)
            if unit == "d": total_secs += val * 86400
            elif unit == "h": total_secs += val * 3600
            elif unit == "m": total_secs += val * 60

        if total_secs < 60:
            await interaction.response.send_message(embed=embed_error("Minimum giveaway duration is 1 minute."), ephemeral=True)
            return

        if winners < 1 or winners > 20:
            await interaction.response.send_message(embed=embed_error("Winners must be between 1 and 20."), ephemeral=True)
            return

        ends_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=total_secs)

        giveaway_id = self.db.create(
            interaction.guild.id, interaction.channel.id, interaction.user.id,
            prize, winners, ends_at,
            required_role.id if required_role else None, 0
        )

        gw = self.db.get(giveaway_id)
        embed = self.build_embed(gw, 0)
        view = GiveawayView(self, giveaway_id)

        await interaction.response.send_message(embed=embed_success("Giveaway Started", "The giveaway has been posted!"), ephemeral=True)
        msg = await interaction.channel.send(embed=embed, view=view)
        self.db.update_message_id(giveaway_id, msg.id)

    @giveaway.command(name="end", description="End a giveaway early")
    @app_commands.describe(giveaway_id="The ID of the giveaway to end")
    @app_commands.default_permissions(manage_guild=True)
    async def end_early(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        gw = self.db.get(giveaway_id)
        if not gw or gw["guild_id"] != str(interaction.guild.id) or gw["ended"]:
            await interaction.response.send_message(embed=embed_error("Giveaway not found or already ended."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.conclude_giveaway(gw)
        await interaction.followup.send(embed=embed_success("Giveaway Ended", f"Giveaway `{giveaway_id}` ended manually!"), ephemeral=True)

    @giveaway.command(name="reroll", description="Reroll winners for a finished giveaway")
    @app_commands.describe(giveaway_id="The ID of the giveaway to reroll")
    @app_commands.default_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        gw = self.db.get(giveaway_id)
        if not gw or gw["guild_id"] != str(interaction.guild.id) or not gw["ended"]:
            await interaction.response.send_message(embed=embed_error("Giveaway not found or has not ended yet."), ephemeral=True)
            return

        entries = self.db.get_entries(giveaway_id)
        if not entries:
            await interaction.response.send_message(embed=embed_error("No entries to reroll."), ephemeral=True)
            return

        num_winners = min(gw["winners"], len(entries))
        new_winners = random.sample(entries, num_winners)
        winner_mentions = " ".join(f"<@{w}>" for w in new_winners)
        await interaction.response.send_message(f"🔄 **Reroll!** New winners: {winner_mentions} — Congratulations!")

    @giveaway.command(name="list", description="List all active giveaways in this server")
    async def list_active(self, interaction: discord.Interaction) -> None:
        active = self.db.get_active(interaction.guild.id)
        if not active:
            await interaction.response.send_message(embed=embed_info("Active Giveaways", "There are no active giveaways right now."), ephemeral=True)
            return

        embed = discord.Embed(title="🎉  Active Giveaways", color=C.PURPLE)
        for gw in active:
            ends_at = datetime.datetime.fromisoformat(gw["ends_at"])
            count = self.db.get_entry_count(gw["id"])
            embed.add_field(
                name=f"ID {gw['id']}: {gw['prize']}",
                value=f"Ends: <t:{int(ends_at.timestamp())}:R> | Entries: {count} | Winners: {gw['winners']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
