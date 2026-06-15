"""
server_logs.py
──────────────
Comprehensive A-Z Discord server event logging.
  • Configurable log channel per guild  (/logs channel)
  • Master on/off toggle               (/logs toggle)
  • Per-event enable/disable           (/logs events)
  • Logs commands used by any user/bot
  • Modern, color-coded embed design
"""

from __future__ import annotations

import json
import os
import sqlite3
import textwrap
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# ─── Database ─────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "font_sync.sqlite3")

# ─── Full event catalogue ─────────────────────────────────────────────────────

ALL_EVENTS: list[str] = [
    # Members
    "member_join", "member_leave", "member_ban", "member_unban",
    "member_kick", "member_timeout", "member_role_add", "member_role_remove",
    "member_nickname",
    # Messages
    "message_delete", "message_edit", "message_bulk_delete",
    # Channels
    "channel_create", "channel_delete", "channel_update",
    # Roles
    "role_create", "role_delete", "role_update",
    # Voice
    "voice_join", "voice_leave", "voice_move", "voice_mute",
    # Server
    "server_update", "invite_create", "invite_delete",
    # Threads
    "thread_create", "thread_delete",
    # Commands & Bots
    "command_used", "bot_message",
    # Emoji / Sticker
    "emoji_update",
]

# ─── Color palette ────────────────────────────────────────────────────────────
C = {
    "join":          0x2ECC71,
    "leave":         0xE74C3C,
    "ban":           0xC0392B,
    "unban":         0x27AE60,
    "kick":          0xE67E22,
    "timeout":       0xF39C12,
    "msg_del":       0xFF6B6B,
    "msg_edit":      0xF1C40F,
    "bulk_del":      0xFF4444,
    "ch_create":     0x2ECC71,
    "ch_delete":     0xE74C3C,
    "ch_update":     0xF1C40F,
    "role_create":   0x9B59B6,
    "role_delete":   0x8E44AD,
    "role_update":   0xBB8FCE,
    "role_add":      0x1ABC9C,
    "role_remove":   0xE74C3C,
    "nick":          0x3498DB,
    "voice_join":    0x1ABC9C,
    "voice_leave":   0x95A5A6,
    "voice_move":    0x3498DB,
    "voice_mute":    0xF39C12,
    "server":        0x5865F2,
    "invite_create": 0x2ECC71,
    "invite_delete": 0xE74C3C,
    "thread_create": 0x1ABC9C,
    "thread_delete": 0xE74C3C,
    "command":       0x5865F2,
    "bot_msg":       0x99AAB5,
    "emoji":         0xF39C12,
    "default":       0x7289DA,
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _trunc(text: str, limit: int = 1024) -> str:
    """Truncate text to Discord field limit."""
    if not text:
        return "*empty*"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _fmt_user(user: discord.abc.User) -> str:
    return f"{user.mention} (`{user}` · ID: `{user.id}`)"


def _fmt_channel(channel) -> str:
    if hasattr(channel, "mention"):
        return f"{channel.mention} (`#{channel.name}` · ID: `{channel.id}`)"
    return f"`{channel}`"


def _base_embed(title: str, color: int, icon: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    if icon:
        embed.set_author(name=title, icon_url=icon)
        embed.title = None  # type: ignore[assignment]
    embed.set_footer(text="GKR Logs • " + _now())
    return embed


# ─── Database layer ───────────────────────────────────────────────────────────

class LogsDB:
    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS server_logs (
                    guild_id        TEXT PRIMARY KEY,
                    log_channel_id  TEXT,
                    enabled         INTEGER NOT NULL DEFAULT 1,
                    enabled_events  TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            c.commit()

    def get(self, guild_id: int) -> dict:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM server_logs WHERE guild_id = ?", (str(guild_id),)
            ).fetchone()
        if not row:
            return {
                "guild_id": guild_id,
                "log_channel_id": None,
                "enabled": True,
                "enabled_events": list(ALL_EVENTS),   # all on by default
            }
        raw_events = json.loads(row["enabled_events"] or "[]")
        return {
            "guild_id": guild_id,
            "log_channel_id": int(row["log_channel_id"]) if row["log_channel_id"] else None,
            "enabled": bool(row["enabled"]),
            "enabled_events": raw_events if raw_events else list(ALL_EVENTS),
        }

    def save(self, cfg: dict) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO server_logs (guild_id, log_channel_id, enabled, enabled_events)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    log_channel_id  = excluded.log_channel_id,
                    enabled         = excluded.enabled,
                    enabled_events  = excluded.enabled_events
                """,
                (
                    str(cfg["guild_id"]),
                    str(cfg["log_channel_id"]) if cfg["log_channel_id"] else None,
                    1 if cfg["enabled"] else 0,
                    json.dumps(cfg["enabled_events"]),
                ),
            )
            c.commit()


# ─── Core dispatcher ──────────────────────────────────────────────────────────

class ServerLogger:
    """Fetches config and dispatches formatted embeds to the log channel."""

    def __init__(self, bot: commands.Bot, db: LogsDB) -> None:
        self.bot = bot
        self.db = db

    async def _send(self, guild: discord.Guild, event: str, embed: discord.Embed) -> None:
        cfg = self.db.get(guild.id)
        if not cfg["enabled"]:
            return
        if event not in cfg["enabled_events"]:
            return
        if not cfg["log_channel_id"]:
            return
        channel = guild.get_channel(cfg["log_channel_id"])
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ── Member events ─────────────────────────────────────────────────────────

    async def on_member_join(self, member: discord.Member) -> None:
        embed = _base_embed("📥  Member Joined", C["join"])
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=_fmt_user(member), inline=False)
        embed.add_field(name="Account Created",
                        value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.add_field(name="Member #", value=f"`{member.guild.member_count}`", inline=True)
        await self._send(member.guild, "member_join", embed)

    async def on_member_remove(self, member: discord.Member) -> None:
        embed = _base_embed("📤  Member Left", C["leave"])
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=_fmt_user(member), inline=False)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(name="Roles Held", value=" ".join(roles) or "None", inline=False)
        await self._send(member.guild, "member_leave", embed)

    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = _base_embed("🔨  Member Banned", C["ban"])
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=_fmt_user(user), inline=False)
        # Try to fetch audit log for reason + moderator
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    embed.add_field(name="Moderator", value=_fmt_user(entry.user), inline=True)
                    embed.add_field(name="Reason", value=_trunc(entry.reason or "No reason"), inline=True)
                    break
        except discord.Forbidden:
            pass
        await self._send(guild, "member_ban", embed)

    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = _base_embed("✅  Member Unbanned", C["unban"])
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=_fmt_user(user), inline=False)
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    embed.add_field(name="Moderator", value=_fmt_user(entry.user), inline=True)
                    break
        except discord.Forbidden:
            pass
        await self._send(guild, "member_unban", embed)

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = after.guild

        # Nickname change
        if before.nick != after.nick:
            embed = _base_embed("✏️  Nickname Changed", C["nick"])
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="User", value=_fmt_user(after), inline=False)
            embed.add_field(name="Before", value=f"`{before.nick or before.name}`", inline=True)
            embed.add_field(name="After",  value=f"`{after.nick or after.name}`",  inline=True)
            await self._send(guild, "member_nickname", embed)

        # Role changes
        added   = [r for r in after.roles  if r not in before.roles and r.name != "@everyone"]
        removed = [r for r in before.roles if r not in after.roles  and r.name != "@everyone"]

        if added:
            embed = _base_embed("🎭  Role Added", C["role_add"])
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="User",  value=_fmt_user(after), inline=False)
            embed.add_field(name="Roles Added", value=" ".join(r.mention for r in added), inline=False)
            # Try audit log for who did it
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update):
                    if entry.target.id == after.id:
                        embed.add_field(name="By", value=_fmt_user(entry.user), inline=True)
                        break
            except discord.Forbidden:
                pass
            await self._send(guild, "member_role_add", embed)

        if removed:
            embed = _base_embed("🎭  Role Removed", C["role_remove"])
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="User",  value=_fmt_user(after), inline=False)
            embed.add_field(name="Roles Removed", value=" ".join(r.mention for r in removed), inline=False)
            await self._send(guild, "member_role_remove", embed)

        # Timeout
        if before.timed_out_until != after.timed_out_until and after.timed_out_until:
            embed = _base_embed("⏱️  Member Timed Out", C["timeout"])
            embed.set_thumbnail(url=after.display_avatar.url)
            embed.add_field(name="User",  value=_fmt_user(after), inline=False)
            embed.add_field(name="Until", value=discord.utils.format_dt(after.timed_out_until, "F"), inline=True)
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                    if entry.target.id == after.id:
                        embed.add_field(name="Moderator", value=_fmt_user(entry.user), inline=True)
                        embed.add_field(name="Reason",    value=_trunc(entry.reason or "No reason"), inline=True)
                        break
            except discord.Forbidden:
                pass
            await self._send(guild, "member_timeout", embed)

    # ── Message events ────────────────────────────────────────────────────────

    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        embed = _base_embed("🗑️  Message Deleted", C["msg_del"])
        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.add_field(name="Author",  value=_fmt_user(message.author), inline=True)
        embed.add_field(name="Channel", value=_fmt_channel(message.channel), inline=True)
        embed.add_field(name="Content", value=_trunc(message.content or "*[no text content]*"), inline=False)
        if message.attachments:
            embed.add_field(name="Attachments",
                            value="\n".join(a.filename for a in message.attachments), inline=False)
        await self._send(message.guild, "message_delete", embed)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or after.author.bot:
            return
        if before.content == after.content:
            return
        embed = _base_embed("📝  Message Edited", C["msg_edit"])
        embed.set_thumbnail(url=after.author.display_avatar.url)
        embed.add_field(name="Author",  value=_fmt_user(after.author), inline=True)
        embed.add_field(name="Channel", value=_fmt_channel(after.channel), inline=True)
        embed.add_field(name="Jump",    value=f"[View Message]({after.jump_url})", inline=True)
        embed.add_field(name="Before",  value=_trunc(before.content), inline=False)
        embed.add_field(name="After",   value=_trunc(after.content),  inline=False)
        await self._send(after.guild, "message_edit", embed)

    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return
        channel = messages[0].channel
        embed = _base_embed(f"🗑️  Bulk Delete — {len(messages)} Messages", C["bulk_del"])
        embed.add_field(name="Channel", value=_fmt_channel(channel), inline=True)
        embed.add_field(name="Count",   value=f"`{len(messages)}`",  inline=True)
        # Build short log
        lines = []
        for m in messages[-10:]:  # show last 10
            lines.append(f"`{m.author}`: {_trunc(m.content, 80)}")
        embed.add_field(name="Last Messages (up to 10)", value="\n".join(lines) or "*none*", inline=False)
        await self._send(guild, "message_bulk_delete", embed)

    # ── Channel events ────────────────────────────────────────────────────────

    async def on_guild_channel_create(self, channel) -> None:
        embed = _base_embed(f"➕  Channel Created", C["ch_create"])
        embed.add_field(name="Name",     value=_fmt_channel(channel), inline=True)
        embed.add_field(name="Type",     value=f"`{channel.type}`",   inline=True)
        embed.add_field(name="Category", value=f"`{channel.category}`" if channel.category else "None", inline=True)
        try:
            async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
                embed.add_field(name="Created By", value=_fmt_user(entry.user), inline=True)
                break
        except discord.Forbidden:
            pass
        await self._send(channel.guild, "channel_create", embed)

    async def on_guild_channel_delete(self, channel) -> None:
        embed = _base_embed(f"➖  Channel Deleted", C["ch_delete"])
        embed.add_field(name="Name",     value=f"`#{channel.name}`", inline=True)
        embed.add_field(name="Type",     value=f"`{channel.type}`",  inline=True)
        embed.add_field(name="Category", value=f"`{channel.category}`" if channel.category else "None", inline=True)
        try:
            async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
                embed.add_field(name="Deleted By", value=_fmt_user(entry.user), inline=True)
                break
        except discord.Forbidden:
            pass
        await self._send(channel.guild, "channel_delete", embed)

    async def on_guild_channel_update(self, before, after) -> None:
        changes: list[tuple[str, str, str]] = []
        if before.name != after.name:
            changes.append(("Name", f"`{before.name}`", f"`{after.name}`"))
        if hasattr(before, "topic") and before.topic != after.topic:
            changes.append(("Topic", _trunc(before.topic or "None", 200), _trunc(after.topic or "None", 200)))
        if hasattr(before, "slowmode_delay") and before.slowmode_delay != after.slowmode_delay:
            changes.append(("Slowmode", f"`{before.slowmode_delay}s`", f"`{after.slowmode_delay}s`"))
        if hasattr(before, "nsfw") and before.nsfw != after.nsfw:
            changes.append(("NSFW", f"`{before.nsfw}`", f"`{after.nsfw}`"))
        if not changes:
            return
        embed = _base_embed(f"🔧  Channel Updated", C["ch_update"])
        embed.add_field(name="Channel", value=_fmt_channel(after), inline=False)
        for label, bval, aval in changes:
            embed.add_field(name=f"{label} (before)", value=bval, inline=True)
            embed.add_field(name=f"{label} (after)",  value=aval, inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
        await self._send(after.guild, "channel_update", embed)

    # ── Role events ───────────────────────────────────────────────────────────

    async def on_guild_role_create(self, role: discord.Role) -> None:
        embed = _base_embed("🎭  Role Created", C["role_create"])
        embed.add_field(name="Role",  value=role.mention, inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Hoisted", value=str(role.hoist), inline=True)
        try:
            async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
                embed.add_field(name="Created By", value=_fmt_user(entry.user), inline=True)
                break
        except discord.Forbidden:
            pass
        await self._send(role.guild, "role_create", embed)

    async def on_guild_role_delete(self, role: discord.Role) -> None:
        embed = _base_embed("🗑️  Role Deleted", C["role_delete"])
        embed.add_field(name="Name",  value=f"`@{role.name}`", inline=True)
        embed.add_field(name="Color", value=str(role.color),   inline=True)
        embed.add_field(name="Members Had", value=f"`{len(role.members)}`", inline=True)
        try:
            async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
                embed.add_field(name="Deleted By", value=_fmt_user(entry.user), inline=True)
                break
        except discord.Forbidden:
            pass
        await self._send(role.guild, "role_delete", embed)

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        changes: list[tuple[str, str, str]] = []
        if before.name != after.name:
            changes.append(("Name", f"`{before.name}`", f"`{after.name}`"))
        if before.color != after.color:
            changes.append(("Color", str(before.color), str(after.color)))
        if before.hoist != after.hoist:
            changes.append(("Hoisted", str(before.hoist), str(after.hoist)))
        if before.mentionable != after.mentionable:
            changes.append(("Mentionable", str(before.mentionable), str(after.mentionable)))
        if not changes:
            return
        embed = _base_embed("✏️  Role Updated", C["role_update"])
        embed.add_field(name="Role", value=after.mention, inline=False)
        for label, bval, aval in changes:
            embed.add_field(name=f"{label} (before)", value=bval, inline=True)
            embed.add_field(name=f"{label} (after)",  value=aval, inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
        await self._send(after.guild, "role_update", embed)

    # ── Voice events ──────────────────────────────────────────────────────────

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild = member.guild

        if before.channel is None and after.channel is not None:
            embed = _base_embed("🔊  Joined Voice", C["voice_join"])
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="User",    value=_fmt_user(member),         inline=True)
            embed.add_field(name="Channel", value=_fmt_channel(after.channel), inline=True)
            await self._send(guild, "voice_join", embed)

        elif before.channel is not None and after.channel is None:
            embed = _base_embed("🔇  Left Voice", C["voice_leave"])
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="User",    value=_fmt_user(member),          inline=True)
            embed.add_field(name="Channel", value=_fmt_channel(before.channel), inline=True)
            await self._send(guild, "voice_leave", embed)

        elif before.channel != after.channel and before.channel and after.channel:
            embed = _base_embed("🔀  Moved Voice Channel", C["voice_move"])
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="User",   value=_fmt_user(member),           inline=False)
            embed.add_field(name="From",   value=_fmt_channel(before.channel), inline=True)
            embed.add_field(name="→ To",   value=_fmt_channel(after.channel),  inline=True)
            await self._send(guild, "voice_move", embed)

        elif before.self_mute != after.self_mute or before.mute != after.mute:
            muted = after.self_mute or after.mute
            label = "🔕  Muted" if muted else "🔔  Unmuted"
            embed = _base_embed(f"{label} (Voice)", C["voice_mute"])
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="User",    value=_fmt_user(member), inline=True)
            embed.add_field(name="Channel", value=_fmt_channel(after.channel) if after.channel else "N/A", inline=True)
            await self._send(guild, "voice_mute", embed)

    # ── Server update ─────────────────────────────────────────────────────────

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        changes: list[tuple[str, str, str]] = []
        if before.name != after.name:
            changes.append(("Name", f"`{before.name}`", f"`{after.name}`"))
        if before.icon != after.icon:
            changes.append(("Icon", "Changed", "New icon set"))
        if before.verification_level != after.verification_level:
            changes.append(("Verification", str(before.verification_level), str(after.verification_level)))
        if not changes:
            return
        embed = _base_embed("⚙️  Server Updated", C["server"])
        if after.icon:
            embed.set_thumbnail(url=after.icon.url)
        for label, bval, aval in changes:
            embed.add_field(name=f"{label} (before)", value=bval, inline=True)
            embed.add_field(name=f"{label} (after)",  value=aval, inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
        await self._send(after, "server_update", embed)

    # ── Invite events ─────────────────────────────────────────────────────────

    async def on_invite_create(self, invite: discord.Invite) -> None:
        if not invite.guild:
            return
        embed = _base_embed("🔗  Invite Created", C["invite_create"])
        embed.add_field(name="Code",    value=f"`{invite.code}`",  inline=True)
        embed.add_field(name="Channel", value=_fmt_channel(invite.channel) if invite.channel else "N/A", inline=True)
        embed.add_field(name="Max Uses", value=f"`{invite.max_uses or '∞'}`", inline=True)
        embed.add_field(name="Created By", value=_fmt_user(invite.inviter) if invite.inviter else "Unknown", inline=True)
        await self._send(invite.guild, "invite_create", embed)  # type: ignore[arg-type]

    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if not invite.guild:
            return
        embed = _base_embed("🗑️  Invite Deleted", C["invite_delete"])
        embed.add_field(name="Code",    value=f"`{invite.code}`", inline=True)
        embed.add_field(name="Channel", value=_fmt_channel(invite.channel) if invite.channel else "N/A", inline=True)
        await self._send(invite.guild, "invite_delete", embed)  # type: ignore[arg-type]

    # ── Thread events ─────────────────────────────────────────────────────────

    async def on_thread_create(self, thread: discord.Thread) -> None:
        embed = _base_embed("🧵  Thread Created", C["thread_create"])
        embed.add_field(name="Thread",   value=thread.mention,    inline=True)
        embed.add_field(name="Parent",   value=_fmt_channel(thread.parent) if thread.parent else "N/A", inline=True)
        embed.add_field(name="Owner",    value=_fmt_user(thread.owner) if thread.owner else "Unknown", inline=True)
        await self._send(thread.guild, "thread_create", embed)

    async def on_thread_delete(self, thread: discord.Thread) -> None:
        embed = _base_embed("🗑️  Thread Deleted", C["thread_delete"])
        embed.add_field(name="Name",   value=f"`{thread.name}`",  inline=True)
        embed.add_field(name="Parent", value=_fmt_channel(thread.parent) if thread.parent else "N/A", inline=True)
        await self._send(thread.guild, "thread_delete", embed)

    # ── Command usage ─────────────────────────────────────────────────────────

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild:
            return

        # Log bot messages (from OTHER bots, not us)
        if message.author.bot and message.author.id != self.bot.user.id:  # type: ignore[union-attr]
            embed = _base_embed("🤖  Bot Message", C["bot_msg"])
            embed.set_thumbnail(url=message.author.display_avatar.url)
            embed.add_field(name="Bot",     value=_fmt_user(message.author), inline=True)
            embed.add_field(name="Channel", value=_fmt_channel(message.channel), inline=True)
            content_preview = _trunc(message.content or "*[embed / file only]*", 512)
            embed.add_field(name="Content", value=content_preview, inline=False)
            if message.jump_url:
                embed.add_field(name="Jump", value=f"[View]({message.jump_url})", inline=True)
            await self._send(message.guild, "bot_message", embed)
            return

        # Detect prefix-style commands from human users
        PREFIXES = ("!", "/", "?", ".", "$", "-", "~", "=", ">>", ";;")
        if message.author.bot:
            return
        content = message.content.strip()
        if content and any(content.startswith(p) for p in PREFIXES):
            cmd_text = content.split()[0]
            embed = _base_embed("⌨️  Command Used", C["command"])
            embed.set_thumbnail(url=message.author.display_avatar.url)
            embed.add_field(name="User",    value=_fmt_user(message.author),    inline=True)
            embed.add_field(name="Channel", value=_fmt_channel(message.channel), inline=True)
            embed.add_field(name="Command", value=f"`{cmd_text}`",               inline=True)
            embed.add_field(name="Full Message", value=_trunc(content, 512),     inline=False)
            if message.jump_url:
                embed.add_field(name="Jump", value=f"[View]({message.jump_url})", inline=True)
            await self._send(message.guild, "command_used", embed)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Log slash command / application command usage."""
        if interaction.type != discord.InteractionType.application_command:
            return
        if not interaction.guild:
            return
        data = interaction.data or {}
        cmd_name = data.get("name", "unknown")
        embed = _base_embed("🔷  Slash Command Used", C["command"])
        if interaction.user:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(name="User",    value=_fmt_user(interaction.user),      inline=True)
        embed.add_field(name="Channel",  value=_fmt_channel(interaction.channel) if interaction.channel else "N/A", inline=True)
        embed.add_field(name="Command",  value=f"`/{cmd_name}`",                    inline=True)
        # Options / sub-commands
        options = data.get("options", [])
        if options:
            opts_str = " ".join(
                f"`{o['name']}`=`{o.get('value', '[sub]')}`" for o in options[:5]
            )
            embed.add_field(name="Options", value=opts_str, inline=False)
        await self._send(interaction.guild, "command_used", embed)

    # ── Emoji update ──────────────────────────────────────────────────────────

    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: list[discord.Emoji],
        after: list[discord.Emoji],
    ) -> None:
        added   = [e for e in after  if e not in before]
        removed = [e for e in before if e not in after]
        if not added and not removed:
            return
        embed = _base_embed("😀  Emoji Updated", C["emoji"])
        if added:
            embed.add_field(name="Added",   value=" ".join(str(e) for e in added[:10]),   inline=False)
        if removed:
            embed.add_field(name="Removed", value=" ".join(f"`:{e.name}:`" for e in removed[:10]), inline=False)
        await self._send(guild, "emoji_update", embed)


# ─── Slash commands ───────────────────────────────────────────────────────────

EVENT_DESCRIPTIONS: dict[str, str] = {
    "member_join":         "Member joins the server",
    "member_leave":        "Member leaves the server",
    "member_ban":          "Member is banned",
    "member_unban":        "Member is unbanned",
    "member_kick":         "Member is kicked",
    "member_timeout":      "Member is timed out",
    "member_role_add":     "Role added to member",
    "member_role_remove":  "Role removed from member",
    "member_nickname":     "Member nickname changes",
    "message_delete":      "Message is deleted",
    "message_edit":        "Message is edited",
    "message_bulk_delete": "Bulk message deletion",
    "channel_create":      "Channel created",
    "channel_delete":      "Channel deleted",
    "channel_update":      "Channel settings changed",
    "role_create":         "Role created",
    "role_delete":         "Role deleted",
    "role_update":         "Role updated",
    "voice_join":          "User joins voice channel",
    "voice_leave":         "User leaves voice channel",
    "voice_move":          "User moves between voice channels",
    "voice_mute":          "User mutes/unmutes in voice",
    "server_update":       "Server settings changed",
    "invite_create":       "Invite link created",
    "invite_delete":       "Invite link deleted/expired",
    "thread_create":       "Thread created",
    "thread_delete":       "Thread deleted",
    "command_used":        "Any slash/prefix command used",
    "bot_message":         "Bot sends a message",
    "emoji_update":        "Emoji added or removed",
}

EVENT_CATEGORIES: dict[str, list[str]] = {
    "members":  ["member_join", "member_leave", "member_ban", "member_unban",
                 "member_kick", "member_timeout", "member_role_add", "member_role_remove", "member_nickname"],
    "messages": ["message_delete", "message_edit", "message_bulk_delete"],
    "channels": ["channel_create", "channel_delete", "channel_update"],
    "roles":    ["role_create", "role_delete", "role_update"],
    "voice":    ["voice_join", "voice_leave", "voice_move", "voice_mute"],
    "server":   ["server_update", "invite_create", "invite_delete", "emoji_update"],
    "threads":  ["thread_create", "thread_delete"],
    "commands": ["command_used", "bot_message"],
}


def setup_server_logs(bot: commands.Bot) -> None:
    db = LogsDB()
    db.initialize()
    logger = ServerLogger(bot, db)

    # Wire up all listeners
    bot.add_listener(logger.on_member_join,           "on_member_join")
    bot.add_listener(logger.on_member_remove,         "on_member_remove")
    bot.add_listener(logger.on_member_ban,            "on_member_ban")
    bot.add_listener(logger.on_member_unban,          "on_member_unban")
    bot.add_listener(logger.on_member_update,         "on_member_update")
    bot.add_listener(logger.on_message_delete,        "on_message_delete")
    bot.add_listener(logger.on_message_edit,          "on_message_edit")
    bot.add_listener(logger.on_bulk_message_delete,   "on_bulk_message_delete")
    bot.add_listener(logger.on_guild_channel_create,  "on_guild_channel_create")
    bot.add_listener(logger.on_guild_channel_delete,  "on_guild_channel_delete")
    bot.add_listener(logger.on_guild_channel_update,  "on_guild_channel_update")
    bot.add_listener(logger.on_guild_role_create,     "on_guild_role_create")
    bot.add_listener(logger.on_guild_role_delete,     "on_guild_role_delete")
    bot.add_listener(logger.on_guild_role_update,     "on_guild_role_update")
    bot.add_listener(logger.on_voice_state_update,    "on_voice_state_update")
    bot.add_listener(logger.on_guild_update,          "on_guild_update")
    bot.add_listener(logger.on_invite_create,         "on_invite_create")
    bot.add_listener(logger.on_invite_delete,         "on_invite_delete")
    bot.add_listener(logger.on_thread_create,         "on_thread_create")
    bot.add_listener(logger.on_thread_delete,         "on_thread_delete")
    bot.add_listener(logger.on_message,               "on_message")
    bot.add_listener(logger.on_interaction,           "on_interaction")
    bot.add_listener(logger.on_guild_emojis_update,   "on_guild_emojis_update")

    # ── /logs command group ───────────────────────────────────────────────────
    logs_group = app_commands.Group(
        name="logs",
        description="Configure server event logging for this guild",
    )

    @logs_group.command(name="channel", description="Set the channel where all server logs will be sent")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        cfg = db.get(interaction.guild.id)
        cfg["log_channel_id"] = channel.id
        cfg["enabled"] = True
        db.save(cfg)
        embed = discord.Embed(
            title="✅  Logs Channel Set",
            description=f"All server events will now be logged to {channel.mention}.",
            color=0x2ECC71,
        )
        embed.add_field(name="Active Events", value=f"`{len(cfg['enabled_events'])}` / `{len(ALL_EVENTS)}`", inline=True)
        embed.set_footer(text="Use /logs events to enable or disable specific event categories.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @logs_group.command(name="toggle", description="Enable or disable the entire logging system for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle(interaction: discord.Interaction) -> None:
        cfg = db.get(interaction.guild.id)
        cfg["enabled"] = not cfg["enabled"]
        db.save(cfg)
        status = "**ENABLED** ✅" if cfg["enabled"] else "**DISABLED** ❌"
        await interaction.response.send_message(
            f"🔔 Server logging is now {status}.", ephemeral=True
        )

    @logs_group.command(name="status", description="Show the current logging configuration for this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(interaction: discord.Interaction) -> None:
        cfg = db.get(interaction.guild.id)
        ch = interaction.guild.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None
        embed = discord.Embed(
            title="📋  Server Logging Status",
            color=0x2ECC71 if cfg["enabled"] else 0x808080,
        )
        embed.add_field(name="Status",  value="✅ Enabled" if cfg["enabled"] else "❌ Disabled", inline=True)
        embed.add_field(name="Channel", value=ch.mention if ch else "Not set", inline=True)
        embed.add_field(name="Active Events", value=f"`{len(cfg['enabled_events'])}` / `{len(ALL_EVENTS)}`", inline=True)

        # Show per-category breakdown
        lines = []
        for cat, events in EVENT_CATEGORIES.items():
            active = sum(1 for e in events if e in cfg["enabled_events"])
            icon = "🟢" if active == len(events) else ("🟡" if active > 0 else "🔴")
            lines.append(f"{icon} **{cat.title()}** — `{active}/{len(events)}`")
        embed.add_field(name="Category Breakdown", value="\n".join(lines), inline=False)
        embed.set_footer(text="Use /logs events <category> to toggle categories.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @logs_group.command(name="events", description="Enable or disable a logging category (or 'all')")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        category="Category to toggle: members | messages | channels | roles | voice | server | threads | commands | all",
        action="enable or disable",
    )
    @app_commands.choices(
        category=[app_commands.Choice(name=k, value=k) for k in list(EVENT_CATEGORIES.keys()) + ["all"]],
        action=[
            app_commands.Choice(name="enable",  value="enable"),
            app_commands.Choice(name="disable", value="disable"),
        ],
    )
    async def events(
        interaction: discord.Interaction,
        category: str,
        action: str,
    ) -> None:
        cfg = db.get(interaction.guild.id)
        enabled: set[str] = set(cfg["enabled_events"])

        if category == "all":
            target_events = ALL_EVENTS
        else:
            target_events = EVENT_CATEGORIES.get(category, [])

        if action == "enable":
            enabled.update(target_events)
            verb = "enabled"
        else:
            enabled.difference_update(target_events)
            verb = "disabled"

        cfg["enabled_events"] = list(enabled)
        db.save(cfg)

        ev_list = "\n".join(
            f"{'✅' if e in enabled else '❌'} `{e}` — {EVENT_DESCRIPTIONS.get(e, '')}"
            for e in target_events
        )
        embed = discord.Embed(
            title=f"🔧  Events {verb.title()} — {category.title()}",
            description=ev_list,
            color=0x2ECC71 if action == "enable" else 0xE74C3C,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @logs_group.command(name="list", description="List all available log events and their current status")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def list_events(interaction: discord.Interaction) -> None:
        cfg = db.get(interaction.guild.id)
        enabled: set[str] = set(cfg["enabled_events"])
        embed = discord.Embed(
            title="📑  All Log Events",
            description="Full list of all trackable events and their current status.",
            color=0x5865F2,
        )
        for cat, events in EVENT_CATEGORIES.items():
            lines = [
                f"{'✅' if e in enabled else '❌'} `{e}` — {EVENT_DESCRIPTIONS.get(e, '')}"
                for e in events
            ]
            embed.add_field(name=f"📂 {cat.title()}", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Register globally
    bot.tree.add_command(logs_group)
