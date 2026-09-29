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
            "CREATE TABLE IF NOT EXISTS weblog_meta (id INTEGER PRIMARY KEY CHECK (id = 1), category_channel_id INTEGER)"
        )
        conn.commit()


_init_db()


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
) -> bool:
    """Post one audit-log entry for a website-triggered action.

    action       e.g. "Server Blacklisted", "Dev News Published"
    actor_label  who did it, e.g. "User 123456789012345678" or an admin's name
    details      one or two lines of specifics (target, reason, etc.)
    category     which log channel this belongs to, e.g. "blacklist",
                 "devnews", "banner" — auto-creates a small-caps channel
                 named after this the first time it's used

    Returns False (and does nothing else) if the dev guild / bot ref isn't
    available, or the channel can't be found or created -- this must never
    raise and break the website action it's logging.
    """
    if _bot_ref is None or _DEV_GUILD is None:
        return False

    guild = _bot_ref.get_guild(_DEV_GUILD)
    if guild is None:
        return False

    channel = await _ensure_channel_for_category(guild, category)
    if channel is None:
        return False

    embed = discord.Embed(
        title=small_caps(f"🌐 {action}"),
        description=details[:3500] if details else None,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name=small_caps("performed by"), value=actor_label or "Unknown", inline=False)
    embed.set_footer(text=small_caps("website audit log"))
    try:
        await channel.send(embed=embed)
        return True
    except Exception as e:
        print(f"[Weblog] Failed to post entry: {e}")
        return False


class WeblogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        global _bot_ref
        _bot_ref = bot

    async def cog_load(self) -> None:
        if _DEV_GUILD:
            self.bot.tree.add_command(self.weblog_group, guild=discord.Object(id=_DEV_GUILD))
        asyncio.create_task(self._startup_check())

    async def cog_unload(self) -> None:
        if _DEV_GUILD:
            self.bot.tree.remove_command("weblog", guild=discord.Object(id=_DEV_GUILD))

    async def _startup_check(self):
        await self.bot.wait_until_ready()

        if _DEV_GUILD is None:
            print("[Weblog] NOT working: BLACKLIST_DEV_GUILD_ID env var missing or not numeric.")
            return

        guild = self.bot.get_guild(_DEV_GUILD)
        if guild is None:
            print(f"[Weblog] NOT working: bot is not in dev guild {_DEV_GUILD}.")
            return

        if not guild.me.guild_permissions.manage_channels:
            print(f"[Weblog] NOT working: missing Manage Channels permission in '{guild.name}'.")
            return

        print(f"[Weblog] loaded, working — dev guild '{guild.name}' ({guild.id}), channels auto-provision on first use.")

    # Guild-scoped (dev guild only) — same pattern as dev_global_logs.py's dev_group.
    weblog_group = app_commands.Group(name="weblog", description="[Dev guild only] Weblog system status")

    @weblog_group.command(name="setup", description="Check / trigger the weblog auto-provisioning")
    async def weblog_setup(self, interaction: discord.Interaction):
        if interaction.guild_id != _DEV_GUILD:
            return await interaction.response.send_message("This command can only be used in the dev guild.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        if not guild.me.guild_permissions.manage_channels:
            return await interaction.followup.send(f"❌ I'm missing **Manage Channels** in {guild.name}.", ephemeral=True)

        parent = await _ensure_category_channel(guild)
        if parent is None:
            return await interaction.followup.send("❌ Could not create/find the log category folder.", ephemeral=True)

        with _connect() as conn:
            rows = conn.execute("SELECT category, channel_id FROM weblog_channels").fetchall()

        lines = [f"✅ Working — folder **{parent.name}**."]
        if rows:
            lines.append("Existing log channels:")
            lines += [f"• `{r['category']}` → <#{r['channel_id']}>" for r in rows]
        else:
            lines.append("No category channels created yet — they auto-create on first `post_weblog()` call.")
        await interaction.followup.send("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WeblogCog(bot))