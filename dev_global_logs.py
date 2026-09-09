"""
dev_global_logs.py — Developer-Only Global Bot Monitoring System.

Accessible ONLY inside the developer guild (DISCORD_GUILD_ID).
Dispatches cross-server activity using the centralized GKR design system.
"""

from __future__ import annotations

import os
import sys
import json
import time
import asyncio
import sqlite3
import datetime
import threading
import traceback
import urllib.request
from typing import Optional, List, Dict

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from gkr_ui import (
    C,
    create_audit_embed,
    embed_success,
    embed_error,
    embed_info,
    fmt_rel,
    Paginator,
)

DEV_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
DB_PATH = os.path.join(os.path.dirname(__file__), "dev_logs.sqlite3")

# Remote console for crash/bug forwarding
CONSOLE_HOST = "89.106.84.82"
CONSOLE_PORT = 2011
CONSOLE_URL  = f"http://{CONSOLE_HOST}:{CONSOLE_PORT}/api/report"

DEV_LOG_CHANNELS = [
    ("error_logs",   "dev-error-and-crashes", "Unhandled errors, exceptions, and bot crashes across all servers"),
    ("bug_reports",  "dev-bug-reports",       "Developer crash and bug reports from all servers"),
    ("role_logs",    "dev-role-logs",         "All role & member-role events across all servers"),
    ("member_logs",  "dev-member-logs",       "All member join/leave/ban events across all servers"),
    ("message_logs", "dev-message-logs",      "All deleted and edited messages across all servers"),
    ("command_logs", "dev-command-logs",      "All slash commands used across all servers"),
    ("invite_logs",  "dev-invite-logs",       "All invite events across all servers"),
    ("server_events","dev-server-events",     "Channel, role, and server-level changes across all servers"),
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class DevLogsDB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS dev_log_channels (
                    key        TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS dev_bug_reports (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT    NOT NULL DEFAULT 'bug',
                    title       TEXT    NOT NULL,
                    description TEXT    NOT NULL,
                    reporter_id TEXT    NOT NULL,
                    reporter    TEXT    NOT NULL,
                    guild_id    TEXT    NOT NULL,
                    guild_name  TEXT    NOT NULL,
                    console_ok  INTEGER NOT NULL DEFAULT 0,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.commit()

    def log_report(
        self,
        report_type: str,
        title: str,
        description: str,
        reporter_id: int,
        reporter: str,
        guild_id: int,
        guild_name: str,
        console_ok: bool = False,
    ) -> int:
        """Persist a bug/crash report and return its auto-incremented ID."""
        with self._conn() as c:
            cur = c.execute(
                """
                INSERT INTO dev_bug_reports
                    (report_type, title, description, reporter_id, reporter, guild_id, guild_name, console_ok)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_type, title, description, str(reporter_id), reporter,
                 str(guild_id), guild_name, int(console_ok))
            )
            c.commit()
            return cur.lastrowid

    def get_channel(self, key: str) -> Optional[int]:
        with self._conn() as c:
            row = c.execute("SELECT channel_id FROM dev_log_channels WHERE key=?", (key,)).fetchone()
        return int(row["channel_id"]) if row else None

    def set_channel(self, key: str, channel_id: int) -> None:
        with self._conn() as c:
            c.execute("""
                INSERT INTO dev_log_channels (key, channel_id) VALUES (?,?)
                ON CONFLICT(key) DO UPDATE SET channel_id=excluded.channel_id
            """, (key, str(channel_id)))
            c.commit()

    def get_all(self) -> Dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT key, channel_id FROM dev_log_channels").fetchall()
        return {r["key"]: int(r["channel_id"]) for r in rows}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guild_footer(guild: discord.Guild) -> str:
    return f"{guild.name} · {guild.id}"


MEMBERS_PER_PAGE = 20

def _build_members_embeds(guild: discord.Guild) -> List[discord.Embed]:
    members = sorted(guild.members, key=lambda m: m.display_name.lower())
    total = len(members)
    chunks = [members[i:i + MEMBERS_PER_PAGE] for i in range(0, total, MEMBERS_PER_PAGE)]
    if not chunks:
        return [embed_info(f"👥 {guild.name} — Members", "No members found in guild.")]

    pages = []
    total_pages = len(chunks)
    for idx, chunk in enumerate(chunks):
        lines = []
        for m in chunk:
            bot_badge = " `[BOT]`" if m.bot else ""
            lines.append(f"• **{m.display_name}**{bot_badge} ({m.mention})")

        e = discord.Embed(
            title=f"👥 {guild.name} — Member Directory",
            description="\n".join(lines),
            color=C.BRAND
        )
        e.set_footer(text=f"Page {idx+1}/{total_pages} · {total:,} total members · {guild.name}")
        pages.append(e)
    return pages


# ---------------------------------------------------------------------------
# Global Auto-Error Reporting & Console Logging System
# ---------------------------------------------------------------------------

_recent_errors: Dict[str, float] = {}

def _is_rate_limited(key: str, window_seconds: float = 8.0) -> bool:
    """Throttle duplicate identical errors within a time window."""
    now = time.time()
    last = _recent_errors.get(key, 0.0)
    if now - last < window_seconds:
        return True
    _recent_errors[key] = now
    if len(_recent_errors) > 200:
        for k in list(_recent_errors.keys()):
            if now - _recent_errors[k] > 60.0:
                _recent_errors.pop(k, None)
    return False


def _safe_print(text: str) -> None:
    """Print text safely across Windows (cp1252) and Linux consoles without UnicodeEncodeError."""
    try:
        print(text)
    except (UnicodeEncodeError, UnicodeError):
        try:
            encoding = getattr(sys.stdout, "encoding", None) or "ascii"
            clean = text.encode(encoding, errors="backslashreplace").decode(encoding)
            print(clean)
        except Exception:
            clean = text.encode("ascii", errors="replace").decode("ascii")
            print(clean)


def send_console_sync(
    report_type: str,
    title: str,
    description: str,
    reporter: str,
    reporter_id: int | str,
    guild_name: str,
    guild_id: int | str,
    report_id: int,
) -> bool:
    """Synchronous HTTP POST to remote console for fatal crashes or non-async contexts."""
    payload = {
        "type":        report_type,
        "id":          report_id,
        "title":       title,
        "description": description,
        "reporter":    str(reporter),
        "reporter_id": str(reporter_id),
        "guild":       str(guild_name),
        "guild_id":    str(guild_id),
        "timestamp":   datetime.datetime.utcnow().isoformat() + "Z",
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            CONSOLE_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "GKR-Bot-CrashReporter/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status < 300
    except Exception as exc:
        _safe_print(f"[DevLogs] Sync console POST failed ({CONSOLE_URL}): {exc}")
        return False


async def auto_report_error(
    bot: Optional[commands.Bot],
    category: str,
    title: str,
    error_details: str,
    guild_name: str = "System",
    guild_id: int = 0,
    reporter: str = "GKR Auto-Detector",
    reporter_id: int = 0,
) -> int:
    """
    Unified auto error reporter:
    1. Prints rich, detailed error information to console.
    2. Logs into dev_bug_reports SQLite table.
    3. Sends JSON payload to hosted console (http://89.106.84.82:2011/api/report).
    4. Forwards an embed to the #dev-bug-reports channel in DEV_GUILD_ID.
    """
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    err_key = f"{category}:{title}:{error_details[:100]}"
    throttled = _is_rate_limited(err_key, window_seconds=8.0)

    # 1. Prominent Console Details Output
    border = "=" * 80
    sub_border = "-" * 80
    _safe_print(f"\n{border}")
    _safe_print(f"🚨 [GKR ERROR DETECTED: {category.upper()}]")
    _safe_print(f"⏰ Time:        {now_str}")
    _safe_print(f"🏷️  Category:    {category}")
    _safe_print(f"📌 Title:       {title}")
    _safe_print(f"🌐 Origin:      {guild_name} (ID: {guild_id})")
    _safe_print(f"👤 Reporter:    {reporter} (ID: {reporter_id})")
    if throttled:
        _safe_print("⚡ Throttled:   Identical error received within 8s — suppressing duplicate forward alerts.")
    _safe_print(sub_border)
    _safe_print("📋 Traceback / Error Details:")
    _safe_print(error_details.strip())
    _safe_print(f"{border}\n")

    if throttled:
        return 0

    # 2. Persist to DB
    db = DevLogsDB()
    report_id = 0
    try:
        report_id = db.log_report(
            report_type=category.lower(),
            title=title[:250],
            description=error_details,
            reporter_id=reporter_id,
            reporter=reporter,
            guild_id=guild_id,
            guild_name=guild_name,
            console_ok=False,
        )
    except Exception as e:
        _safe_print(f"[DevLogs] DB write failed: {e}")

    # 3. Remote Console POST
    console_ok = False
    try:
        payload = {
            "type":        category.lower(),
            "id":          report_id,
            "title":       title,
            "description": error_details,
            "reporter":    str(reporter),
            "reporter_id": str(reporter_id),
            "guild":       str(guild_name),
            "guild_id":    str(guild_id),
            "timestamp":   datetime.datetime.utcnow().isoformat() + "Z",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                CONSOLE_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                console_ok = resp.status < 300
    except Exception as exc:
        _safe_print(f"[DevLogs] Console POST failed ({CONSOLE_URL}): {exc}")

    if console_ok and report_id > 0:
        try:
            with db._conn() as c:
                c.execute("UPDATE dev_bug_reports SET console_ok=1 WHERE id=?", (report_id,))
                c.commit()
        except Exception:
            pass

    # 4. Forward embed to #dev-bug-reports channel
    if bot:
        cog = bot.get_cog("DevLogsCog")
        if cog and hasattr(cog, "_forward"):
            tb_display = error_details[:1000] + "\n…" if len(error_details) > 1000 else error_details
            embed = discord.Embed(
                title=f"🚨  Auto Error: {category[:200]}",
                color=0xED4245,
                timestamp=datetime.datetime.utcnow(),
            )
            embed.add_field(name="Report ID", value=f"`#{report_id}`" if report_id else "`N/A`", inline=True)
            embed.add_field(name="Origin", value=f"`{guild_name}`", inline=True)
            embed.add_field(name="Console", value="✅ Forwarded" if console_ok else "⚠️ Offline (saved locally)", inline=True)
            embed.add_field(name="Title", value=title[:256], inline=False)
            embed.add_field(name="Traceback / Details", value=f"```py\n{tb_display}\n```", inline=False)
            embed.set_footer(text=f"{reporter} · GKR Auto-Detector")
            try:
                await cog._forward("error_logs", embed)
            except Exception as forward_exc:
                _safe_print(f"[DevLogs] Failed to forward auto error embed: {forward_exc}")

    return report_id


def dispatch_auto_report(
    bot: Optional[commands.Bot],
    category: str,
    title: str,
    error_details: str,
    guild_name: str = "System",
    guild_id: int = 0,
    reporter: str = "GKR Auto-Detector",
    reporter_id: int = 0,
) -> None:
    """Safe sync dispatcher: schedules async task if loop is active, otherwise falls back to sync."""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.create_task(auto_report_error(
                bot=bot,
                category=category,
                title=title,
                error_details=error_details,
                guild_name=guild_name,
                guild_id=guild_id,
                reporter=reporter,
                reporter_id=reporter_id,
            ))
            return
    except RuntimeError:
        pass

    # Synchronous crash handling fallback
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    border = "=" * 80
    sub_border = "-" * 80
    _safe_print(f"\n{border}")
    _safe_print(f"🚨 [GKR UNCAUGHT CRASH: {category.upper()}]")
    _safe_print(f"⏰ Time:        {now_str}")
    _safe_print(f"🏷️  Category:    {category}")
    _safe_print(f"📌 Title:       {title}")
    _safe_print(f"🌐 Origin:      {guild_name} (ID: {guild_id})")
    _safe_print(f"👤 Reporter:    {reporter} (ID: {reporter_id})")
    _safe_print(sub_border)
    _safe_print("📋 Traceback:")
    _safe_print(error_details.strip())
    _safe_print(f"{border}\n")

    db = DevLogsDB()
    report_id = 0
    try:
        report_id = db.log_report(
            report_type=category.lower(),
            title=title[:250],
            description=error_details,
            reporter_id=reporter_id,
            reporter=reporter,
            guild_id=guild_id,
            guild_name=guild_name,
            console_ok=False,
        )
    except Exception as e:
        print(f"[DevLogs] DB write failed in sync crash fallback: {e}")

    ok = send_console_sync(
        report_type=category.lower(),
        title=title,
        description=error_details,
        reporter=reporter,
        reporter_id=reporter_id,
        guild_name=guild_name,
        guild_id=guild_id,
        report_id=report_id,
    )
    if ok and report_id > 0:
        try:
            with db._conn() as c:
                c.execute("UPDATE dev_bug_reports SET console_ok=1 WHERE id=?", (report_id,))
                c.commit()
        except Exception:
            pass


def setup_global_error_handlers(bot: commands.Bot, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """
    Installs comprehensive, multi-layer error interception across the bot:
    1. sys.excepthook for synchronous uncaught exceptions
    2. threading.excepthook for uncaught background thread exceptions
    3. bot.on_error for unhandled Discord event errors
    4. bot.tree.error for unhandled slash command errors
    5. bot.on_command_error for prefix command errors
    6. loop.set_exception_handler for unhandled async rejections in the event loop
    """

    # 1. Uncaught synchronous exceptions (Main thread)
    original_excepthook = sys.excepthook

    def sync_excepthook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            original_excepthook(exc_type, exc_value, exc_traceback)
            return
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        title = f"Uncaught Exception: {exc_type.__name__}: {exc_value}"
        dispatch_auto_report(
            bot=bot,
            category="Uncaught Exception",
            title=title,
            error_details=tb,
            guild_name="Main Process",
        )
        original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = sync_excepthook

    # 2. Uncaught thread exceptions (Background threads, HTTP server, etc.)
    if hasattr(threading, "excepthook"):
        def thread_excepthook(args):
            if issubclass(args.exc_type, KeyboardInterrupt):
                return
            tb = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
            thread_name = getattr(args.thread, "name", "Thread")
            title = f"Uncaught Thread Error in {thread_name}: {args.exc_type.__name__}: {args.exc_value}"
            dispatch_auto_report(
                bot=bot,
                category="Thread Crash",
                title=title,
                error_details=tb,
                guild_name=f"Thread: {thread_name}",
            )

        threading.excepthook = thread_excepthook

    # 3. Discord Event Errors (on_message, on_member_join, etc.)
    @bot.event
    async def on_error(event_method: str, *args, **kwargs):
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb)) if exc_type else "No traceback available"
        exc_name = exc_type.__name__ if exc_type else "Error"
        title = f"Event on_{event_method} Error: {exc_name}: {exc_value}"

        guild_name = "Discord Event"
        guild_id = 0
        if args and len(args) > 0:
            first_arg = args[0]
            if hasattr(first_arg, "guild") and first_arg.guild:
                guild_name = first_arg.guild.name
                guild_id = first_arg.guild.id
            elif isinstance(first_arg, discord.Guild):
                guild_name = first_arg.name
                guild_id = first_arg.id

        await auto_report_error(
            bot=bot,
            category="Discord Event Error",
            title=title,
            error_details=tb,
            guild_name=guild_name,
            guild_id=guild_id,
        )

    # 4. Slash / App Command Errors
    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        orig = getattr(error, "original", error)
        # Suppress normal user permission / cooldown notifications from filing bug reports
        if isinstance(orig, (app_commands.CommandOnCooldown, app_commands.CheckFailure)):
            msg = f"⏳ {orig}" if isinstance(orig, app_commands.CommandOnCooldown) else f"⛔ {orig}"
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                pass
            return

        tb = "".join(traceback.format_exception(type(orig), orig, orig.__traceback__))
        cmd_name = interaction.command.name if interaction.command else "unknown"
        title = f"Slash Command Error: /{cmd_name} ({type(orig).__name__}: {orig})"

        guild_name = interaction.guild.name if interaction.guild else "Direct Message"
        guild_id = interaction.guild_id or 0
        user_name = str(interaction.user)
        user_id = interaction.user.id

        await auto_report_error(
            bot=bot,
            category="Slash Command Error",
            title=title,
            error_details=tb,
            guild_name=guild_name,
            guild_id=guild_id,
            reporter=user_name,
            reporter_id=user_id,
        )

        err_msg = "❌ An unexpected error occurred while executing this command. The developers have been automatically notified."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(err_msg, ephemeral=True)
            else:
                await interaction.response.send_message(err_msg, ephemeral=True)
        except Exception:
            pass

    # 5. Prefix Command Errors
    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, (commands.CommandNotFound, commands.CommandOnCooldown, commands.CheckFailure)):
            return

        orig = getattr(error, "original", error)
        tb = "".join(traceback.format_exception(type(orig), orig, orig.__traceback__))
        cmd_name = ctx.command.name if ctx.command else (ctx.invoked_with or "unknown")
        title = f"Prefix Command Error: !{cmd_name} ({type(orig).__name__}: {orig})"

        guild_name = ctx.guild.name if ctx.guild else "Direct Message"
        guild_id = ctx.guild.id if ctx.guild else 0
        user_name = str(ctx.author)
        user_id = ctx.author.id

        await auto_report_error(
            bot=bot,
            category="Prefix Command Error",
            title=title,
            error_details=tb,
            guild_name=guild_name,
            guild_id=guild_id,
            reporter=user_name,
            reporter_id=user_id,
        )

    # 6. Event Loop Unhandled Exception Handler
    if loop:
        register_async_exception_handler(loop, bot)

    print("🛡️  Global Error Handlers & Unhandled Rejection Watcher installed!")


def register_async_exception_handler(loop: asyncio.AbstractEventLoop, bot: Optional[commands.Bot] = None) -> None:
    """Registers an unhandled rejection / exception handler on the specified asyncio event loop."""
    default_handler = loop.get_exception_handler()

    def async_exception_handler(current_loop: asyncio.AbstractEventLoop, context: dict):
        msg = context.get("message", "Unhandled exception in asyncio loop")
        exc = context.get("exception")

        if exc:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            title = f"Unhandled Async Rejection: {type(exc).__name__}: {exc}"
        else:
            tb = f"Message: {msg}\nContext: {context}"
            title = f"Unhandled Async Rejection: {msg}"

        dispatch_auto_report(
            bot=bot,
            category="Unhandled Async Rejection",
            title=title,
            error_details=tb,
            guild_name="Async Event Loop",
        )

        if default_handler:
            default_handler(current_loop, context)
        else:
            current_loop.default_exception_handler(context)

    loop.set_exception_handler(async_exception_handler)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class DevLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DevLogsDB()

    async def cog_load(self) -> None:
        if DEV_GUILD_ID:
            dev_guild_obj = discord.Object(id=DEV_GUILD_ID)
            self.bot.tree.add_command(self.dev_group, guild=dev_guild_obj)
        try:
            loop = asyncio.get_running_loop()
            register_async_exception_handler(loop, self.bot)
        except Exception as e:
            pass

    async def cog_unload(self) -> None:
        if DEV_GUILD_ID:
            dev_guild_obj = discord.Object(id=DEV_GUILD_ID)
            self.bot.tree.remove_command("dev", guild=dev_guild_obj)

    async def _forward(self, key: str, embed: discord.Embed) -> None:
        # 1. Check environment variable override for errors & crashes
        channel_id = None
        if key in ("error_logs", "bug_reports"):
            env_id = os.getenv("ERROR_LOG_CHANNEL_ID") or os.getenv("CRASH_LOG_CHANNEL_ID") or os.getenv("DEV_ERROR_CHANNEL_ID")
            if env_id:
                try:
                    channel_id = int(env_id)
                except ValueError:
                    pass

        # 2. Check DB mapping
        if not channel_id:
            channel_id = self.db.get_channel(key)
            if not channel_id and key == "error_logs":
                channel_id = self.db.get_channel("bug_reports")
            elif not channel_id and key == "bug_reports":
                channel_id = self.db.get_channel("error_logs")

        # 3. Locate target guild
        target_guild = None
        if DEV_GUILD_ID:
            target_guild = self.bot.get_guild(DEV_GUILD_ID)
        if not target_guild:
            default_gid = int(os.getenv("DISCORD_GUILD_ID", "0"))
            if default_gid:
                target_guild = self.bot.get_guild(default_gid)

        channel = None
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    channel = None

        # 4. Fallback: Search target guild text channels by known names
        if not channel and target_guild:
            if key in ("error_logs", "bug_reports"):
                search_names = ["dev-error-and-crashes", "dev-error-logs", "error-and-crashes", "error-logs", "dev-bug-reports", "crash-logs"]
                for ch in target_guild.text_channels:
                    if ch.name in search_names:
                        channel = ch
                        self.db.set_channel("error_logs", ch.id)
                        self.db.set_channel("bug_reports", ch.id)
                        break

        # 5. Auto-provision channel in dev guild if missing
        if not channel and target_guild and key in ("error_logs", "bug_reports"):
            try:
                overwrites = {
                    target_guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    target_guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        embed_links=True,
                        attach_files=True,
                        read_message_history=True,
                    ),
                }
                category = discord.utils.get(target_guild.categories, name="🔧 Dev Logs")
                if not category:
                    category = await target_guild.create_category(
                        "🔧 Dev Logs",
                        overwrites=overwrites,
                        reason="GKR Dev Logs (Private: Hidden from @everyone)"
                    )
                else:
                    try:
                        await category.set_permissions(target_guild.default_role, view_channel=False)
                    except Exception:
                        pass
                channel = await target_guild.create_text_channel(
                    "dev-error-and-crashes",
                    category=category,
                    topic="🚨 Unhandled errors, crashes, and exceptions across all servers",
                    overwrites=overwrites,
                    reason="GKR Error & Crash Log (Private: Hidden from @everyone)"
                )
                self.db.set_channel("error_logs", channel.id)
                self.db.set_channel("bug_reports", channel.id)
                _safe_print(f"[DevLogs] Auto-created private #{channel.name} ({channel.id}) for crash/error logging!")
            except Exception as e:
                _safe_print(f"[DevLogs] Failed to auto-provision error channel: {e}")

        # 6. Send the embed
        if channel and isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except Exception as exc:
                _safe_print(f"[DevLogs] Failed to forward to #{channel.name}: {exc}")

    # ── Dev Command Group (Guild Only) ─────────────────────────────────────────

    dev_group = app_commands.Group(
        name="dev",
        description="[Developer Only] Global bot management commands",
    )

    @dev_group.command(name="set_error_channel", description="Set the dedicated channel for error and crash logs")
    @app_commands.describe(channel="The Discord channel where error and crash embeds will be posted")
    async def set_error_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Assign any text channel as the dedicated error and crash log channel."""
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("This command can only be used in the developer guild."), ephemeral=True)
            return

        self.db.set_channel("error_logs", channel.id)
        self.db.set_channel("bug_reports", channel.id)
        embed = embed_success(
            "Error & Crash Channel Configured",
            f"All unhandled errors, async rejections, and bot crashes will now automatically post to {channel.mention} (`#{channel.name}`)."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev_group.command(name="setup_logs", description="Create or configure the global dev log channels")
    async def setup_logs(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("This command can only be used in the developer guild."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # Build private overwrites: @everyone CANNOT view, bot and command runner can view
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }
        if interaction.user and isinstance(interaction.user, discord.Member):
            overwrites[interaction.user] = discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
            )

        category = discord.utils.get(guild.categories, name="🔧 Dev Logs")
        if not category:
            category = await guild.create_category(
                "🔧 Dev Logs",
                overwrites=overwrites,
                reason="GKR Dev Logs (Private: Hidden from @everyone)"
            )
        else:
            # Enforce private permissions on existing category
            try:
                await category.set_permissions(guild.default_role, view_channel=False, reason="Hide Dev Logs from @everyone")
                await category.set_permissions(
                    guild.me,
                    view_channel=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                )
                if interaction.user and isinstance(interaction.user, discord.Member):
                    await category.set_permissions(interaction.user, view_channel=True, read_message_history=True)
            except Exception as perm_err:
                _safe_print(f"[DevLogs] Warning: Could not update category permissions: {perm_err}")

        created, existing_list = [], []
        for key, ch_name, topic in DEV_LOG_CHANNELS:
            target_ch = None

            # 1. Check if we already have an ID in the DB
            existing_id = self.db.get_channel(key)
            if existing_id:
                target_ch = guild.get_channel(existing_id)

            # 2. If not found by ID, search under category or guild by name
            if not target_ch:
                target_ch = discord.utils.get(category.text_channels, name=ch_name)
                if not target_ch:
                    target_ch = discord.utils.get(guild.text_channels, name=ch_name)

            # 3. If found, sync DB and preserve without duplicating
            if target_ch:
                self.db.set_channel(key, target_ch.id)
                try:
                    if target_ch.category_id != category.id:
                        await target_ch.edit(category=category, sync_permissions=True)
                    else:
                        await target_ch.set_permissions(guild.default_role, view_channel=False)
                except Exception:
                    pass
                existing_list.append(target_ch.name)
            else:
                # 4. If missing, create ONLY this missing channel (with private overwrites)
                ch = await guild.create_text_channel(
                    ch_name,
                    category=category,
                    topic=topic,
                    overwrites=overwrites,
                    reason="GKR Dev Logs channel (Private: Hidden from @everyone)"
                )
                self.db.set_channel(key, ch.id)
                created.append(ch.name)

        desc_lines = []
        desc_lines.append("🔒 **Privacy:** Locked to `@everyone` (Private to Developers & Bot)")
        if created:
            desc_lines.append(f"\n**➕ Added Missing Channel{'s' if len(created) > 1 else ''}:**\n" + "\n".join(f"• `#{n}`" for n in created))
        if existing_list:
            desc_lines.append(f"\n**✅ Already Existing & Synced ({len(existing_list)}):**\n" + ", ".join(f"`#{n}`" for n in existing_list))

        embed = embed_success(
            "Dev Log Channels Synchronized",
            "\n".join(desc_lines)
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dev_group.command(name="status", description="Show all dev log channel assignments")
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("Developer only."), ephemeral=True)
            return

        mapping = self.db.get_all()
        lines = []
        for key, ch_name, desc in DEV_LOG_CHANNELS:
            ch_id = mapping.get(key)
            ch = (interaction.guild.get_channel(ch_id) or self.bot.get_channel(ch_id)) if ch_id else None
            status = ch.mention if ch else "`Not configured`"
            lines.append(f"• **{key}** (`#{ch_name}`): {status}")

        embed = embed_info("🔧  Dev Log Channels", "\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev_group.command(name="guilds", description="List all guilds the bot is currently in")
    async def list_guilds(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("Developer only."), ephemeral=True)
            return

        lines = [f"• **{g.name}** — `{g.member_count:,}` members" for g in self.bot.guilds]
        embed = embed_info(f"🌐  Active Guilds ({len(self.bot.guilds)})", "\n".join(lines[:25]))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev_group.command(name="members", description="View members of any guild the bot is in")
    @app_commands.describe(guild_id="The server ID to inspect")
    async def list_members(self, interaction: discord.Interaction, guild_id: str = "") -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("Developer only."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        if guild_id.strip():
            if not guild_id.strip().isdigit():
                await interaction.followup.send(embed=embed_error("Server ID must be a numeric integer."), ephemeral=True)
                return
            target_guild = self.bot.get_guild(int(guild_id.strip()))
            if not target_guild:
                await interaction.followup.send(embed=embed_error("Bot is not in that server or ID is invalid."), ephemeral=True)
                return
        else:
            target_guild = interaction.guild

        pages = _build_members_embeds(target_guild)
        view = Paginator(pages, interaction.user.id)
        await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

    # ── Bug / Crash Reporting ──────────────────────────────────────────────────

    async def _send_to_console(
        self,
        report_type: str,
        title: str,
        description: str,
        reporter: str,
        reporter_id: int,
        guild_name: str,
        guild_id: int,
        report_id: int,
    ) -> bool:
        """Forward the report as JSON to the hosted console at 89.106.84.82:2011."""
        payload = {
            "type":        report_type,
            "id":          report_id,
            "title":       title,
            "description": description,
            "reporter":    reporter,
            "reporter_id": str(reporter_id),
            "guild":       guild_name,
            "guild_id":    str(guild_id),
            "timestamp":   datetime.datetime.utcnow().isoformat() + "Z",
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    CONSOLE_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    return resp.status < 300
        except Exception as exc:
            print(f"[DevLogs] Console POST failed: {exc}")
            return False

    @dev_group.command(name="bugreport", description="🐛 Submit a bug report to the dev console and bug-reports channel")
    @app_commands.describe(
        title="Short title describing the bug",
        description="Detailed description of what went wrong",
    )
    async def bugreport(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
    ) -> None:
        """Submit a bug report — dev guild only."""
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(
                embed=embed_error("This command can only be used in the developer guild."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        report_id = self.db.log_report(
            report_type="bug",
            title=title,
            description=description,
            reporter_id=interaction.user.id,
            reporter=str(interaction.user),
            guild_id=interaction.guild_id,
            guild_name=interaction.guild.name,
        )

        console_ok = await self._send_to_console(
            "bug", title, description,
            str(interaction.user), interaction.user.id,
            interaction.guild.name, interaction.guild_id,
            report_id,
        )

        # Update console status in DB
        with self.db._conn() as c:
            c.execute("UPDATE dev_bug_reports SET console_ok=? WHERE id=?", (int(console_ok), report_id))
            c.commit()

        embed = discord.Embed(
            title="🐛  Bug Report Received",
            color=0xE67E22,
        )
        embed.add_field(name="Report ID",    value=f"`#{report_id}`",         inline=True)
        embed.add_field(name="Reporter",     value=interaction.user.mention,  inline=True)
        embed.add_field(name="Console",      value="✅ Forwarded" if console_ok else "⚠️ Offline (saved locally)", inline=True)
        embed.add_field(name="Title",        value=title[:256],               inline=False)
        embed.add_field(name="Description",  value=description[:1024],        inline=False)
        embed.set_footer(text=f"{interaction.guild.name} · {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

        await self._forward("bug_reports", embed)
        await interaction.followup.send(
            embed=embed_success(f"Bug report `#{report_id}` submitted!",
                                f"{'Console notified ✅' if console_ok else 'Console offline — saved locally ⚠️'}\nPosted to dev-bug-reports channel."),
            ephemeral=True,
        )

    @dev_group.command(name="crashreport", description="💥 Submit a crash report with traceback to the dev console")
    @app_commands.describe(
        title="Short crash description",
        traceback="Full error traceback or crash log (paste here)",
    )
    async def crashreport(
        self,
        interaction: discord.Interaction,
        title: str,
        traceback: str,
    ) -> None:
        """Submit a crash report — dev guild only."""
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(
                embed=embed_error("This command can only be used in the developer guild."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        report_id = self.db.log_report(
            report_type="crash",
            title=title,
            description=traceback,
            reporter_id=interaction.user.id,
            reporter=str(interaction.user),
            guild_id=interaction.guild_id,
            guild_name=interaction.guild.name,
        )

        console_ok = await self._send_to_console(
            "crash", title, traceback,
            str(interaction.user), interaction.user.id,
            interaction.guild.name, interaction.guild_id,
            report_id,
        )

        with self.db._conn() as c:
            c.execute("UPDATE dev_bug_reports SET console_ok=? WHERE id=?", (int(console_ok), report_id))
            c.commit()

        # Truncate for embed (max 1024 chars per field)
        tb_display = traceback[:1000] + "\n…" if len(traceback) > 1000 else traceback

        embed = discord.Embed(
            title="💥  Crash Report",
            color=0xE74C3C,
        )
        embed.add_field(name="Report ID",   value=f"`#{report_id}`",         inline=True)
        embed.add_field(name="Reporter",    value=interaction.user.mention,  inline=True)
        embed.add_field(name="Console",     value="✅ Forwarded" if console_ok else "⚠️ Offline (saved locally)", inline=True)
        embed.add_field(name="Title",       value=title[:256],               inline=False)
        embed.add_field(name="Traceback",   value=f"```\n{tb_display}\n```",  inline=False)
        embed.set_footer(text=f"{interaction.guild.name} · {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

        await self._forward("bug_reports", embed)
        await interaction.followup.send(
            embed=embed_success(f"Crash report `#{report_id}` submitted!",
                                f"{'Console notified ✅' if console_ok else 'Console offline — saved locally ⚠️'}\nPosted to dev-bug-reports channel."),
            ephemeral=True,
        )

    @dev_group.command(name="reports", description="📋 View recent bug and crash reports")
    @app_commands.describe(limit="Number of recent reports to show (default 10)")
    async def view_reports(
        self,
        interaction: discord.Interaction,
        limit: Optional[int] = 10,
    ) -> None:
        """List recent reports — dev guild only."""
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(
                embed=embed_error("Developer only."),
                ephemeral=True,
            )
            return

        limit = max(1, min(limit or 10, 25))
        with self.db._conn() as c:
            rows = c.execute(
                "SELECT id, report_type, title, reporter, console_ok, created_at "
                "FROM dev_bug_reports ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()

        if not rows:
            await interaction.response.send_message(
                embed=embed_info("📋 No Reports", "No bug or crash reports have been submitted yet."),
                ephemeral=True,
            )
            return

        lines = []
        for r in rows:
            icon = "💥" if r["report_type"] == "crash" else "🐛"
            ok   = "✅" if r["console_ok"] else "⚠️"
            lines.append(f"{icon} `#{r['id']}` **{r['title'][:40]}** — {r['reporter']} {ok} `{r['created_at'][:16]}`")

        embed = embed_info(f"📋  Last {len(rows)} Reports", "\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)


    # ── Global Event Forwarders ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="📥 Member joined",
            subject=member.mention,
            details=[f"Account created {fmt_rel(member.created_at)}", f"Member #{member.guild.member_count:,}"],
            color=C.SUCCESS,
            thumbnail_url=member.display_avatar.url,
            footer_text=_guild_footer(member.guild)
        )
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="📤 Member left",
            subject=member.mention,
            color=C.DANGER,
            thumbnail_url=member.display_avatar.url,
            footer_text=_guild_footer(member.guild)
        )
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="🔨 Member banned",
            subject=user.mention,
            color=C.DANGER,
            thumbnail_url=user.display_avatar.url,
            footer_text=_guild_footer(guild)
        )
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        if role.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="🎭 Role created",
            subject=role.mention,
            details=[f"Color #{role.color.value:06x}"],
            color=C.PURPLE,
            footer_text=_guild_footer(role.guild)
        )
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if role.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="🗑️ Role deleted",
            subject=f"@{role.name}",
            color=C.DANGER,
            footer_text=_guild_footer(role.guild)
        )
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.guild.id == DEV_GUILD_ID:
            return
        added = [r for r in after.roles if r not in before.roles and r.name != "@everyone"]
        removed = [r for r in before.roles if r not in after.roles and r.name != "@everyone"]
        if not added and not removed:
            return

        details = [f"+ {r.mention}" for r in added] + [f"- {r.mention}" for r in removed]
        embed = create_audit_embed(
            title="🎭 Member roles updated",
            subject=after.mention,
            details=details,
            color=C.PURPLE,
            thumbnail_url=after.display_avatar.url,
            footer_text=_guild_footer(after.guild)
        )
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.guild.id == DEV_GUILD_ID or message.author.bot:
            return
        content = f"> {message.content[:500]}" if message.content else "*[No text content]*"
        embed = create_audit_embed(
            title="🗑️ Message deleted",
            subject=f"#{message.channel.name}",
            actor=message.author,
            details=[content],
            color=C.DANGER,
            thumbnail_url=message.author.display_avatar.url,
            footer_text=_guild_footer(message.guild)
        )
        await self._forward("message_logs", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.guild.id == DEV_GUILD_ID or before.author.bot or before.content == after.content:
            return
        embed = create_audit_embed(
            title="📝 Message edited",
            subject=f"#{after.channel.name}",
            actor=after.author,
            changes=[("Content", before.content[:200], after.content[:200])],
            color=C.WARNING,
            thumbnail_url=after.author.display_avatar.url,
            footer_text=_guild_footer(before.guild)
        )
        await self._forward("message_logs", embed)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command) -> None:
        if not interaction.guild or interaction.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="⌨️ Command used",
            subject=f"/{command.qualified_name}",
            actor=interaction.user,
            details=[f"Channel: {interaction.channel.mention if interaction.channel else 'N/A'}"],
            color=C.BRAND,
            thumbnail_url=interaction.user.display_avatar.url if interaction.user else None,
            footer_text=_guild_footer(interaction.guild)
        )
        await self._forward("command_logs", embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if not invite.guild or invite.guild.id == DEV_GUILD_ID:
            return
        details = [f"Channel: {invite.channel.mention if invite.channel else 'N/A'}", f"Max uses: {invite.max_uses or '∞'}"]
        embed = create_audit_embed(
            title="🔗 Invite created",
            subject=f"discord.gg/{invite.code}",
            actor=invite.inviter,
            details=details,
            color=C.CYAN,
            footer_text=_guild_footer(invite.guild)
        )
        await self._forward("invite_logs", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="➕ Channel created",
            subject=channel.mention if hasattr(channel, "mention") else f"#{channel.name}",
            details=[f"Type: {channel.type}"],
            color=C.SUCCESS,
            footer_text=_guild_footer(channel.guild)
        )
        await self._forward("server_events", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="➖ Channel deleted",
            subject=f"#{channel.name}",
            details=[f"Type: {channel.type}"],
            color=C.DANGER,
            footer_text=_guild_footer(channel.guild)
        )
        await self._forward("server_events", embed)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if after.id == DEV_GUILD_ID or before.name == after.name:
            return
        embed = create_audit_embed(
            title="⚙️ Server renamed",
            subject=after.name,
            changes=[("Name", before.name, after.name)],
            color=C.BRAND,
            footer_text=_guild_footer(after)
        )
        await self._forward("server_events", embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DevLogsCog(bot))
    print("🔧 Dev Global Logs loaded!")
