"""
community.py — Verification & Suggestion System for GKR Bot.

Features:
  Verification:
    • /verify setup   — Creates a verification button in a channel
    • /verify config  — Set the verified role and log channel
    Suggestions:
    • /suggest [text] — Submit a suggestion (voted by members)
    • /suggest approve/deny [id] — Staff approve/deny with reason
    • /suggest list    — List open suggestions
"""

from __future__ import annotations

import os
import sqlite3
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from gkr_ui import C, embed_error, embed_success, embed_info, embed_warning, embed_action  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "community.sqlite3")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class CommunityDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            # Verification config per guild
            conn.execute("""
                CREATE TABLE IF NOT EXISTS verify_config (
                    guild_id TEXT PRIMARY KEY,
                    verified_role_id TEXT,
                    log_channel_id TEXT,
                    min_account_days INTEGER DEFAULT 0
                )
            """)
            # Suggestions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS suggestions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_id TEXT,
                    author_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    staff_note TEXT,
                    upvotes INTEGER DEFAULT 0,
                    downvotes INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            # Votes (prevent duplicate voting)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS suggestion_votes (
                    suggestion_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    vote INTEGER NOT NULL,  -- 1 = up, -1 = down
                    PRIMARY KEY (suggestion_id, user_id),
                    FOREIGN KEY(suggestion_id) REFERENCES suggestions(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    # --- Verification Config ---

    def get_verify_config(self, guild_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM verify_config WHERE guild_id=?", (str(guild_id),)).fetchone()
            if row:
                return dict(row)
            return {"guild_id": str(guild_id), "verified_role_id": None, "log_channel_id": None, "min_account_days": 0}

    def set_verify_config(self, guild_id: int, **kwargs) -> None:
        cfg = self.get_verify_config(guild_id)
        for k, v in kwargs.items():
            cfg[k] = v
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO verify_config (guild_id, verified_role_id, log_channel_id, min_account_days)
                VALUES (?, ?, ?, ?)
            """, (str(guild_id), cfg["verified_role_id"], cfg["log_channel_id"], cfg["min_account_days"]))
            conn.commit()

    # --- Suggestions ---

    def create_suggestion(self, guild_id: int, channel_id: int, author_id: int, content: str) -> int:
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO suggestions (guild_id, channel_id, author_id, content, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (str(guild_id), str(channel_id), str(author_id), content, datetime.datetime.utcnow().isoformat()))
            conn.commit()
            return cur.lastrowid

    def update_message_id(self, suggestion_id: int, message_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE suggestions SET message_id=? WHERE id=?", (str(message_id), suggestion_id))
            conn.commit()

    def get_suggestion(self, suggestion_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM suggestions WHERE id=?", (suggestion_id,)).fetchone()
            return dict(row) if row else None

    def get_by_message(self, message_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM suggestions WHERE message_id=?", (str(message_id),)).fetchone()
            return dict(row) if row else None

    def cast_vote(self, suggestion_id: int, user_id: int, vote: int) -> str:
        """Returns 'added', 'changed', or 'removed'."""
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT vote FROM suggestion_votes WHERE suggestion_id=? AND user_id=?",
                (suggestion_id, str(user_id))
            ).fetchone()

            if existing:
                old_vote = existing["vote"]
                if old_vote == vote:
                    # Remove vote (toggle off)
                    conn.execute(
                        "DELETE FROM suggestion_votes WHERE suggestion_id=? AND user_id=?",
                        (suggestion_id, str(user_id))
                    )
                    if vote == 1:
                        conn.execute("UPDATE suggestions SET upvotes=upvotes-1 WHERE id=?", (suggestion_id,))
                    else:
                        conn.execute("UPDATE suggestions SET downvotes=downvotes-1 WHERE id=?", (suggestion_id,))
                    conn.commit()
                    return "removed"
                else:
                    # Change vote
                    conn.execute(
                        "UPDATE suggestion_votes SET vote=? WHERE suggestion_id=? AND user_id=?",
                        (vote, suggestion_id, str(user_id))
                    )
                    if vote == 1:
                        conn.execute("UPDATE suggestions SET upvotes=upvotes+1, downvotes=downvotes-1 WHERE id=?", (suggestion_id,))
                    else:
                        conn.execute("UPDATE suggestions SET upvotes=upvotes-1, downvotes=downvotes+1 WHERE id=?", (suggestion_id,))
                    conn.commit()
                    return "changed"
            else:
                conn.execute(
                    "INSERT INTO suggestion_votes (suggestion_id, user_id, vote) VALUES (?, ?, ?)",
                    (suggestion_id, str(user_id), vote)
                )
                if vote == 1:
                    conn.execute("UPDATE suggestions SET upvotes=upvotes+1 WHERE id=?", (suggestion_id,))
                else:
                    conn.execute("UPDATE suggestions SET downvotes=downvotes+1 WHERE id=?", (suggestion_id,))
                conn.commit()
                return "added"

    def update_status(self, suggestion_id: int, status: str, staff_note: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE suggestions SET status=?, staff_note=? WHERE id=?",
                (status, staff_note, suggestion_id)
            )
            conn.commit()

    def get_pending(self, guild_id: int, limit: int = 10) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM suggestions
                WHERE guild_id=? AND status='pending'
                ORDER BY (upvotes - downvotes) DESC LIMIT ?
            """, (str(guild_id), limit)).fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class VerifyView(discord.ui.View):
    def __init__(self, cog: "CommunityCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="✅ Verify Me", style=discord.ButtonStyle.green, custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.cog.db.get_verify_config(interaction.guild.id)

        if not cfg["verified_role_id"]:
            await interaction.response.send_message(embed=embed_error("Verification role not configured. Please ask an admin."), ephemeral=True)
            return

        role = interaction.guild.get_role(int(cfg["verified_role_id"]))
        if not role:
            await interaction.response.send_message(embed=embed_error("Verification role not found. Please ask an admin."), ephemeral=True)
            return

        # Check if already verified
        if role in interaction.user.roles:
            await interaction.response.send_message(embed=embed_info("Already Verified", "You are already verified!"), ephemeral=True)
            return

        # Account age check
        min_days = cfg["min_account_days"] or 0
        if min_days > 0:
            account_age = (discord.utils.utcnow() - interaction.user.created_at).days
            if account_age < min_days:
                await interaction.response.send_message(
                    embed=embed_error(
                        f"Your account must be at least **{min_days} days old** to verify.\n"
                        f"Your account is **{account_age} days old**."
                    ),
                    ephemeral=True
                )
                return

        try:
            await interaction.user.add_roles(role, reason="Verified via button")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("I don't have permission to give you this role."), ephemeral=True)
            return

        await interaction.response.send_message(embed=embed_success("Verified", f"You have been verified and received the {role.mention} role!"), ephemeral=True)

        # Log
        if cfg["log_channel_id"]:
            log_ch = interaction.guild.get_channel(int(cfg["log_channel_id"]))
            if log_ch:
                embed = discord.Embed(
                    title="✅  Member Verified",
                    description=f"{interaction.user.mention} verified themselves.",
                    color=C.SUCCESS,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                embed.set_footer(text="GKR Community")
                await log_ch.send(embed=embed)


class SuggestionView(discord.ui.View):
    def __init__(self, cog: "CommunityCog", suggestion_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.suggestion_id = suggestion_id

    @discord.ui.button(label="👍", style=discord.ButtonStyle.secondary, custom_id="suggest_up")
    async def upvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = self.cog.db.cast_vote(self.suggestion_id, interaction.user.id, 1)
        sug = self.cog.db.get_suggestion(self.suggestion_id)
        await self.cog.refresh_suggestion_embed(interaction.message, sug)
        msgs = {"added": "Upvoted!", "removed": "Removed your upvote.", "changed": "Changed to upvote!"}
        await interaction.response.send_message(embed=embed_info("Vote Cast", msgs[result]), ephemeral=True)

    @discord.ui.button(label="👎", style=discord.ButtonStyle.secondary, custom_id="suggest_down")
    async def downvote(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = self.cog.db.cast_vote(self.suggestion_id, interaction.user.id, -1)
        sug = self.cog.db.get_suggestion(self.suggestion_id)
        await self.cog.refresh_suggestion_embed(interaction.message, sug)
        msgs = {"added": "Downvoted!", "removed": "Removed your downvote.", "changed": "Changed to downvote!"}
        await interaction.response.send_message(embed=embed_info("Vote Cast", msgs[result]), ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class CommunityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = CommunityDatabase()
        self.db.initialize()

    def build_suggestion_embed(self, sug: dict) -> discord.Embed:
        status_colors = {"pending": C.BRAND, "approved": C.SUCCESS, "denied": C.DANGER}
        status_icons = {"pending": "🔵", "approved": "✅", "denied": "❌"}
        color = status_colors.get(sug["status"], C.BRAND)

        embed = discord.Embed(
            title=f"{status_icons.get(sug['status'], '🔵')}  Suggestion #{sug['id']}",
            description=sug["content"],
            color=color,
            timestamp=datetime.datetime.fromisoformat(sug["created_at"])
        )
        embed.add_field(name="👍 Upvotes", value=str(sug["upvotes"]), inline=True)
        embed.add_field(name="👎 Downvotes", value=str(sug["downvotes"]), inline=True)
        embed.add_field(name="📊 Score", value=str(sug["upvotes"] - sug["downvotes"]), inline=True)
        embed.set_footer(text=f"Submitted by User ID: {sug['author_id']}")

        if sug.get("staff_note"):
            embed.add_field(name="📝 Staff Note", value=sug["staff_note"], inline=False)

        return embed

    async def refresh_suggestion_embed(self, message: discord.Message, sug: dict):
        try:
            embed = self.build_suggestion_embed(sug)
            await message.edit(embed=embed)
        except Exception:
            pass

    # ── Verify Commands ────────────────────────────────────────────────────

    verify = app_commands.Group(name="verify", description="Verification system commands")

    @verify.command(name="setup", description="Post a verification button in this channel")
    @app_commands.default_permissions(manage_guild=True)
    async def setup_verify(self, interaction: discord.Interaction) -> None:
        cfg = self.db.get_verify_config(interaction.guild.id)
        if not cfg["verified_role_id"]:
            await interaction.response.send_message(embed=embed_error("Please set the verified role first with `/verify config`."), ephemeral=True)
            return

        role = interaction.guild.get_role(int(cfg["verified_role_id"]))
        embed = discord.Embed(
            title="✅  Member Verification",
            description=(
                f"Welcome to **{interaction.guild.name}**!\n\n"
                f"Click the button below to verify yourself and gain access to the server.\n"
                f"You will receive the **{role.mention if role else 'Verified'}** role."
            ),
            color=C.BRAND
        )
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        view = VerifyView(self)
        await interaction.response.send_message(embed=embed_success("Verification Panel", "Posted!"), ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)

    @verify.command(name="config", description="Configure the verification system")
    @app_commands.describe(
        verified_role="Role given after verification",
        log_channel="Where to log verifications",
        min_account_age_days="Minimum Discord account age (days) required"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def config_verify(self, interaction: discord.Interaction,
                            verified_role: Optional[discord.Role] = None,
                            log_channel: Optional[discord.TextChannel] = None,
                            min_account_age_days: int = 0) -> None:
        kwargs = {}
        if verified_role:
            kwargs["verified_role_id"] = str(verified_role.id)
        if log_channel:
            kwargs["log_channel_id"] = str(log_channel.id)
        if min_account_age_days >= 0:
            kwargs["min_account_days"] = min_account_age_days

        self.db.set_verify_config(interaction.guild.id, **kwargs)

        embed = discord.Embed(title="✅  Verification Config Updated", color=C.SUCCESS)
        if verified_role: embed.add_field(name="Verified Role", value=verified_role.mention, inline=False)
        if log_channel: embed.add_field(name="Log Channel", value=log_channel.mention, inline=False)
        embed.add_field(name="Min Account Age", value=f"{min_account_age_days} days", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Suggestion Commands ────────────────────────────────────────────────

    suggest = app_commands.Group(name="suggest", description="Suggestion system")

    @suggest.command(name="submit", description="Submit a suggestion to the server")
    @app_commands.describe(suggestion="Your suggestion")
    async def submit(self, interaction: discord.Interaction, suggestion: str) -> None:
        if len(suggestion) > 1500:
            await interaction.response.send_message(embed=embed_error("Suggestion must be 1500 characters or fewer."), ephemeral=True)
            return

        sug_id = self.db.create_suggestion(interaction.guild.id, interaction.channel.id, interaction.user.id, suggestion)
        sug = self.db.get_suggestion(sug_id)
        embed = self.build_suggestion_embed(sug)
        view = SuggestionView(self, sug_id)

        await interaction.response.send_message(embed=embed_success("Suggestion Submitted", "Your suggestion has been posted!"), ephemeral=True)
        msg = await interaction.channel.send(embed=embed, view=view)
        self.db.update_message_id(sug_id, msg.id)

    @suggest.command(name="approve", description="[Staff] Approve a suggestion")
    @app_commands.describe(suggestion_id="The suggestion ID", reason="Reason for approval")
    @app_commands.default_permissions(manage_messages=True)
    async def approve(self, interaction: discord.Interaction, suggestion_id: int, reason: str = "Approved by staff.") -> None:
        sug = self.db.get_suggestion(suggestion_id)
        if not sug or sug["guild_id"] != str(interaction.guild.id):
            await interaction.response.send_message(embed=embed_error("Suggestion not found."), ephemeral=True)
            return

        self.db.update_status(suggestion_id, "approved", f"{reason} — {interaction.user.display_name}")

        if sug["message_id"] and sug["channel_id"]:
            ch = interaction.guild.get_channel(int(sug["channel_id"]))
            if ch:
                try:
                    msg = await ch.fetch_message(int(sug["message_id"]))
                    updated = self.db.get_suggestion(suggestion_id)
                    await self.refresh_suggestion_embed(msg, updated)
                except Exception:
                    pass

        await interaction.response.send_message(embed=embed_success("Suggestion Approved", f"Suggestion #{suggestion_id} has been marked as approved."), ephemeral=True)

    @suggest.command(name="deny", description="[Staff] Deny a suggestion")
    @app_commands.describe(suggestion_id="The suggestion ID", reason="Reason for denial")
    @app_commands.default_permissions(manage_messages=True)
    async def deny(self, interaction: discord.Interaction, suggestion_id: int, reason: str = "Not accepted at this time.") -> None:
        sug = self.db.get_suggestion(suggestion_id)
        if not sug or sug["guild_id"] != str(interaction.guild.id):
            await interaction.response.send_message(embed=embed_error("Suggestion not found."), ephemeral=True)
            return

        self.db.update_status(suggestion_id, "denied", f"{reason} — {interaction.user.display_name}")

        if sug["message_id"] and sug["channel_id"]:
            ch = interaction.guild.get_channel(int(sug["channel_id"]))
            if ch:
                try:
                    msg = await ch.fetch_message(int(sug["message_id"]))
                    updated = self.db.get_suggestion(suggestion_id)
                    await self.refresh_suggestion_embed(msg, updated)
                except Exception:
                    pass

        await interaction.response.send_message(embed=embed_success("Suggestion Denied", f"Suggestion #{suggestion_id} has been marked as denied."), ephemeral=True)

    @suggest.command(name="list", description="List top pending suggestions")
    async def list_suggestions(self, interaction: discord.Interaction) -> None:
        pending = self.db.get_pending(interaction.guild.id)
        if not pending:
            await interaction.response.send_message(embed=embed_info("Suggestions", "No pending suggestions right now."), ephemeral=True)
            return

        embed = discord.Embed(title="💡  Top Pending Suggestions", color=C.BRAND)
        for sug in pending[:10]:
            score = sug["upvotes"] - sug["downvotes"]
            preview = sug["content"][:80] + ("..." if len(sug["content"]) > 80 else "")
            embed.add_field(
                name=f"#{sug['id']}  |  Score: {score:+d} (👍{sug['upvotes']} 👎{sug['downvotes']})",
                value=preview,
                inline=False
            )
        embed.set_footer(text="GKR Suggestions")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommunityCog(bot))
