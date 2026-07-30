"""
notifications.py — Boost & Server Level-up Notifications for GKR Bot.

Features:
  • Detects when a member boosts the server (premium_since change)
  • Detects when the server reaches a new Boost Tier (level 1/2/3)
  • Sends a fully customisable, beautiful embed to a configured channel
  • /notifications setup         — set channels and messages
  • /notifications boost         — configure boost notification
  • /notifications boostlevel    — configure server level-up notification
  • /notifications test boost     — preview boost card
  • /notifications test boostlevel — preview server level-up card
"""

from __future__ import annotations

import asyncio
import datetime
import os
import sqlite3
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_DB_PATH = os.path.join(os.path.dirname(__file__), "font_sync.sqlite3")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_configs (
                guild_id                INTEGER PRIMARY KEY,

                boost_channel_id        TEXT,
                boost_message           TEXT NOT NULL DEFAULT '🚀 **{member}** just boosted the server! Thank you so much! 💖',
                boost_enabled           INTEGER NOT NULL DEFAULT 1,

                boostlevel_channel_id   TEXT,
                boostlevel_message      TEXT NOT NULL DEFAULT '🎉 The server has reached **Boost Level {level}**! Thank you to all boosters! 💜',
                boostlevel_enabled      INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load(guild_id: int) -> sqlite3.Row | None:
    with _db() as conn:
        return conn.execute(
            "SELECT * FROM notification_configs WHERE guild_id = ?", (guild_id,)
        ).fetchone()


def _ensure(guild_id: int) -> None:
    with _db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO notification_configs (guild_id) VALUES (?)", (guild_id,)
        )
        conn.commit()


def _set(guild_id: int, **kwargs) -> None:
    _ensure(guild_id)
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [guild_id]
    with _db() as conn:
        conn.execute(f"UPDATE notification_configs SET {sets} WHERE guild_id = ?", vals)
        conn.commit()


# ---------------------------------------------------------------------------
# Embed builders
# ---------------------------------------------------------------------------

def _boost_embed(member: discord.Member, message: str) -> discord.Embed:
    desc = message.format(
        member=member.mention,
        member_name=member.display_name,
        server=member.guild.name,
        boost_count=member.guild.premium_subscription_count or 0,
        boost_tier=member.guild.premium_tier,
    )
    embed = discord.Embed(
        description=desc,
        color=0xFF73FA,  # Discord Nitro pink
        timestamp=datetime.datetime.utcnow(),
    )
    embed.set_author(
        name=f"{member.display_name} boosted the server!",
        icon_url=member.display_avatar.url,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="💜 Total Boosts", value=str(member.guild.premium_subscription_count or 0), inline=True)
    embed.add_field(name="🏆 Boost Tier", value=f"Level {member.guild.premium_tier}", inline=True)
    embed.set_footer(text=f"GKR Boost Notifications • {member.guild.name}")
    return embed


def _boostlevel_embed(guild: discord.Guild, old_tier: int, new_tier: int, message: str) -> discord.Embed:
    desc = message.format(
        level=new_tier,
        old_level=old_tier,
        server=guild.name,
        boost_count=guild.premium_subscription_count or 0,
    )
    tier_colors = {1: 0xF47FFF, 2: 0xA855F7, 3: 0x7C3AED}
    color = tier_colors.get(new_tier, 0xFF73FA)

    embed = discord.Embed(
        title=f"🎉 Server Unlocked Boost Level {new_tier}!",
        description=desc,
        color=color,
        timestamp=datetime.datetime.utcnow(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    perks = {
        1: "Better audio quality (128kbps), Animated server icon, Server invite background",
        2: "Even better audio (256kbps), Server banner, 50 custom emoji slots",
        3: "Best audio (384kbps), Vanity URL, 100 custom emoji slots",
    }
    embed.add_field(name="✨ Newly Unlocked Perks", value=perks.get(new_tier, "Various perks!"), inline=False)
    embed.add_field(name="💜 Total Boosts", value=str(guild.premium_subscription_count or 0), inline=True)
    embed.set_footer(text=f"GKR Boost Notifications • {guild.name}")
    return embed


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class NotificationsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _init_db()

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Fires when a member boosts (premium_since goes from None → a date)."""
        if before.premium_since is None and after.premium_since is not None:
            await self._send_boost(after)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """Fires when the server changes boost tier."""
        if before.premium_tier < after.premium_tier:
            await self._send_boost_level(after, old_tier=before.premium_tier, new_tier=after.premium_tier)

    # ── Internal senders ──────────────────────────────────────────────────────

    async def _send_boost(self, member: discord.Member) -> None:
        row = _load(member.guild.id)
        if not row:
            return
        if not row["boost_enabled"] or not row["boost_channel_id"]:
            return

        ch = member.guild.get_channel(int(row["boost_channel_id"]))
        if not isinstance(ch, discord.TextChannel):
            return

        embed = _boost_embed(member, row["boost_message"])
        try:
            await ch.send(content=f"💖 {member.mention}", embed=embed)
        except discord.Forbidden:
            print(f"[Notifications] Missing permissions to send boost notification in {ch.name}")
        except Exception as e:
            print(f"[Notifications] Failed to send boost notification: {e}")

    async def _send_boost_level(self, guild: discord.Guild, old_tier: int, new_tier: int) -> None:
        row = _load(guild.id)
        if not row:
            return
        if not row["boostlevel_enabled"] or not row["boostlevel_channel_id"]:
            return

        ch = guild.get_channel(int(row["boostlevel_channel_id"]))
        if not isinstance(ch, discord.TextChannel):
            return

        embed = _boostlevel_embed(guild, old_tier, new_tier, row["boostlevel_message"])
        try:
            await ch.send(embed=embed)
        except discord.Forbidden:
            print(f"[Notifications] Missing permissions to send level-up notification in {ch.name}")
        except Exception as e:
            print(f"[Notifications] Failed to send level-up notification: {e}")

    # ── Commands ──────────────────────────────────────────────────────────────

    notifs_group = app_commands.Group(
        name="notifications",
        description="Configure Boost & Server Level-Up notification messages",
    )
    test_group = app_commands.Group(
        name="test",
        description="Preview notification messages",
        parent=notifs_group,
    )

    # /notifications boost channel
    @notifs_group.command(name="boost", description="Configure boost notification channel & message")
    @app_commands.describe(
        channel="Channel to send boost notifications in",
        message="Custom message (supports {member}, {member_name}, {server}, {boost_count}, {boost_tier})",
        enabled="Enable or disable boost notifications",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def config_boost(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        message: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        _ensure(interaction.guild.id)
        updates = {}
        if channel is not None:
            updates["boost_channel_id"] = str(channel.id)
        if message is not None:
            updates["boost_message"] = message
        if enabled is not None:
            updates["boost_enabled"] = 1 if enabled else 0

        if updates:
            _set(interaction.guild.id, **updates)

        row = _load(interaction.guild.id)
        ch_mention = "Not set"
        if row and row["boost_channel_id"]:
            c = interaction.guild.get_channel(int(row["boost_channel_id"]))
            ch_mention = c.mention if c else "Deleted channel"

        embed = discord.Embed(title="🚀 Boost Notification Settings", color=0xFF73FA)
        embed.add_field(name="Channel", value=ch_mention, inline=True)
        embed.add_field(name="Enabled", value="✅ Yes" if (row and row["boost_enabled"]) else "❌ No", inline=True)
        embed.add_field(name="Message", value=f"```{row['boost_message'] if row else ''}```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /notifications boostlevel
    @notifs_group.command(name="boostlevel", description="Configure server level-up notification channel & message")
    @app_commands.describe(
        channel="Channel to send level-up notifications in",
        message="Custom message (supports {level}, {old_level}, {server}, {boost_count})",
        enabled="Enable or disable level-up notifications",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def config_boostlevel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        message: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        _ensure(interaction.guild.id)
        updates = {}
        if channel is not None:
            updates["boostlevel_channel_id"] = str(channel.id)
        if message is not None:
            updates["boostlevel_message"] = message
        if enabled is not None:
            updates["boostlevel_enabled"] = 1 if enabled else 0

        if updates:
            _set(interaction.guild.id, **updates)

        row = _load(interaction.guild.id)
        ch_mention = "Not set"
        if row and row["boostlevel_channel_id"]:
            c = interaction.guild.get_channel(int(row["boostlevel_channel_id"]))
            ch_mention = c.mention if c else "Deleted channel"

        embed = discord.Embed(title="🏆 Server Level-Up Notification Settings", color=0xA855F7)
        embed.add_field(name="Channel", value=ch_mention, inline=True)
        embed.add_field(name="Enabled", value="✅ Yes" if (row and row["boostlevel_enabled"]) else "❌ No", inline=True)
        embed.add_field(name="Message", value=f"```{row['boostlevel_message'] if row else ''}```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /notifications status
    @notifs_group.command(name="status", description="Show all notification settings")
    @app_commands.default_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction) -> None:
        row = _load(interaction.guild.id)

        embed = discord.Embed(
            title="🔔 Notification Settings",
            color=0xFF73FA,
            timestamp=datetime.datetime.utcnow(),
        )

        # Boost
        boost_ch = "Not set"
        if row and row["boost_channel_id"]:
            c = interaction.guild.get_channel(int(row["boost_channel_id"]))
            boost_ch = c.mention if c else "Deleted channel"
        embed.add_field(
            name="🚀 Boost Notifications",
            value=(
                f"Channel: {boost_ch}\n"
                f"Enabled: {'✅' if row and row['boost_enabled'] else '❌'}"
            ),
            inline=True,
        )

        # Level-up
        level_ch = "Not set"
        if row and row["boostlevel_channel_id"]:
            c = interaction.guild.get_channel(int(row["boostlevel_channel_id"]))
            level_ch = c.mention if c else "Deleted channel"
        embed.add_field(
            name="🏆 Level-Up Notifications",
            value=(
                f"Channel: {level_ch}\n"
                f"Enabled: {'✅' if row and row['boostlevel_enabled'] else '❌'}"
            ),
            inline=True,
        )

        embed.set_footer(text="Use /notifications boost or /notifications boostlevel to configure")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /notifications test boost
    @test_group.command(name="boost", description="Preview the boost notification in this channel")
    @app_commands.default_permissions(manage_guild=True)
    async def test_boost(self, interaction: discord.Interaction) -> None:
        row = _load(interaction.guild.id)
        message = (row["boost_message"] if row else
                   "🚀 **{member}** just boosted the server! Thank you so much! 💖")
        embed = _boost_embed(interaction.user, message)
        await interaction.response.send_message(
            content="📋 **Preview — Boost Notification**",
            embed=embed,
            ephemeral=True,
        )

    # /notifications test boostlevel
    @test_group.command(name="boostlevel", description="Preview the server level-up notification in this channel")
    @app_commands.default_permissions(manage_guild=True)
    async def test_boostlevel(self, interaction: discord.Interaction) -> None:
        row = _load(interaction.guild.id)
        message = (row["boostlevel_message"] if row else
                   "🎉 The server has reached **Boost Level {level}**! Thank you to all boosters! 💜")
        embed = _boostlevel_embed(interaction.guild, old_tier=0, new_tier=1, message=message)
        await interaction.response.send_message(
            content="📋 **Preview — Server Level-Up Notification**",
            embed=embed,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NotificationsCog(bot))
    print("🔔 Notifications system loaded!")
