"""
weblog.py — posts an audit log entry to a Discord channel every time someone
takes an action through the WEBSITE dashboard (blacklist changes, Dev News
posts/deletes, bot banner changes, and any future admin-panel action that
calls `post_weblog()`).

    /weblog setup <channel>   — set (or change) the log channel

The command is deliberately hard to find:
    - Registered ONLY in your dev guild (same BLACKLIST_DEV_GUILD_ID env var
      blacklist.py uses) — it never shows up in any other server's command list.
    - `default_permissions(administrator=True)` — in Discord's own Integrations
      permission panel this is the exact same switch as turning the @everyone
      toggle OFF for the command: members without Administrator never see it
      in the slash-command picker at all, not even a greyed-out entry.
    - On top of both of the above, `is_bot_staff()` is checked in code too, so
      even an Administrator in your dev guild can't run it unless they're also
      bot staff (owner / ADMIN_USER_IDS).

Embeds use small-caps styling (ᴛɪᴛʟᴇ ᴄᴀsᴇ ʟɪᴋᴇ ᴛʜɪs) to visually set weblog
entries apart from normal bot messages at a glance.

Add "weblog" to the `extensions` list in main.py.
"""
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = Path(__file__).resolve().parent / "weblog.sqlite3"
DEV_GUILD_ID = os.getenv("BLACKLIST_DEV_GUILD_ID", "").strip()
_DEV_GUILD = int(DEV_GUILD_ID) if DEV_GUILD_ID.isdigit() else None

_SMALL_CAPS = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ",
)


def small_caps(text: str) -> str:
    """'Website Action' -> 'ᴡᴇʙsɪᴛᴇ ᴀᴄᴛɪᴏɴ'. Digits/punctuation pass through."""
    return (text or "").lower().translate(_SMALL_CAPS)


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS weblog_config (id INTEGER PRIMARY KEY CHECK (id = 1), channel_id INTEGER)"
        )
        conn.commit()


_init_db()


def get_weblog_channel_id() -> Optional[int]:
    with _connect() as conn:
        row = conn.execute("SELECT channel_id FROM weblog_config WHERE id = 1").fetchone()
    return row["channel_id"] if row and row["channel_id"] else None


def set_weblog_channel_id(channel_id: Optional[int]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO weblog_config (id, channel_id) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET channel_id = excluded.channel_id",
            (channel_id,),
        )
        conn.commit()


# Bot-wide reference set once the cog loads, so post_weblog() can be called
# from any other module (blacklist_api.py, devnews_api.py, admin_api.py, ...)
# without each of them needing their own copy of the bot instance.
_bot_ref: Optional[commands.Bot] = None


async def post_weblog(action: str, actor_label: str, details: str = "", color: int = 0x5865F2) -> bool:
    """Post one audit-log entry for a website-triggered action.

    action       e.g. "Server Blacklisted", "Dev News Published"
    actor_label  who did it, e.g. "User 123456789012345678" or an admin's name
    details      one or two lines of specifics (target, reason, etc.)

    Returns False (and does nothing else) if no weblog channel has been set
    up yet, or if it's no longer reachable -- this must never raise and break
    the website action it's logging.
    """
    if _bot_ref is None:
        return False
    channel_id = get_weblog_channel_id()
    if not channel_id:
        return False
    channel = _bot_ref.get_channel(channel_id)
    if channel is None:
        try:
            channel = await _bot_ref.fetch_channel(channel_id)
        except Exception:
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

    weblog_group = app_commands.Group(
        name="weblog",
        description="[Bot staff only] Configure the website audit-log channel",
        # Registered globally (not locked to one dev guild) so the bot owner/developer
        # can set this up in WHICHEVER of their own servers they want -- is_bot_staff()
        # below is what actually restricts who can run it, and default_permissions
        # keeps it out of the command picker for everyone else in every server.
        default_permissions=discord.Permissions(administrator=True),
    )

    @weblog_group.command(name="setup", description="Set the channel that receives website audit-log entries")
    @app_commands.describe(channel="The channel to post website actions to")
    async def weblog_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        from blacklist import is_bot_staff  # reuse the SAME staff identity as everything else

        if not await is_bot_staff(interaction, self.bot):
            return await interaction.response.send_message("Unknown command.", ephemeral=True)

        perms = channel.permissions_for(channel.guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            return await interaction.response.send_message(
                f"I need View Channel, Send Messages and Embed Links in {channel.mention}.", ephemeral=True
            )

        set_weblog_channel_id(channel.id)
        await interaction.response.send_message(f"✅ Website actions will now be logged to {channel.mention}.", ephemeral=True)
        await post_weblog("Weblog Configured", f"<@{interaction.user.id}>", f"Log channel set to {channel.mention}.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WeblogCog(bot))
