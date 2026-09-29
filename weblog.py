"""
weblog.py — posts an audit log entry to a Discord channel every time someone
takes an action through the WEBSITE dashboard (blacklist changes, Dev News
posts/deletes, bot banner changes, and any future admin-panel action that
calls `post_weblog()`).

Setup mirrors dev_global_logs.py: `/weblog setup` is registered ONLY on the
dev guild's command tree (BLACKLIST_DEV_GUILD_ID) — it never shows up
anywhere else, no owner-id check needed. Each log category gets its own
small-caps text channel, auto-created (and private: hidden from @everyone)
under one "weblog" category folder on first use.

Add "weblog" to the `extensions` list in main.py.
"""
import asyncio
import os
import sqlite3
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = Path(__file__).resolve().parent / "weblog.sqlite3"
DEV_GUILD_ID = os.getenv("BLACKLIST_DEV_GUILD_ID", "").strip()
_DEV_GUILD = int(DEV_GUILD_ID) if DEV_GUILD_ID.isdigit() else None

CATEGORY_FOLDER_NAME = "🔧 Weblog"
DEFAULT_CATEGORY = "general"

# Known log categories, created upfront by /weblog setup. New categories
# used only via post_weblog(category=...) still auto-create on first use.
KNOWN_CATEGORIES = [
    "auth",
    "welcome",
    "tickets",
    "music",
    "radio",
    "security",
    "custom_commands",
    "blacklist",
    "devnews",
    "banner",
    "admin",
    "general",
]

_SMALL_CAPS = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ",
)


def small_caps(text: str) -> str:
    """'Website Action' -> 'ᴡᴇʙsɪᴛᴇ ᴀᴄᴛɪᴏɴ'. Digits/punctuation pass through."""
    return (text or "").lower().translate(_SMALL_CAPS)


def _channel_name_for_category(category: str) -> str:
    """'bot_banner' -> 'ʙᴏᴛ-ʙᴀɴɴᴇʀ' (Discord-safe: small caps, hyphenated)."""
    cleaned = (category or DEFAULT_CATEGORY).strip().lower().replace("_", " ").replace(" ", "-")
    return small_caps(cleaned)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS weblog_channels (category TEXT PRIMARY KEY, channel_id INTEGER NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS weblog_meta (id INTEGER PRIMARY KEY CHECK (id = 1), category_channel_id INTEGER, guild_id INTEGER)"
        )
        try:
            conn.execute("ALTER TABLE weblog_meta ADD COLUMN guild_id INTEGER")
        except Exception:
            pass
        conn.execute(
            """CREATE TABLE IF NOT EXISTS weblog_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                action TEXT NOT NULL,
                actor_id TEXT,
                actor_name TEXT,
                category TEXT NOT NULL,
                details TEXT,
                guild_id TEXT,
                guild_name TEXT,
                color INTEGER
            )"""
        )
        conn.commit()


_init_db()


def _get_target_guild_id() -> Optional[int]:
    if _DEV_GUILD:
        return _DEV_GUILD
    with _connect() as conn:
        row = conn.execute("SELECT guild_id FROM weblog_meta WHERE id = 1").fetchone()
        if row and row["guild_id"]:
            return int(row["guild_id"])
    return None


def _save_target_guild_id(guild_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO weblog_meta (id, guild_id) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET guild_id = excluded.guild_id",
            (guild_id,),
        )
        conn.commit()


def _get_channel_id(category: str) -> Optional[int]:
    with _connect() as conn:
        row = conn.execute("SELECT channel_id FROM weblog_channels WHERE category = ?", (category,)).fetchone()
    return row["channel_id"] if row else None


def _save_channel_id(category: str, channel_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO weblog_channels (category, channel_id) VALUES (?, ?) "
            "ON CONFLICT(category) DO UPDATE SET channel_id = excluded.channel_id",
            (category, channel_id),
        )
        conn.commit()


def _get_category_channel_id() -> Optional[int]:
    with _connect() as conn:
        row = conn.execute("SELECT category_channel_id FROM weblog_meta WHERE id = 1").fetchone()
    return row["category_channel_id"] if row and row["category_channel_id"] else None


def _save_category_channel_id(channel_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO weblog_meta (id, category_channel_id) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET category_channel_id = excluded.category_channel_id",
            (channel_id,),
        )
        conn.commit()
        conn.commit()


def _private_overwrites(guild: discord.Guild) -> dict:
    """@everyone can't see weblog channels; the bot can post in them."""
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, embed_links=True, read_message_history=True,
        ),
    }


# Bot-wide reference set once the cog loads, so post_weblog() can be called
# from any other module (blacklist_api.py, devnews_api.py, admin_api.py, ...)
# without each of them needing their own copy of the bot instance.
_bot_ref: Optional[commands.Bot] = None

# Per-category locks so two concurrent post_weblog() calls for a brand-new
# category can't both pass the "does it exist" check and create duplicates.
_category_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def _get_lock(category: str) -> asyncio.Lock:
    async with _locks_guard:
        lock = _category_locks.get(category)
        if lock is None:
            lock = asyncio.Lock()
            _category_locks[category] = lock
        return lock


async def _ensure_category_channel(guild: discord.Guild) -> Optional[discord.CategoryChannel]:
    """Find or create the shared category (folder) that holds all weblog channels."""
    cat_id = _get_category_channel_id()
    if cat_id:
        cat = guild.get_channel(cat_id)
        if isinstance(cat, discord.CategoryChannel):
            return cat

    existing = discord.utils.get(guild.categories, name=CATEGORY_FOLDER_NAME)
    if existing:
        _save_category_channel_id(existing.id)
        return existing

    if not guild.me.guild_permissions.manage_channels:
        print("[Weblog] Missing Manage Channels permission; can't auto-create the log category.")
        return None

    try:
        cat = await guild.create_category(
            CATEGORY_FOLDER_NAME,
            overwrites=_private_overwrites(guild),
            reason="Weblog: auto-provision log category",
        )
        _save_category_channel_id(cat.id)
        return cat
    except discord.HTTPException as e:
        print(f"[Weblog] Failed to create log category: {e}")
        return None


async def _ensure_channel_for_category(guild: discord.Guild, category: str) -> Optional[discord.TextChannel]:
    """Find or create the text channel for this log category, under the shared folder."""
    channel_id = _get_channel_id(category)
    if channel_id:
        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await guild.fetch_channel(channel_id)
            except Exception:
                channel = None
        if isinstance(channel, discord.TextChannel):
            return channel

    lock = await _get_lock(category)
    async with lock:
        # re-check after acquiring the lock in case another call just created it
        channel_id = _get_channel_id(category)
        if channel_id:
            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                return channel

        parent = await _ensure_category_channel(guild)

        name = _channel_name_for_category(category)
        found = discord.utils.get(parent.text_channels, name=name) if parent else discord.utils.get(guild.text_channels, name=name)
        if found:
            _save_channel_id(category, found.id)
            return found

        if not guild.me.guild_permissions.manage_channels:
            print("[Weblog] Missing Manage Channels permission; can't auto-create log channels.")
            return None

        try:
            channel = await guild.create_text_channel(
                name,
                category=parent,
                overwrites=_private_overwrites(guild),
                reason=f"Weblog: auto-provision '{category}' log channel",
            )
            _save_channel_id(category, channel.id)
            return channel
        except discord.HTTPException as e:
            print(f"[Weblog] Failed to create channel for category '{category}': {e}")
            return None


async def post_weblog(
    action: str,
    actor_label: str,
    details: str = "",
    color: int = 0x5865F2,
    category: str = DEFAULT_CATEGORY,
    actor_id: Optional[str | int] = None,
    guild_id: Optional[str | int] = None,
    guild_name: Optional[str] = None,
) -> bool:
    """Post one audit-log entry for a website-triggered action and persist it to SQLite.

    action       e.g. "Server Blacklisted", "Dev News Published", "User Signed In"
    actor_label  who did it, e.g. "User 123456789012345678" or an admin's name
    details      one or two lines of specifics (target, reason, etc.)
    category     which log category this belongs to: auth, welcome, tickets, radio, music, etc.
    """
    import time
    # 1. Always record in SQLite weblog_events so it appears on the web dashboard
    try:
        with _connect() as conn:
            conn.execute(
                """INSERT INTO weblog_events (timestamp, action, actor_id, actor_name, category, details, guild_id, guild_name, color)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(time.time()),
                    action,
                    str(actor_id) if actor_id else None,
                    str(actor_label) if actor_label else "Unknown",
                    category or DEFAULT_CATEGORY,
                    details or "",
                    str(guild_id) if guild_id else None,
                    guild_name or None,
                    color,
                ),
            )
            conn.commit()
    except Exception as e:
        print(f"[Weblog] Failed to persist event to SQLite: {e}")

    # 2. Also send Discord embed if target guild channel is available
    target_guild_id = _get_target_guild_id()
    if _bot_ref is None or target_guild_id is None:
        return True

    guild = _bot_ref.get_guild(target_guild_id)
    if guild is None:
        return True

    channel = await _ensure_channel_for_category(guild, category)
    if channel is None:
        return True

    embed = discord.Embed(
        title=small_caps(f"🌐 {action}"),
        description=details[:3500] if details else None,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name=small_caps("performed by"), value=actor_label or "Unknown", inline=False)
    if guild_name or guild_id:
        embed.add_field(name=small_caps("server"), value=f"{guild_name or 'Server'} (`{guild_id}`)", inline=True)
    embed.set_footer(text=small_caps("website audit log"))
    try:
        await channel.send(embed=embed)
        return True
    except Exception as e:
        print(f"[Weblog] Failed to post entry: {e}")
        return False


def get_weblog_events(
    limit: int = 150,
    category: Optional[str] = None,
    guild_id: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict]:
    """Retrieve audit log events from SQLite with filtering."""
    with _connect() as conn:
        query = "SELECT * FROM weblog_events WHERE 1=1"
        params = []
        if category and category != "all":
            query += " AND category = ?"
            params.append(category)
        if guild_id:
            query += " AND (guild_id = ? OR guild_id IS NULL)"
            params.append(str(guild_id))
        if search:
            query += " AND (action LIKE ? OR actor_name LIKE ? OR details LIKE ? OR guild_name LIKE ? OR actor_id LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term, term, term])
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(max(1, min(500, limit)))
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


class WeblogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        global _bot_ref
        _bot_ref = bot

    async def cog_load(self) -> None:
        if _DEV_GUILD:
            self.bot.tree.add_command(self.weblog_group, guild=discord.Object(id=_DEV_GUILD))
        # Register globally so /weblog setup can be run in any guild
        self.bot.tree.add_command(self.weblog_group)
        asyncio.create_task(self._startup_check())

    async def cog_unload(self) -> None:
        try:
            if _DEV_GUILD:
                self.bot.tree.remove_command("weblog", guild=discord.Object(id=_DEV_GUILD))
            self.bot.tree.remove_command("weblog")
        except Exception:
            pass

    async def _startup_check(self):
        await self.bot.wait_until_ready()
        target_guild_id = _get_target_guild_id()

        if target_guild_id is None:
            print("[Weblog] Loaded — waiting for /weblog setup to be run in a Discord server.")
            return

        guild = self.bot.get_guild(target_guild_id)
        if guild is None:
            print(f"[Weblog] Target guild {target_guild_id} not found in bot cache.")
            return

        if not guild.me.guild_permissions.manage_channels:
            print(f"[Weblog] Warning: missing Manage Channels permission in '{guild.name}'.")
            return

        print(f"[Weblog] Active and transmitting to Discord server '{guild.name}' ({guild.id}).")

    weblog_group = app_commands.Group(name="weblog", description="Website audit log configuration")

    @weblog_group.command(name="setup", description="Auto-provision Discord audit log channels for all website actions")
    async def weblog_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return await interaction.followup.send("❌ This command must be used in a Discord server.", ephemeral=True)

        if not guild.me.guild_permissions.manage_channels:
            return await interaction.followup.send(f"❌ I'm missing **Manage Channels** in {guild.name}.", ephemeral=True)

        _save_target_guild_id(guild.id)
        parent = await _ensure_category_channel(guild)
        if parent is None:
            return await interaction.followup.send("❌ Could not create/find the log category folder.", ephemeral=True)

        created, existing = [], []
        for cat in KNOWN_CATEGORIES:
            before = _get_channel_id(cat)
            ch = await _ensure_channel_for_category(guild, cat)
            if ch is None:
                continue
            (existing if before else created).append(ch)

        lines = [
            f"✅ **Website Audit Weblog Setup Complete!**",
            f"All website actions (sign-ins, welcome, tickets, music, radio, security, etc.) will now be posted live to **{guild.name}** under **{parent.name}**.",
        ]
        if created:
            lines.append("\n**Created channels:**\n" + "\n".join(f"• <#{c.id}> (`{c.name}`)" for c in created))
        if existing:
            lines.append("\n**Connected channels:**\n" + "\n".join(f"• <#{c.id}>" for c in existing))
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @weblog_group.command(name="test", description="Send a test audit log embed to verify Discord delivery")
    async def weblog_test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ok = await post_weblog(
            "Test Audit Log",
            actor_label=f"{interaction.user.name} ({interaction.user.id})",
            details="Testing Discord audit channel delivery from /weblog test command.",
            color=0x57F287,
            category="general",
            actor_id=str(interaction.user.id),
            guild_id=str(interaction.guild_id),
            guild_name=interaction.guild.name if interaction.guild else "",
        )
        if ok:
            await interaction.followup.send("✅ Test audit log successfully posted to Discord!", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Could not post to Discord. Run `/weblog setup` first in this server.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WeblogCog(bot))