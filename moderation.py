"""
moderation.py — Advanced Moderation & Administration System.

Structured with the GKR Centralized Design System:
  • /mute, /unmute, /mutelist — Clean moderation infraction cards
  • /staffrole — Add/remove/list staff roles
  • /saye, /sayt — Official announcements
  • /config, /status — Administration overview & bot health
"""

from __future__ import annotations

import datetime
import os
import platform
import re
import sqlite3
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from gkr_ui import (
    C,
    BOT_NAME,
    create_moderation_embed,
    embed_success,
    embed_error,
    embed_info,
    embed_warning,
    fmt_duration,
    fmt_rel,
    fmt_ts,
)

DB_PATH = os.path.join(os.path.dirname(__file__), "moderation.sqlite3")


# ---------------------------------------------------------------------------
# Database (Staff Roles)
# ---------------------------------------------------------------------------

class ModerationDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS staff_roles (
                    guild_id TEXT NOT NULL,
                    role_id  TEXT NOT NULL,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)
            conn.commit()

    def add_staff_role(self, guild_id: int, role_id: int) -> bool:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO staff_roles (guild_id, role_id) VALUES (?, ?)",
                    (str(guild_id), str(role_id))
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_staff_role(self, guild_id: int, role_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM staff_roles WHERE guild_id=? AND role_id=?",
                (str(guild_id), str(role_id))
            )
            conn.commit()
        return cur.rowcount > 0

    def get_staff_roles(self, guild_id: int) -> List[int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role_id FROM staff_roles WHERE guild_id=?", (str(guild_id),)
            ).fetchall()
        return [int(r["role_id"]) for r in rows]


# ---------------------------------------------------------------------------
# Duration Parser
# ---------------------------------------------------------------------------

def parse_duration(raw: str) -> Optional[datetime.timedelta]:
    """Parse duration string like '10m', '2h', '7d', '30s'. Max 28 days."""
    pattern = re.fullmatch(r"(\d+)\s*(s|sec|m|min|h|hr|d|day|days)?", raw.strip().lower())
    if not pattern:
        return None
    amount = int(pattern.group(1))
    unit   = pattern.group(2) or "m"

    if unit.startswith("s"):
        delta = datetime.timedelta(seconds=amount)
    elif unit.startswith("m"):
        delta = datetime.timedelta(minutes=amount)
    elif unit.startswith("h"):
        delta = datetime.timedelta(hours=amount)
    elif unit.startswith("d"):
        delta = datetime.timedelta(days=amount)
    else:
        return None

    return min(delta, datetime.timedelta(days=28))


# ---------------------------------------------------------------------------
# Moderation Cog
# ---------------------------------------------------------------------------

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ModerationDatabase()
        self.db.initialize()
        self._start_time = discord.utils.utcnow()

    # ── /mute ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="mute", description="Timeout (mute) a member")
    @app_commands.describe(
        user="The member to timeout",
        duration="Duration e.g. 10m, 2h, 7d (default: 1h, max: 28d)",
        reason="Reason for the timeout",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: str = "1h",
        reason: str = "No reason provided",
    ) -> None:
        if user.bot:
            await interaction.response.send_message(embed=embed_error("Cannot timeout a bot account."), ephemeral=True)
            return
        if user == interaction.user:
            await interaction.response.send_message(embed=embed_error("You cannot timeout yourself."), ephemeral=True)
            return
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(embed=embed_error("You cannot timeout a member with an equal or higher role."), ephemeral=True)
            return

        delta = parse_duration(duration)
        if not delta:
            await interaction.response.send_message(embed=embed_error("Invalid duration. Use formats like `10m`, `2h`, `1d`."), ephemeral=True)
            return

        until = discord.utils.utcnow() + delta
        try:
            await user.timeout(until, reason=f"[{interaction.user}] {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("Missing permissions to timeout this member."), ephemeral=True)
            return

        dur_str = fmt_duration(delta.total_seconds())
        embed = create_moderation_embed(
            action_title="🔇  Member Timed Out",
            user=user,
            moderator=interaction.user,
            reason=reason,
            duration_str=dur_str,
            expires_at=until,
            color=C.DANGER,
        )
        await interaction.response.send_message(embed=embed)

    # ── /unmute ───────────────────────────────────────────────────────────────

    @app_commands.command(name="unmute", description="Remove timeout from a member")
    @app_commands.describe(user="The member to unmute", reason="Reason for removal")
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        if not user.is_timed_out():
            await interaction.response.send_message(embed=embed_info("Not Timed Out", f"{user.mention} is not currently timed out."), ephemeral=True)
            return
        try:
            await user.timeout(None, reason=f"[{interaction.user}] {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("Missing permissions to remove timeout."), ephemeral=True)
            return

        embed = create_moderation_embed(
            action_title="🔊  Timeout Removed",
            user=user,
            moderator=interaction.user,
            reason=reason,
            color=C.SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    # ── /mutelist ─────────────────────────────────────────────────────────────

    @app_commands.command(name="mutelist", description="List all currently timed-out members")
    @app_commands.default_permissions(moderate_members=True)
    async def mutelist(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        muted = [m for m in interaction.guild.members if m.is_timed_out() and not m.bot]
        if not muted:
            await interaction.followup.send(embed=embed_success("No Active Timeouts", "No members are currently timed out."), ephemeral=True)
            return

        lines = []
        for m in muted[:20]:
            expires = m.communication_disabled_until
            exp_str = fmt_rel(expires) if expires else "Unknown"
            lines.append(f"• **{m.display_name}** ({m.mention}) — expires {exp_str}")

        embed = discord.Embed(
            title=f"🔇  Active Timeouts ({len(muted):,})",
            description="\n".join(lines),
            color=C.WARNING
        )
        if len(muted) > 20:
            embed.set_footer(text=f"Showing latest 20 of {len(muted):,} timed-out members")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /staffrole ────────────────────────────────────────────────────────────

    @app_commands.command(name="staffrole", description="Manage administrative staff roles")
    @app_commands.describe(action="Action to perform", role="The target role")
    @app_commands.choices(action=[
        app_commands.Choice(name="Add",    value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="List",   value="list"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def staffrole(
        self,
        interaction: discord.Interaction,
        action: str,
        role: Optional[discord.Role] = None,
    ) -> None:
        if action == "list":
            role_ids = self.db.get_staff_roles(interaction.guild.id)
            if not role_ids:
                await interaction.response.send_message(embed=embed_info("Staff Roles", "No staff roles configured."), ephemeral=True)
                return
            mentions = [r.mention for rid in role_ids if (r := interaction.guild.get_role(rid))]
            embed = discord.Embed(
                title="🛡️  Configured Staff Roles",
                description="\n".join(f"• {m}" for m in mentions) or "No valid roles found.",
                color=C.BRAND
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not role:
            await interaction.response.send_message(embed=embed_error("Please specify a role to add or remove."), ephemeral=True)
            return

        if action == "add":
            added = self.db.add_staff_role(interaction.guild.id, role.id)
            if added:
                await interaction.response.send_message(embed=embed_success("Staff Role Added", f"{role.mention} has been designated as a staff role."), ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed_info("Already Configured", f"{role.mention} is already in the staff roles list."), ephemeral=True)
        else:
            removed = self.db.remove_staff_role(interaction.guild.id, role.id)
            if removed:
                await interaction.response.send_message(embed=embed_success("Staff Role Removed", f"{role.mention} was removed from staff roles."), ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed_info("Not Found", f"{role.mention} was not configured as a staff role."), ephemeral=True)

    # ── /saye & /sayt ─────────────────────────────────────────────────────────

    @app_commands.command(name="saye", description="Send a formatted embed announcement as the bot")
    @app_commands.describe(channel="Target channel", title="Embed title", message="Body content", color="Hex color code (e.g. #5865F2)")
    @app_commands.default_permissions(manage_messages=True)
    async def saye(self, interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str, color: str = "#5865F2") -> None:
        try:
            color_int = int(color.replace("#", ""), 16)
        except ValueError:
            color_int = C.BRAND

        embed = discord.Embed(title=title, description=message, color=color_int)
        if interaction.guild and interaction.guild.icon:
            embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url)
        await channel.send(embed=embed)
        await interaction.response.send_message(embed=embed_success("Embed Dispatched", f"Sent to {channel.mention}."), ephemeral=True)

    @app_commands.command(name="sayt", description="Send a plain text message as the bot")
    @app_commands.describe(channel="Target channel", message="Message content")
    @app_commands.default_permissions(manage_messages=True)
    async def sayt(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str) -> None:
        await channel.send(message)
        await interaction.response.send_message(embed=embed_success("Message Dispatched", f"Sent to {channel.mention}."), ephemeral=True)

    # ── /config & /status ─────────────────────────────────────────────────────

    @app_commands.command(name="config", description="View server configuration overview")
    @app_commands.default_permissions(manage_guild=True)
    async def config_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        staff_role_ids = self.db.get_staff_roles(guild.id)
        staff_str = " ".join(f"<@&{rid}>" for rid in staff_role_ids) if staff_role_ids else "*None*"

        lines = [
            f"**Server:** {guild.name} (`{guild.id}`)",
            f"**Members:** `{guild.member_count:,}` · **Channels:** `{len(guild.channels):,}`",
            f"**Staff Roles:** {staff_str}",
            f"**Active Modules:** `{len(self.bot.cogs)}` loaded",
        ]

        embed = discord.Embed(
            title="⚙️  Server Configuration Overview",
            description="\n".join(lines),
            color=C.BRAND
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Show bot health, uptime, and system performance")
    async def status(self, interaction: discord.Interaction) -> None:
        uptime = discord.utils.utcnow() - self._start_time
        uptime_str = fmt_duration(uptime.total_seconds())

        latency_ms = round(self.bot.latency * 1000, 1)
        latency_badge = "🟢 Good" if latency_ms < 100 else ("🟡 Normal" if latency_ms < 250 else "🔴 High")

        lines = [
            f"**Uptime:** `{uptime_str}`",
            f"**Gateway Ping:** `{latency_ms}ms` ({latency_badge})",
            f"**Active Guilds:** `{len(self.bot.guilds):,}` · **Cached Users:** `{sum(g.member_count for g in self.bot.guilds):,}`",
            f"**Platform:** Python `{platform.python_version()}` · discord.py `{discord.__version__}`",
            f"**Loaded Modules:** `{len(self.bot.cogs)}` modules active",
        ]

        embed = discord.Embed(
            title=f"🤖  {BOT_NAME} Bot System Status",
            description="\n".join(lines),
            color=C.SUCCESS if latency_ms < 200 else C.WARNING,
            timestamp=discord.utils.utcnow()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
