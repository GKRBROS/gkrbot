"""
server_logs.py — Comprehensive Discord Server Audit & Event Logging.

Structured with the GKR Centralized Design System:
  • /logs setup — Automatic server log category and channel provisioning
    (creates category-based private log channels formatted in small caps with emojis)
  • Comprehensive event catalogue (members, messages, channels, roles, voice,
    server, threads, commands, emojis, stickers, events, stages, webhooks, automod)
  • Uses unified `create_audit_embed()` answering:
      1. What happened?
      2. To whom / what?
      3. Who performed it?
      4. What changed?
  • Zero raw database table/internal ID dumps
  • Standardized 12-hour `<t:TIMESTAMP:t>` and relative timestamps
  • Per-category custom routing & interactive configuration
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from typing import Optional, List, Dict, Tuple, Any, Union

import discord
from discord import app_commands
from discord.ext import commands

from gkr_ui import (
    C,
    create_audit_embed,
    embed_success,
    embed_error,
    embed_info,
    embed_warning,
    fmt_rel,
    fmt_ts,
)

# ─── Database Path ────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "font_sync.sqlite3")

# ─── Small Caps Converter Helper ──────────────────────────────────────────────

SMALL_CAPS_MAP: Dict[str, str] = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ', 'h': 'ʜ',
    'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
    'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
    'y': 'ʏ', 'z': 'ᴢ', '-': '-', '_': '-', ' ': '-'
}

def to_small_caps(text: str) -> str:
    """Convert standard text to aesthetic small caps format."""
    return "".join(SMALL_CAPS_MAP.get(c.lower(), c.lower()) for c in text)


# ─── Category Channel Provisioning Specs ──────────────────────────────────────

CATEGORY_SPECS: List[Tuple[str, str, str, str]] = [
    ("members",  "👥・ᴍᴇᴍʙᴇʀ-ʟᴏɢꜱ",    "👥 Members",    "Member joins, leaves, bans, unbans, kicks, timeouts, and nickname changes"),
    ("messages", "💬・ᴍᴇꜱꜱᴀɢᴇ-ʟᴏɢꜱ",   "💬 Messages",   "Deleted messages, message edits, bulk purges, and mentions"),
    ("channels", "📁・ᴄʜᴀɴɴᴇʟ-ʟᴏɢꜱ",   "📁 Channels",   "Channel creations, deletions, updates, stages, and webhooks"),
    ("roles",    "🎭・ʀᴏʟᴇ-ʟᴏɢꜱ",      "🎭 Roles",      "Role creations, deletions, updates, and member role assignments"),
    ("voice",    "🔊・ᴠᴏɪᴄᴇ-ʟᴏɢꜱ",     "🔊 Voice",      "Voice joins, leaves, moves, mutes, screen shares, and camera"),
    ("server",   "⚙️・ꜱᴇʀᴠᴇʀ-ʟᴏɢꜱ",    "⚙️ Server",     "Server settings, invites, emojis, stickers, and scheduled events"),
    ("threads",  "🧵・ᴛʜʀᴇᴀᴅ-ʟᴏɢꜱ",    "🧵 Threads",    "Thread creations, deletions, and archive updates"),
    ("commands", "⌨️・ᴄᴏᴍᴍᴀɴᴅ-ʟᴏɢꜱ",   "⌨️ Commands",   "Slash commands used, bot messages, and AutoMod triggers"),
    ("security", "🛡️・ꜱᴇᴄᴜʀɪᴛʏ-ʟᴏɢꜱ", "🛡️ Security",   "Warnings, auto-punishments, anti-spam, anti-raid, honeypot, and image scan actions"),
    ("ai",       "🧠・ᴀɪ-ʟᴏɢꜱ",       "🧠 AI System",  "AI chat queries, deep research, generated images, animated GIF banners, and settings"),
    ("errors",   "🚨・ᴇʀʀᴏʀ-ᴀɴᴅ-ᴄʀᴀꜱʜᴇꜱ", "🚨 Errors & Crashes", "Unhandled exceptions, command failures, and bot crash logs"),
]


# ─── Full Event Catalogue ─────────────────────────────────────────────────────

ALL_EVENTS: List[str] = [
    # Members
    "member_join", "member_leave", "member_ban", "member_unban",
    "member_kick", "member_timeout", "member_role_add", "member_role_remove",
    "member_nickname",
    # Messages
    "message_delete", "message_edit", "message_bulk_delete", "message_send", "message_mention",
    # Channels
    "channel_create", "channel_delete", "channel_update", "stage_instance_create", "stage_instance_delete", "webhook_update",
    # Roles
    "role_create", "role_delete", "role_update",
    # Voice
    "voice_join", "voice_leave", "voice_move", "voice_mute",
    "voice_stream", "voice_camera",
    # Server
    "server_update", "invite_create", "invite_delete", "emoji_update", "sticker_update", "event_create", "event_delete", "event_update",
    # Threads
    "thread_create", "thread_delete", "thread_update",
    # Commands & Bots
    "command_used", "bot_message", "automod_execution",
    # Security (bot auto-actions)
    "security_warn", "security_auto_timeout", "security_auto_kick", "security_auto_ban",
    "security_anti_spam", "security_anti_raid", "security_image_flagged",
    "security_honeypot",
    # AI System
    "ai_query", "ai_research", "ai_image", "ai_banner", "ai_comedy", "ai_config",
]

EVENT_CATEGORIES: Dict[str, List[str]] = {
    "members":  ["member_join", "member_leave", "member_ban", "member_unban",
                 "member_kick", "member_timeout", "member_nickname"],
    "messages": ["message_delete", "message_edit", "message_bulk_delete", "message_send", "message_mention"],
    "channels": ["channel_create", "channel_delete", "channel_update", "stage_instance_create", "stage_instance_delete", "webhook_update"],
    "roles":    ["role_create", "role_delete", "role_update", "member_role_add", "member_role_remove"],
    "voice":    ["voice_join", "voice_leave", "voice_move", "voice_mute",
                 "voice_stream", "voice_camera"],
    "server":   ["server_update", "invite_create", "invite_delete", "emoji_update", "sticker_update", "event_create", "event_delete", "event_update"],
    "threads":  ["thread_create", "thread_delete", "thread_update"],
    "commands": ["command_used", "bot_message", "automod_execution"],
    "security": [
        "security_warn", "security_auto_timeout", "security_auto_kick", "security_auto_ban",
        "security_anti_spam", "security_anti_raid", "security_image_flagged",
        "security_honeypot",
    ],
    "ai": [
        "ai_query", "ai_research", "ai_image", "ai_banner", "ai_comedy", "ai_config",
    ],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _trunc(text: str, limit: int = 1000) -> str:
    """Truncate text cleanly."""
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ─── Database Layer ───────────────────────────────────────────────────────────

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
            try:
                c.execute("ALTER TABLE server_logs ADD COLUMN category_channels TEXT NOT NULL DEFAULT '{}'")
            except sqlite3.OperationalError:
                pass  # Column already exists
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
                "enabled_events": list(ALL_EVENTS),
                "category_channels": {},
            }
        raw_events = json.loads(row["enabled_events"] or "[]")
        cat_data = row["category_channels"] if "category_channels" in row.keys() else "{}"
        raw_cats = json.loads(cat_data or "{}")
        return {
            "guild_id": guild_id,
            "log_channel_id": int(row["log_channel_id"]) if row["log_channel_id"] else None,
            "enabled": bool(row["enabled"]),
            "enabled_events": raw_events if raw_events else list(ALL_EVENTS),
            "category_channels": raw_cats,
        }

    def save(self, cfg: dict) -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO server_logs (guild_id, log_channel_id, enabled, enabled_events, category_channels)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    log_channel_id    = excluded.log_channel_id,
                    enabled           = excluded.enabled,
                    enabled_events    = excluded.enabled_events,
                    category_channels = excluded.category_channels
                """,
                (
                    str(cfg["guild_id"]),
                    str(cfg["log_channel_id"]) if cfg["log_channel_id"] else None,
                    1 if cfg["enabled"] else 0,
                    json.dumps(cfg["enabled_events"]),
                    json.dumps(cfg.get("category_channels", {})),
                ),
            )
            c.commit()


# ─── Core Dispatcher ──────────────────────────────────────────────────────────

class ServerLogger:
    """Fetches config and dispatches formatted audit embeds to log channels."""

    def __init__(self, bot: commands.Bot, db: LogsDB) -> None:
        self.bot = bot
        self.db = db
        self._queue: dict[int, list[discord.Embed]] = {}
        self._flush_task: Optional[asyncio.Task] = None

    def start(self):
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.get_running_loop().create_task(self._flush_loop())

    def stop(self):
        if self._flush_task:
            self._flush_task.cancel()

    async def _flush_loop(self):
        await self.bot.wait_until_ready()
        while True:
            await asyncio.sleep(3)
            for channel_id in list(self._queue.keys()):
                embeds = self._queue.get(channel_id, [])
                if not embeds:
                    continue
                to_send = embeds[:10]
                self._queue[channel_id] = embeds[10:]
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(embeds=to_send)
                    except Exception:
                        pass

    async def _send(self, guild: discord.Guild, event: str, embed: discord.Embed) -> None:
        cfg = self.db.get(guild.id)
        if not cfg["enabled"] or event not in cfg["enabled_events"]:
            return

        target_channel_id = cfg["log_channel_id"]
        category_channels: dict = cfg.get("category_channels") or {}
        for category, events in EVENT_CATEGORIES.items():
            if event in events:
                override = category_channels.get(category)
                if override:
                    target_channel_id = int(override)
                break

        if not target_channel_id:
            return

        channel = guild.get_channel(int(target_channel_id))
        if not isinstance(channel, discord.TextChannel):
            return

        # Ignore temporary voice channel spam
        if embed.description and ("Temp Voice" in embed.description or "Join to Create" in embed.description):
            return
        if embed.title and "Temp Voice" in embed.title:
            return

        if channel.id not in self._queue:
            self._queue[channel.id] = []
        self._queue[channel.id].append(embed)

    async def dispatch_security(
        self,
        guild: discord.Guild,
        event: str,
        title: str,
        description: str,
        color: int = 0xFF0000,
        thumbnail_url: Optional[str] = None,
    ) -> None:
        """Public method — lets security.py and honeypot.py post to the Security log channel."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        embed.set_footer(text="GKR Security  •  Audit & Defense Log")
        await self._send(guild, event, embed)

    async def dispatch_ai(
        self,
        guild: discord.Guild,
        event: str,
        title: str,
        description: str,
        color: int = 0x5865F2,
        thumbnail_url: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> None:
        """Public method — lets ai_system.py post to the AI log channel."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        if image_url:
            embed.set_image(url=image_url)
        embed.set_footer(text="GKR AI System  •  Audit & Activity Log")
        await self._send(guild, event, embed)


    # ── Member Events ─────────────────────────────────────────────────────────

    async def on_member_join(self, member: discord.Member) -> None:
        embed = create_audit_embed(
            title="📥 Member joined",
            subject=member.mention,
            details=[
                f"Account created {fmt_rel(member.created_at)}",
                f"Member #{member.guild.member_count:,}"
            ],
            color=C.SUCCESS,
            thumbnail_url=member.display_avatar.url,
            footer_text="Member Join"
        )
        await self._send(member.guild, "member_join", embed)

    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild

        # Audit check for kick vs regular leave
        is_kick = False
        kicker = None
        kick_reason = "No reason provided"
        try:
            await asyncio.sleep(0.3)
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 5:
                    is_kick = True
                    kicker = entry.user
                    if entry.reason:
                        kick_reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        if is_kick:
            embed = create_audit_embed(
                title="👢 Member kicked",
                subject=member.mention,
                actor=kicker,
                details=[f"Reason: {kick_reason}"],
                color=C.DANGER,
                thumbnail_url=member.display_avatar.url,
                footer_text="Kick Log"
            )
            await self._send(guild, "member_kick", embed)
        else:
            roles = [r.mention for r in member.roles if r.name != "@everyone"]
            roles_str = f"Roles held: {' '.join(roles)}" if roles else "No roles held"
            embed = create_audit_embed(
                title="📤 Member left",
                subject=member.mention,
                details=[roles_str],
                color=C.DANGER,
                thumbnail_url=member.display_avatar.url,
                footer_text="Member Leave"
            )
            await self._send(guild, "member_leave", embed)

    async def on_member_ban(self, guild: discord.Guild, user: Union[discord.User, discord.Member]) -> None:
        mod = None
        reason = "No reason provided"
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    mod = entry.user
                    if entry.reason:
                        reason = entry.reason
                    break
        except discord.Forbidden:
            pass

        embed = create_audit_embed(
            title="🔨 Member banned",
            subject=user.mention,
            actor=mod,
            details=[f"Reason: {reason}"],
            color=C.DANGER,
            thumbnail_url=user.display_avatar.url if hasattr(user, "display_avatar") else None,
            footer_text="Ban Log"
        )
        await self._send(guild, "member_ban", embed)

    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        mod = None
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    mod = entry.user
                    break
        except discord.Forbidden:
            pass

        embed = create_audit_embed(
            title="✅ Member unbanned",
            subject=user.mention,
            actor=mod,
            color=C.SUCCESS,
            thumbnail_url=user.display_avatar.url,
            footer_text="Unban Log"
        )
        await self._send(guild, "member_unban", embed)

    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = after.guild

        # Nickname change
        if before.nick != after.nick:
            embed = create_audit_embed(
                title="✏️ Nickname changed",
                subject=after.mention,
                changes=[("Nickname", before.nick or before.name, after.nick or after.name)],
                color=C.BRAND,
                thumbnail_url=after.display_avatar.url,
                footer_text="Nickname Update"
            )
            await self._send(guild, "member_nickname", embed)

        # Role changes — skip roles that were deleted from the server entirely
        # (Discord fires on_member_update for every member who had a deleted role,
        # which would spam the log with confusing "Role removed" entries)
        guild_role_ids = {r.id for r in guild.roles}
        added   = [r for r in after.roles  if r not in before.roles and r.name != "@everyone"]
        removed = [r for r in before.roles if r not in after.roles  and r.name != "@everyone"
                   and r.id in guild_role_ids]  # ← only log if role still exists (wasn't deleted)

        if added or removed:
            mod = None
            try:
                await asyncio.sleep(0.5)
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
                    if entry.target.id == after.id:
                        mod = entry.user
                        break
            except discord.Forbidden:
                pass

            if added and removed:
                added_str = " ".join(r.mention for r in added)
                removed_str = " ".join(r.mention for r in removed)
                embed = create_audit_embed(
                    title="🎭 Roles updated",
                    subject=after.mention,
                    subject_header="👤  Member",
                    action_desc=f"Roles were updated for {after.mention}.",
                    actor=mod,
                    actor_label="Updated By",
                    details=[f"Roles Added: {added_str}", f"Roles Removed: {removed_str}"],
                    color=C.PURPLE,
                    thumbnail_url=after.display_avatar.url,
                    footer_text="Role Update"
                )
                await self._send(guild, "role_update", embed)
            elif added:
                added_str = " ".join(r.mention for r in added)
                embed = create_audit_embed(
                    title="🎭 Role added",
                    subject=after.mention,
                    subject_header="👤  Member",
                    action_desc=f"{added_str} was assigned to {after.mention}.",
                    actor=mod,
                    actor_label="Added By",
                    details=[f"Role Added: {added_str}"],
                    color=C.SUCCESS,
                    thumbnail_url=after.display_avatar.url,
                    footer_text="Role Added"
                )
                await self._send(guild, "member_role_add", embed)
            elif removed:
                removed_str = " ".join(r.mention for r in removed)
                embed = create_audit_embed(
                    title="🎭 Role removed",
                    subject=after.mention,
                    subject_header="👤  Member",
                    action_desc=f"{removed_str} was removed from {after.mention}.",
                    actor=mod,
                    actor_label="Removed By",
                    details=[f"Role Removed: {removed_str}"],
                    color=C.DANGER,
                    thumbnail_url=after.display_avatar.url,
                    footer_text="Role Removed"
                )
                await self._send(guild, "member_role_remove", embed)

        # Timeout
        if before.timed_out_until != after.timed_out_until and after.timed_out_until:
            mod = None
            reason = "No reason provided"
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                    if entry.target.id == after.id:
                        mod = entry.user
                        if entry.reason:
                            reason = entry.reason
                        break
            except discord.Forbidden:
                pass

            embed = create_audit_embed(
                title="⏱️ Member timed out",
                subject=after.mention,
                actor=mod,
                details=[f"Expires {fmt_rel(after.timed_out_until)}", f"Reason: {reason}"],
                color=C.WARNING,
                thumbnail_url=after.display_avatar.url,
                footer_text="Timeout Log"
            )
            await self._send(guild, "member_timeout", embed)


    # ── Guild Role Events ──────────────────────────────────────────────────────

    async def on_guild_role_create(self, role: discord.Role) -> None:
        guild = role.guild
        mod = None
        try:
            await asyncio.sleep(0.4)
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.role_create):
                if entry.target.id == role.id:
                    mod = entry.user
                    break
        except discord.Forbidden:
            pass

        details = []
        if role.color.value:
            details.append(f"Color: `{str(role.color)}`")
        if role.mentionable:
            details.append("Mentionable: ✅")
        if role.hoist:
            details.append("Displayed separately: ✅")

        embed = create_audit_embed(
            title="🎭 Role created",
            subject=role.mention,
            subject_header="🎭  Role",
            action_desc=f"Role {role.mention} was created.",
            actor=mod,
            actor_label="Created By",
            details=details or ["No special permissions"],
            color=C.SUCCESS,
            footer_text="Role Create"
        )
        await self._send(guild, "role_create", embed)

    async def on_guild_role_delete(self, role: discord.Role) -> None:
        guild = role.guild
        mod = None
        try:
            await asyncio.sleep(0.4)
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.role_delete):
                if entry.target.id == role.id:
                    mod = entry.user
                    break
        except discord.Forbidden:
            pass

        embed = create_audit_embed(
            title="🗑️ Role deleted",
            subject=f"**@{role.name}**",
            subject_header="🎭  Role",
            action_desc=f"Role **@{role.name}** was deleted from the server.",
            actor=mod,
            actor_label="Deleted By",
            details=[
                f"Color: `{str(role.color)}`" if role.color.value else "Color: Default",
            ],
            color=C.DANGER,
            footer_text="Role Delete"
        )
        await self._send(guild, "role_delete", embed)

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        guild = after.guild
        changes = []
        if before.name != after.name:
            changes.append(("Name", before.name, after.name))
        if before.color != after.color:
            changes.append(("Color", str(before.color), str(after.color)))
        if before.hoist != after.hoist:
            changes.append(("Hoisted", str(before.hoist), str(after.hoist)))
        if before.mentionable != after.mentionable:
            changes.append(("Mentionable", str(before.mentionable), str(after.mentionable)))
        if not changes:
            return

        mod = None
        try:
            await asyncio.sleep(0.4)
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.role_update):
                if entry.target.id == after.id:
                    mod = entry.user
                    break
        except discord.Forbidden:
            pass

        embed = create_audit_embed(
            title="✏️ Role updated",
            subject=after.mention,
            subject_header="🎭  Role",
            action_desc=f"Role {after.mention} was modified.",
            actor=mod,
            actor_label="Updated By",
            changes=changes,
            color=C.PURPLE,
            footer_text="Role Update"
        )
        await self._send(guild, "role_update", embed)

    # ── Message Events ────────────────────────────────────────────────────────

    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return

        content_preview = f"> {_trunc(message.content)}" if message.content else "*[No text content]*"
        details = [f"Channel: {message.channel.mention}", content_preview]
        if message.attachments:
            details.append(f"Attachments: {', '.join(a.filename for a in message.attachments)}")

        embed = create_audit_embed(
            title="🗑️ Message deleted",
            subject=f"#{message.channel.name}",
            actor=message.author,
            details=details,
            color=C.DANGER,
            thumbnail_url=message.author.display_avatar.url,
            footer_text="Message Delete"
        )
        await self._send(message.guild, "message_delete", embed)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or after.author.bot or before.content == after.content:
            return

        embed = create_audit_embed(
            title="📝 Message edited",
            subject=f"#{after.channel.name}",
            actor=after.author,
            changes=[("Content", _trunc(before.content, 200), _trunc(after.content, 200))],
            details=[f"[View Message]({after.jump_url})"],
            color=C.WARNING,
            thumbnail_url=after.author.display_avatar.url,
            footer_text="Message Edit"
        )
        await self._send(after.guild, "message_edit", embed)

    async def on_bulk_message_delete(self, messages: List[discord.Message]) -> None:
        if not messages or not messages[0].guild:
            return
        guild = messages[0].guild
        channel = messages[0].channel

        embed = create_audit_embed(
            title="🗑️ Bulk messages deleted",
            subject=f"#{channel.name}",
            details=[f"{len(messages):,} messages purged"],
            color=C.DANGER,
            footer_text="Bulk Purge"
        )
        await self._send(guild, "message_bulk_delete", embed)


    # ── Channel Events ────────────────────────────────────────────────────────

    async def on_guild_channel_create(self, channel) -> None:
        creator = None
        try:
            async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
                creator = entry.user
                break
        except discord.Forbidden:
            pass

        details = [f"Type: `{channel.type}`"]
        if channel.category:
            details.append(f"Category: {channel.category.name}")

        embed = create_audit_embed(
            title="➕ Channel created",
            subject=channel.mention if hasattr(channel, "mention") else f"#{channel.name}",
            actor=creator,
            details=details,
            color=C.SUCCESS,
            footer_text="Channel Created"
        )
        await self._send(channel.guild, "channel_create", embed)

    async def on_guild_channel_delete(self, channel) -> None:
        deleter = None
        try:
            async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
                deleter = entry.user
                break
        except discord.Forbidden:
            pass

        details = [f"Type: `{channel.type}`"]
        embed = create_audit_embed(
            title="➖ Channel deleted",
            subject=f"#{channel.name}",
            actor=deleter,
            details=details,
            color=C.DANGER,
            footer_text="Channel Deleted"
        )
        await self._send(channel.guild, "channel_delete", embed)

    async def on_guild_channel_update(self, before, after) -> None:
        changes: List[Tuple[str, str, str]] = []
        if before.name != after.name:
            changes.append(("Name", before.name, after.name))
        if hasattr(before, "topic") and before.topic != after.topic:
            changes.append(("Topic", _trunc(before.topic or "None", 100), _trunc(after.topic or "None", 100)))
        if hasattr(before, "slowmode_delay") and before.slowmode_delay != after.slowmode_delay:
            changes.append(("Slowmode", f"{before.slowmode_delay}s", f"{after.slowmode_delay}s"))

        if not changes:
            return

        embed = create_audit_embed(
            title="🔧 Channel updated",
            subject=after.mention if hasattr(after, "mention") else f"#{after.name}",
            changes=changes,
            color=C.BRAND,
            footer_text="Channel Update"
        )
        await self._send(after.guild, "channel_update", embed)

    async def on_stage_instance_create(self, stage_instance: discord.StageInstance) -> None:
        channel = stage_instance.channel
        embed = create_audit_embed(
            title="🎭 Stage event started",
            subject=channel.mention if hasattr(channel, "mention") else f"#{channel.name}",
            details=[f"Topic: {stage_instance.topic}"],
            color=C.PURPLE,
            footer_text="Stage Channel"
        )
        await self._send(stage_instance.guild, "stage_instance_create", embed)

    async def on_stage_instance_delete(self, stage_instance: discord.StageInstance) -> None:
        channel = stage_instance.channel
        embed = create_audit_embed(
            title="🎭 Stage event ended",
            subject=channel.mention if channel and hasattr(channel, "mention") else "Stage Channel",
            color=C.MUTED,
            footer_text="Stage Channel"
        )
        await self._send(stage_instance.guild, "stage_instance_delete", embed)

    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        embed = create_audit_embed(
            title="🪝 Webhooks updated",
            subject=channel.mention if hasattr(channel, "mention") else f"#{channel.name}",
            color=C.CYAN,
            footer_text="Webhook Activity"
        )
        await self._send(channel.guild, "webhook_update", embed)


    # ── Role Events ───────────────────────────────────────────────────────────

    async def on_guild_role_create(self, role: discord.Role) -> None:
        creator = None
        try:
            async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
                creator = entry.user
                break
        except discord.Forbidden:
            pass

        embed = create_audit_embed(
            title="🎭 Role created",
            subject=role.mention,
            actor=creator,
            details=[
                f"Color #{role.color.value:06x}",
                "Hoisted" if role.hoist else "Not hoisted"
            ],
            color=C.PURPLE,
            footer_text="Role Created"
        )
        await self._send(role.guild, "role_create", embed)

    async def on_guild_role_delete(self, role: discord.Role) -> None:
        deleter = None
        try:
            async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
                deleter = entry.user
                break
        except discord.Forbidden:
            pass

        embed = create_audit_embed(
            title="🗑️ Role deleted",
            subject=f"@{role.name}",
            actor=deleter,
            details=[f"Had {len(role.members):,} members"],
            color=C.DANGER,
            footer_text="Role Deleted"
        )
        await self._send(role.guild, "role_delete", embed)

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        changes: List[Tuple[str, str, str]] = []
        if before.name != after.name:
            changes.append(("Name", before.name, after.name))
        if before.color != after.color:
            changes.append(("Color", f"#{before.color.value:06x}", f"#{after.color.value:06x}"))
        if before.hoist != after.hoist:
            changes.append(("Hoisted", str(before.hoist), str(after.hoist)))
        if before.mentionable != after.mentionable:
            changes.append(("Mentionable", str(before.mentionable), str(after.mentionable)))

        if not changes:
            return

        embed = create_audit_embed(
            title="✏️ Role updated",
            subject=after.mention,
            changes=changes,
            color=C.PURPLE,
            footer_text="Role Update"
        )
        await self._send(after.guild, "role_update", embed)


    # ── Voice Events ──────────────────────────────────────────────────────────

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild = member.guild

        if before.channel is None and after.channel is not None:
            embed = create_audit_embed(
                title="🔊 Joined voice",
                subject=member.mention,
                details=[f"Channel: {after.channel.mention}"],
                color=C.CYAN,
                thumbnail_url=member.display_avatar.url,
                footer_text="Voice Activity"
            )
            await self._send(guild, "voice_join", embed)

        elif before.channel is not None and after.channel is None:
            embed = create_audit_embed(
                title="🔇 Left voice",
                subject=member.mention,
                details=[f"Channel: {before.channel.mention}"],
                color=C.MUTED,
                thumbnail_url=member.display_avatar.url,
                footer_text="Voice Activity"
            )
            await self._send(guild, "voice_leave", embed)

        elif before.channel != after.channel and before.channel and after.channel:
            embed = create_audit_embed(
                title="🔀 Moved voice channel",
                subject=member.mention,
                changes=[("Channel", before.channel.name, after.channel.name)],
                color=C.BRAND,
                thumbnail_url=member.display_avatar.url,
                footer_text="Voice Activity"
            )
            await self._send(guild, "voice_move", embed)

        elif before.self_mute != after.self_mute or before.mute != after.mute:
            muted = after.self_mute or after.mute
            embed = create_audit_embed(
                title="🔕 Muted in voice" if muted else "🔔 Unmuted in voice",
                subject=member.mention,
                details=[f"Channel: {after.channel.mention if after.channel else 'N/A'}"],
                color=C.WARNING if muted else C.SUCCESS,
                thumbnail_url=member.display_avatar.url,
                footer_text="Voice State"
            )
            await self._send(guild, "voice_mute", embed)

        if before.self_stream != after.self_stream:
            streaming = after.self_stream
            embed = create_audit_embed(
                title="📡 Stream started (Go Live)" if streaming else "📡 Stream ended",
                subject=member.mention,
                details=[f"Channel: {after.channel.mention if streaming and after.channel else before.channel.mention if before.channel else 'N/A'}"],
                color=C.PURPLE,
                thumbnail_url=member.display_avatar.url,
                footer_text="Screen Share"
            )
            await self._send(guild, "voice_stream", embed)

        if before.self_video != after.self_video:
            video_on = after.self_video
            embed = create_audit_embed(
                title="📷 Camera enabled" if video_on else "📷 Camera disabled",
                subject=member.mention,
                details=[f"Channel: {after.channel.mention if video_on and after.channel else before.channel.mention if before.channel else 'N/A'}"],
                color=C.CYAN,
                thumbnail_url=member.display_avatar.url,
                footer_text="Video Activity"
            )
            await self._send(guild, "voice_camera", embed)


    # ── Server, Invites, Emojis, Stickers, Events ─────────────────────────────

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        changes: List[Tuple[str, str, str]] = []
        if before.name != after.name:
            changes.append(("Server Name", before.name, after.name))
        if before.icon != after.icon:
            changes.append(("Server Icon", "Previous Icon", "New Icon Set"))
        if before.verification_level != after.verification_level:
            changes.append(("Verification", str(before.verification_level), str(after.verification_level)))

        if not changes:
            return

        embed = create_audit_embed(
            title="⚙️ Server settings updated",
            subject=after.name,
            changes=changes,
            color=C.BRAND,
            thumbnail_url=after.icon.url if after.icon else None,
            footer_text="Server Settings"
        )
        await self._send(after, "server_update", embed)

    async def on_invite_create(self, invite: discord.Invite) -> None:
        if not invite.guild:
            return
        details = [f"Channel: {invite.channel.mention if invite.channel else 'N/A'}", f"Max uses: {invite.max_uses or '∞'}"]
        embed = create_audit_embed(
            title="🔗 Invite created",
            subject=f"discord.gg/{invite.code}",
            actor=invite.inviter,
            details=details,
            color=C.SUCCESS,
            footer_text="Invite Create"
        )
        await self._send(invite.guild, "invite_create", embed)

    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if not invite.guild:
            return
        embed = create_audit_embed(
            title="🗑️ Invite deleted",
            subject=f"discord.gg/{invite.code}",
            details=[f"Channel: {invite.channel.mention if invite.channel else 'N/A'}"],
            color=C.DANGER,
            footer_text="Invite Delete"
        )
        await self._send(invite.guild, "invite_delete", embed)

    async def on_guild_emojis_update(
        self,
        guild: discord.Guild,
        before: List[discord.Emoji],
        after: List[discord.Emoji],
    ) -> None:
        added   = [e for e in after  if e not in before]
        removed = [e for e in before if e not in after]
        if not added and not removed:
            return

        details = []
        if added:
            details.append(f"Added: {' '.join(str(e) for e in added[:8])}")
        if removed:
            details.append(f"Removed: {' '.join(f':{e.name}:' for e in removed[:8])}")

        embed = create_audit_embed(
            title="😀 Emoji updated",
            subject=guild.name,
            details=details,
            color=C.GOLD,
            footer_text="Emoji Update"
        )
        await self._send(guild, "emoji_update", embed)

    async def on_guild_stickers_update(
        self,
        guild: discord.Guild,
        before: List[discord.GuildSticker],
        after: List[discord.GuildSticker],
    ) -> None:
        added   = [s for s in after  if s not in before]
        removed = [s for s in before if s not in after]
        if not added and not removed:
            return

        details = []
        if added:
            details.append(f"Added: {', '.join(f'`{s.name}`' for s in added[:8])}")
        if removed:
            details.append(f"Removed: {', '.join(f'`{s.name}`' for s in removed[:8])}")

        embed = create_audit_embed(
            title="🏷️ Sticker updated",
            subject=guild.name,
            details=details,
            color=C.GOLD,
            footer_text="Sticker Update"
        )
        await self._send(guild, "sticker_update", embed)

    async def on_scheduled_event_create(self, event: discord.ScheduledEvent) -> None:
        details = [f"Location: {event.location or 'Discord Voice'}", f"Starts: {fmt_ts(event.start_time)}"]
        if event.description:
            details.append(f"> {_trunc(event.description, 200)}")

        embed = create_audit_embed(
            title="📅 Scheduled event created",
            subject=event.name,
            actor=event.creator,
            details=details,
            color=C.SUCCESS,
            thumbnail_url=event.cover.url if event.cover else None,
            footer_text="Scheduled Event"
        )
        await self._send(event.guild, "event_create", embed)

    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent) -> None:
        embed = create_audit_embed(
            title="🗑️ Scheduled event deleted",
            subject=event.name,
            color=C.DANGER,
            footer_text="Scheduled Event"
        )
        await self._send(event.guild, "event_delete", embed)

    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent) -> None:
        changes: List[Tuple[str, str, str]] = []
        if before.name != after.name:
            changes.append(("Name", before.name, after.name))
        if before.start_time != after.start_time:
            changes.append(("Start Time", fmt_ts(before.start_time), fmt_ts(after.start_time)))
        if before.status != after.status:
            changes.append(("Status", str(before.status), str(after.status)))

        if not changes:
            return

        embed = create_audit_embed(
            title="📅 Scheduled event updated",
            subject=after.name,
            changes=changes,
            color=C.BRAND,
            footer_text="Scheduled Event"
        )
        await self._send(after.guild, "event_update", embed)


    # ── Thread Events ─────────────────────────────────────────────────────────

    async def on_thread_create(self, thread: discord.Thread) -> None:
        details = [f"Parent: {thread.parent.mention if thread.parent else 'N/A'}"]
        embed = create_audit_embed(
            title="🧵 Thread created",
            subject=thread.mention,
            actor=thread.owner,
            details=details,
            color=C.CYAN,
            footer_text="Thread Created"
        )
        await self._send(thread.guild, "thread_create", embed)

    async def on_thread_delete(self, thread: discord.Thread) -> None:
        embed = create_audit_embed(
            title="🗑️ Thread deleted",
            subject=f"#{thread.name}",
            details=[f"Parent: {thread.parent.mention if thread.parent else 'N/A'}"],
            color=C.DANGER,
            footer_text="Thread Deleted"
        )
        await self._send(thread.guild, "thread_delete", embed)

    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        changes: List[Tuple[str, str, str]] = []
        if before.name != after.name:
            changes.append(("Name", before.name, after.name))
        if before.archived != after.archived:
            changes.append(("Archived", str(before.archived), str(after.archived)))
        if before.locked != after.locked:
            changes.append(("Locked", str(before.locked), str(after.locked)))
        if before.slowmode_delay != after.slowmode_delay:
            changes.append(("Slowmode", f"{before.slowmode_delay}s", f"{after.slowmode_delay}s"))

        if not changes:
            return

        embed = create_audit_embed(
            title="🧵 Thread updated",
            subject=after.mention,
            changes=changes,
            color=C.CYAN,
            footer_text="Thread Update"
        )
        await self._send(after.guild, "thread_update", embed)


    # ── Command, AutoMod & Message Listeners ───────────────────────────────────

    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return

        has_mention = bool(message.mentions or message.role_mentions or message.mention_everyone)
        if has_mention:
            mentions_list = []
            if message.mentions:
                mentions_list.append(" ".join(u.mention for u in message.mentions[:5]))
            if message.role_mentions:
                mentions_list.append(" ".join(r.mention for r in message.role_mentions[:5]))
            if message.mention_everyone:
                mentions_list.append("@everyone")

            details = [f"Channel: {message.channel.mention}", f"Mentions: {' '.join(mentions_list)}"]
            if message.content:
                details.append(f"> {_trunc(message.content, 200)}")

            embed = create_audit_embed(
                title="📣 Mention detected",
                subject=f"#{message.channel.name}",
                actor=message.author,
                details=details,
                color=C.WARNING,
                thumbnail_url=message.author.display_avatar.url,
                footer_text="Mention Activity"
            )
            await self._send(message.guild, "message_mention", embed)

    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type != discord.InteractionType.application_command or not interaction.guild:
            return
        data = interaction.data or {}
        cmd_name = data.get("name", "unknown")

        embed = create_audit_embed(
            title="🔷 Slash command used",
            subject=f"/{cmd_name}",
            actor=interaction.user,
            details=[f"Channel: {interaction.channel.mention if interaction.channel else 'N/A'}"],
            color=C.BRAND,
            thumbnail_url=interaction.user.display_avatar.url if interaction.user else None,
            footer_text="Command Log"
        )
        await self._send(interaction.guild, "command_used", embed)

    async def on_automod_action_execution(self, execution: discord.AutoModActionExecution) -> None:
        details = [
            f"Rule ID: `{execution.rule_id}`",
            f"Action: `{execution.action.type.name}`",
            f"Channel: <#{execution.channel_id}>" if execution.channel_id else "N/A"
        ]
        if execution.matched_keyword:
            details.append(f"Matched keyword: `{execution.matched_keyword}`")
        if execution.content:
            details.append(f"> {_trunc(execution.content, 200)}")

        embed = create_audit_embed(
            title="🛡️ AutoMod triggered",
            subject=f"<@{execution.user_id}>",
            details=details,
            color=C.DANGER,
            footer_text="AutoMod Execution"
        )
        await self._send(execution.guild, "automod_execution", embed)


# ─── Interactive UI Components ────────────────────────────────────────────────

EVENT_DESCRIPTIONS: Dict[str, str] = {
    "member_join":           "Member joins the server",
    "member_leave":          "Member leaves the server",
    "member_ban":            "Member is banned",
    "member_unban":          "Member is unbanned",
    "member_kick":           "Member is kicked from server",
    "member_timeout":        "Member is timed out",
    "member_role_add":       "Role added to member",
    "member_role_remove":    "Role removed from member",
    "member_nickname":       "Member nickname changes",
    "message_delete":        "Message is deleted",
    "message_edit":          "Message is edited",
    "message_bulk_delete":   "Bulk message deletion (purge)",
    "message_send":          "A message is sent",
    "message_mention":       "A message containing mentions is sent",
    "channel_create":        "Channel created",
    "channel_delete":        "Channel deleted",
    "channel_update":        "Channel settings changed",
    "stage_instance_create": "Stage channel started",
    "stage_instance_delete": "Stage channel ended",
    "webhook_update":        "Webhook created, edited, or removed",
    "role_create":           "Role created",
    "role_delete":           "Role deleted",
    "role_update":           "Role updated",
    "voice_join":            "User joins voice channel",
    "voice_leave":           "User leaves voice channel",
    "voice_move":            "User moves between voice channels",
    "voice_mute":            "User mutes/unmutes in voice",
    "voice_stream":          "User starts/stops Go Live screen share",
    "voice_camera":          "User turns camera on/off",
    "server_update":         "Server settings changed",
    "invite_create":         "Invite link created",
    "invite_delete":         "Invite link deleted/expired",
    "emoji_update":          "Emoji added or removed",
    "sticker_update":        "Custom sticker added or removed",
    "event_create":          "Scheduled server event created",
    "event_delete":          "Scheduled server event deleted",
    "event_update":          "Scheduled server event updated",
    "thread_create":         "Thread created",
    "thread_delete":         "Thread deleted",
    "thread_update":         "Thread settings or archive status changed",
    "command_used":          "Any slash command used",
    "bot_message":           "Bot sends a message",
    "automod_execution":     "Discord AutoMod triggers a rule action",
}


class LogEventSelect(discord.ui.Select):
    def __init__(self, db: LogsDB, guild_id: int, category: str, events: List[str]):
        self.db = db
        self.guild_id = guild_id
        self.category = category
        self.events = events

        cfg = db.get(guild_id)
        enabled_events = set(cfg["enabled_events"])

        options = [
            discord.SelectOption(
                label=ev,
                description=EVENT_DESCRIPTIONS.get(ev, "")[:100],
                value=ev,
                default=(ev in enabled_events)
            )
            for ev in events
        ]
        super().__init__(
            placeholder=f"Select {category.title()} events...",
            min_values=0,
            max_values=len(options),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        cfg = self.db.get(self.guild_id)
        enabled_set = set(cfg["enabled_events"])

        for ev in self.events:
            if ev in enabled_set:
                enabled_set.remove(ev)

        for val in self.values:
            enabled_set.add(val)

        cfg["enabled_events"] = list(enabled_set)
        self.db.save(cfg)

        await interaction.response.send_message(
            embed=embed_success("Log Events Updated", f"Updated active events for **{self.category.title()}**."),
            ephemeral=True
        )


class LogCategorySelect(discord.ui.Select):
    def __init__(self, db: LogsDB, guild_id: int):
        self.db = db
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label=cat.title(), value=cat, description=f"Configure {cat} log events")
            for cat in EVENT_CATEGORIES.keys()
        ]
        super().__init__(placeholder="Choose a category to configure...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        events = EVENT_CATEGORIES[category]

        view = discord.ui.View()
        view.add_item(LogCategorySelect(self.db, self.guild_id))
        view.add_item(LogEventSelect(self.db, self.guild_id, category, events))

        await interaction.response.edit_message(
            embed=embed_info(f"⚙️  Configure {category.title()} Events", "Toggle specific event notifications below:"),
            view=view
        )


# ─── Main Server Logs Cog ─────────────────────────────────────────────────────

class ServerLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = LogsDB()
        self.db.initialize()
        self.logger = ServerLogger(bot, self.db)

    def cog_load(self):
        self.logger.start()
        self.bot.add_listener(self.logger.on_member_join,               "on_member_join")
        self.bot.add_listener(self.logger.on_member_remove,             "on_member_remove")
        self.bot.add_listener(self.logger.on_member_ban,                "on_member_ban")
        self.bot.add_listener(self.logger.on_member_unban,              "on_member_unban")
        self.bot.add_listener(self.logger.on_member_update,             "on_member_update")
        self.bot.add_listener(self.logger.on_message_delete,            "on_message_delete")
        self.bot.add_listener(self.logger.on_message_edit,              "on_message_edit")
        self.bot.add_listener(self.logger.on_bulk_message_delete,       "on_bulk_message_delete")
        self.bot.add_listener(self.logger.on_guild_channel_create,      "on_guild_channel_create")
        self.bot.add_listener(self.logger.on_guild_channel_delete,      "on_guild_channel_delete")
        self.bot.add_listener(self.logger.on_guild_channel_update,      "on_guild_channel_update")
        self.bot.add_listener(self.logger.on_stage_instance_create,     "on_stage_instance_create")
        self.bot.add_listener(self.logger.on_stage_instance_delete,     "on_stage_instance_delete")
        self.bot.add_listener(self.logger.on_webhooks_update,           "on_webhooks_update")
        self.bot.add_listener(self.logger.on_guild_role_create,         "on_guild_role_create")
        self.bot.add_listener(self.logger.on_guild_role_delete,         "on_guild_role_delete")
        self.bot.add_listener(self.logger.on_guild_role_update,         "on_guild_role_update")
        self.bot.add_listener(self.logger.on_voice_state_update,        "on_voice_state_update")
        self.bot.add_listener(self.logger.on_guild_update,              "on_guild_update")
        self.bot.add_listener(self.logger.on_invite_create,             "on_invite_create")
        self.bot.add_listener(self.logger.on_invite_delete,             "on_invite_delete")
        self.bot.add_listener(self.logger.on_guild_emojis_update,       "on_guild_emojis_update")
        self.bot.add_listener(self.logger.on_guild_stickers_update,     "on_guild_stickers_update")
        self.bot.add_listener(self.logger.on_scheduled_event_create,   "on_scheduled_event_create")
        self.bot.add_listener(self.logger.on_scheduled_event_delete,   "on_scheduled_event_delete")
        self.bot.add_listener(self.logger.on_scheduled_event_update,   "on_scheduled_event_update")
        self.bot.add_listener(self.logger.on_thread_create,             "on_thread_create")
        self.bot.add_listener(self.logger.on_thread_delete,             "on_thread_delete")
        self.bot.add_listener(self.logger.on_thread_update,             "on_thread_update")
        self.bot.add_listener(self.logger.on_message,                   "on_message")
        self.bot.add_listener(self.logger.on_interaction,               "on_interaction")
        self.bot.add_listener(self.logger.on_automod_action_execution,  "on_automod_action_execution")

    def cog_unload(self):
        self.logger.stop()
        self.bot.remove_listener(self.logger.on_member_join,               "on_member_join")
        self.bot.remove_listener(self.logger.on_member_remove,             "on_member_remove")
        self.bot.remove_listener(self.logger.on_member_ban,                "on_member_ban")
        self.bot.remove_listener(self.logger.on_member_unban,              "on_member_unban")
        self.bot.remove_listener(self.logger.on_member_update,             "on_member_update")
        self.bot.remove_listener(self.logger.on_message_delete,            "on_message_delete")
        self.bot.remove_listener(self.logger.on_message_edit,              "on_message_edit")
        self.bot.remove_listener(self.logger.on_bulk_message_delete,       "on_bulk_message_delete")
        self.bot.remove_listener(self.logger.on_guild_channel_create,      "on_guild_channel_create")
        self.bot.remove_listener(self.logger.on_guild_channel_delete,      "on_guild_channel_delete")
        self.bot.remove_listener(self.logger.on_guild_channel_update,      "on_guild_channel_update")
        self.bot.remove_listener(self.logger.on_stage_instance_create,     "on_stage_instance_create")
        self.bot.remove_listener(self.logger.on_stage_instance_delete,     "on_stage_instance_delete")
        self.bot.remove_listener(self.logger.on_webhooks_update,           "on_webhooks_update")
        self.bot.remove_listener(self.logger.on_guild_role_create,         "on_guild_role_create")
        self.bot.remove_listener(self.logger.on_guild_role_delete,         "on_guild_role_delete")
        self.bot.remove_listener(self.logger.on_guild_role_update,         "on_guild_role_update")
        self.bot.remove_listener(self.logger.on_voice_state_update,        "on_voice_state_update")
        self.bot.remove_listener(self.logger.on_guild_update,              "on_guild_update")
        self.bot.remove_listener(self.logger.on_invite_create,             "on_invite_create")
        self.bot.remove_listener(self.logger.on_invite_delete,             "on_invite_delete")
        self.bot.remove_listener(self.logger.on_guild_emojis_update,       "on_guild_emojis_update")
        self.bot.remove_listener(self.logger.on_guild_stickers_update,     "on_guild_stickers_update")
        self.bot.remove_listener(self.logger.on_scheduled_event_create,   "on_scheduled_event_create")
        self.bot.remove_listener(self.logger.on_scheduled_event_delete,   "on_scheduled_event_delete")
        self.bot.remove_listener(self.logger.on_scheduled_event_update,   "on_scheduled_event_update")
        self.bot.remove_listener(self.logger.on_thread_create,             "on_thread_create")
        self.bot.remove_listener(self.logger.on_thread_delete,             "on_thread_delete")
        self.bot.remove_listener(self.logger.on_thread_update,             "on_thread_update")
        self.bot.remove_listener(self.logger.on_message,                   "on_message")
        self.bot.remove_listener(self.logger.on_interaction,               "on_interaction")
        self.bot.remove_listener(self.logger.on_automod_action_execution,  "on_automod_action_execution")

    # ── Slash Commands ────────────────────────────────────────────────────────

    logs_group = app_commands.Group(
        name="logs",
        description="Configure server event logging and category channels",
    )

    @logs_group.command(
        name="setup",
        description="Auto-create category-based private log channels in small caps format with emojis"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_logs(self, interaction: discord.Interaction) -> None:
        """Automatically create private category log channels for this server."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(embed=embed_error("This command must be run inside a server."), ephemeral=True)
            return

        # Check permissions
        me = guild.me
        if not me.guild_permissions.manage_channels:
            await interaction.followup.send(
                embed=embed_error("Bot requires `Manage Channels` permission to auto-create log channels."),
                ephemeral=True
            )
            return

        cfg = self.db.get(guild.id)
        if "category_channels" not in cfg:
            cfg["category_channels"] = {}

        # 1. Create or resolve the private Category
        category_name = "📋・ꜱᴇʀᴠᴇʀ-ʟᴏɢꜱ"
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = discord.utils.get(guild.categories, name="📋 Logs")
        if not category:
            category = discord.utils.get(guild.categories, name="Server Logs")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
            ),
        }

        if not category:
            try:
                category = await guild.create_category(
                    category_name,
                    overwrites=overwrites,
                    reason="Auto-created GKR Server Logs Category"
                )
            except Exception as exc:
                await interaction.followup.send(
                    embed=embed_error(f"Failed to create category: {exc}"),
                    ephemeral=True
                )
                return

        # 2. Provision each channel under the category
        created_channels: List[Tuple[str, discord.TextChannel, bool]] = []
        master_channel_id: Optional[int] = None

        for cat_key, ch_name, label, desc in CATEGORY_SPECS:
            existing_ch = None
            # Check existing config or look for channel under category
            stored_id = cfg["category_channels"].get(cat_key)
            if stored_id:
                existing_ch = guild.get_channel(int(stored_id))

            if not existing_ch:
                # Search by exact or clean name in the category
                for ch in category.text_channels:
                    if ch.name.lower() == ch_name.lower() or ch.name.lower() == ch_name.replace("・", "-").lower():
                        existing_ch = ch
                        break

            if existing_ch:
                cfg["category_channels"][cat_key] = existing_ch.id
                created_channels.append((label, existing_ch, False))
                if master_channel_id is None:
                    master_channel_id = existing_ch.id
            else:
                try:
                    new_ch = await guild.create_text_channel(
                        name=ch_name,
                        category=category,
                        topic=f"GKR Server Audit Log: {desc}",
                        reason="Auto-created category log channel"
                    )
                    cfg["category_channels"][cat_key] = new_ch.id
                    created_channels.append((label, new_ch, True))
                    if master_channel_id is None:
                        master_channel_id = new_ch.id
                except Exception as exc:
                    print(f"[Logs Setup] Failed to create #{ch_name}: {exc}")

        # 3. Update database
        cfg["enabled"] = True
        if master_channel_id and not cfg.get("log_channel_id"):
            cfg["log_channel_id"] = master_channel_id
        self.db.save(cfg)

        # 4. Build response embed
        lines = []
        for label, ch, is_new in created_channels:
            status_tag = "`Created`" if is_new else "`Linked`"
            lines.append(f"• **{label}:** {ch.mention} ({status_tag})")

        embed = discord.Embed(
            title="📋  Server Log Channels Configured",
            description=(
                f"Successfully provisioned category log channels under **{category.name}**.\n\n"
                + "\n".join(lines)
                + f"\n\n🔒 *All log channels are private and restricted to server staff.*"
            ),
            color=C.SUCCESS
        )
        embed.set_footer(text=f"Total active event types: {len(ALL_EVENTS)} trackable events")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @logs_group.command(name="channel", description="Set a single master channel where all server logs will be sent")
    @app_commands.default_permissions(manage_guild=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        cfg = self.db.get(interaction.guild.id)
        cfg["log_channel_id"] = channel.id
        cfg["enabled"] = True
        self.db.save(cfg)

        embed = embed_success(
            "Logs Channel Configured",
            f"Server events will now be logged to {channel.mention}.\nActive events: `{len(cfg['enabled_events'])}/{len(ALL_EVENTS)}`"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @logs_group.command(name="toggle", description="Enable or disable the logging system for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle(self, interaction: discord.Interaction) -> None:
        cfg = self.db.get(interaction.guild.id)
        cfg["enabled"] = not cfg["enabled"]
        self.db.save(cfg)
        status_text = "Enabled" if cfg["enabled"] else "Disabled"
        embed = embed_success("Logging Status", f"Server event logging is now **{status_text}**.") if cfg["enabled"] else embed_warning(f"Server event logging is now **{status_text}**.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @logs_group.command(name="status", description="Show current logging configuration and category routing")
    @app_commands.default_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction) -> None:
        cfg = self.db.get(interaction.guild.id)
        ch = interaction.guild.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None

        lines = [
            f"**Master Channel:** {ch.mention if ch else '`Not set`'}",
            f"**Active Events:** `{len(cfg['enabled_events'])}` / `{len(ALL_EVENTS)}`\n",
            "**Category Breakdown & Routing:**"
        ]
        for cat, events in EVENT_CATEGORIES.items():
            active = sum(1 for e in events if e in cfg["enabled_events"])
            override_id = cfg["category_channels"].get(cat)
            route_str = f" → <#{override_id}>" if override_id else ""
            dot = "🟢" if active == len(events) else ("🟡" if active > 0 else "⚪")
            lines.append(f"{dot} **{cat.title()}**: `{active}/{len(events)}`{route_str}")

        embed = embed_info(
            "📋  Server Logging Configuration",
            "\n".join(lines),
            color=C.BRAND if cfg["enabled"] else C.NEUTRAL
        )
        embed.set_footer(text="Use /logs setup to auto-create all channels, or /logs config to toggle events")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @logs_group.command(name="route", description="Route a specific category of logs to a separate channel")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(category=[app_commands.Choice(name=c.title(), value=c) for c in EVENT_CATEGORIES.keys()])
    async def route(self, interaction: discord.Interaction, category: str, channel: discord.TextChannel) -> None:
        cfg = self.db.get(interaction.guild.id)
        if "category_channels" not in cfg:
            cfg["category_channels"] = {}

        cfg["category_channels"][category] = channel.id
        self.db.save(cfg)

        await interaction.response.send_message(
            embed=embed_success("Log Route Updated", f"**{category.title()}** logs will now be sent to {channel.mention}."),
            ephemeral=True
        )

    @logs_group.command(name="unroute", description="Remove a custom channel route for a category")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(category=[app_commands.Choice(name=c.title(), value=c) for c in EVENT_CATEGORIES.keys()])
    async def unroute(self, interaction: discord.Interaction, category: str) -> None:
        cfg = self.db.get(interaction.guild.id)
        if "category_channels" in cfg and category in cfg["category_channels"]:
            del cfg["category_channels"][category]
            self.db.save(cfg)
            master_ch = interaction.guild.get_channel(cfg["log_channel_id"]) if cfg["log_channel_id"] else None
            dest = master_ch.mention if master_ch else "the master log channel"
            await interaction.response.send_message(
                embed=embed_success("Route Removed", f"**{category.title()}** logs will now fall back to {dest}."),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed_info("No Custom Route", f"**{category.title()}** is not currently routed to a custom channel."),
                ephemeral=True
            )

    @logs_group.command(name="config", description="Interactive dropdown menu to toggle specific log events")
    @app_commands.default_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        view = discord.ui.View()
        view.add_item(LogCategorySelect(self.db, interaction.guild.id))
        await interaction.response.send_message(
            embed=embed_info("⚙️  Log Event Configuration", "Select a category from the dropdown below to customize active events:"),
            view=view,
            ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerLogsCog(bot))
    print("📋 Server Logs system loaded!")
