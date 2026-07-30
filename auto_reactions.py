"""
auto_reactions.py – Auto-Reaction System for GKR Bot.

Automatically adds emoji reactions to every message posted in configured channels.
Perfect for announcement channels, news feeds, welcome channels, etc.

Admin Commands:
  /autoreact add <channel> <emoji>   – Add an emoji reaction to a channel
  /autoreact remove <channel> <emoji>– Remove a specific emoji reaction from a channel
  /autoreact clear <channel>         – Remove ALL auto-reactions from a channel
  /autoreact list                    – Show all configured channels and their reactions
"""

import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "auto_reactions.sqlite3")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class AutoReactDB:
    def __init__(self):
        self._init()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_reactions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    TEXT NOT NULL,
                    channel_id  TEXT NOT NULL,
                    emoji       TEXT NOT NULL,
                    UNIQUE(guild_id, channel_id, emoji)
                )
            """)
            conn.commit()

    def add_reaction(self, guild_id: int, channel_id: int, emoji: str) -> bool:
        """Add an emoji to a channel's auto-reaction list. Returns False if already exists."""
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO auto_reactions (guild_id, channel_id, emoji) VALUES (?, ?, ?)",
                    (str(guild_id), str(channel_id), emoji)
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # already exists

    def remove_reaction(self, guild_id: int, channel_id: int, emoji: str) -> bool:
        """Remove a specific emoji from a channel. Returns True if it was found."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM auto_reactions WHERE guild_id = ? AND channel_id = ? AND emoji = ?",
                (str(guild_id), str(channel_id), emoji)
            )
            conn.commit()
        return cur.rowcount > 0

    def clear_channel(self, guild_id: int, channel_id: int) -> int:
        """Remove all reactions for a channel. Returns count deleted."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM auto_reactions WHERE guild_id = ? AND channel_id = ?",
                (str(guild_id), str(channel_id))
            )
            conn.commit()
        return cur.rowcount

    def get_reactions_for_channel(self, guild_id: int, channel_id: int) -> list[str]:
        """Get all emojis configured for this channel."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT emoji FROM auto_reactions WHERE guild_id = ? AND channel_id = ?",
                (str(guild_id), str(channel_id))
            ).fetchall()
        return [r["emoji"] for r in rows]

    def get_all_for_guild(self, guild_id: int) -> list:
        """Get all auto-reaction config entries for a guild."""
        with self._conn() as conn:
            return conn.execute(
                "SELECT channel_id, emoji FROM auto_reactions WHERE guild_id = ? ORDER BY channel_id",
                (str(guild_id),)
            ).fetchall()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class AutoReactionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = AutoReactDB()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Add reactions to messages in configured channels."""
        # Ignore DMs, ignore the bot itself
        if not message.guild or message.author.bot:
            return

        reactions = self.db.get_reactions_for_channel(message.guild.id, message.channel.id)
        if not reactions:
            return

        for emoji_str in reactions:
            try:
                # Try as a unicode emoji first, then as a custom emoji
                await message.add_reaction(emoji_str)
            except discord.HTTPException:
                # Try to resolve as a custom emoji from this guild
                try:
                    # Custom emoji format: <:name:id> or <a:name:id>
                    emoji_obj = discord.utils.get(message.guild.emojis, name=emoji_str)
                    if emoji_obj:
                        await message.add_reaction(emoji_obj)
                except Exception:
                    pass
            except Exception as e:
                print(f"[AutoReact] Failed to add reaction '{emoji_str}' in #{message.channel.name}: {e}")

    # ── Slash Commands ────────────────────────────────────────────────────────

    react_group = app_commands.Group(
        name="autoreact",
        description="Manage auto-reactions for channels"
    )

    @react_group.command(name="add", description="Add an auto-reaction emoji to a channel")
    @app_commands.describe(
        channel="The channel to add auto-reactions to",
        emoji="The emoji to automatically add (e.g. 👍, or a custom server emoji)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def add_reaction(self, interaction: discord.Interaction, channel: discord.TextChannel, emoji: str):
        emoji = emoji.strip()

        # Validate the emoji by trying to add a test reaction
        # We'll try to react to a message we can find, but the simplest way is just to store and let it fail naturally
        # Instead let's try a quick format validation
        
        success = self.db.add_reaction(interaction.guild.id, channel.id, emoji)
        if not success:
            await interaction.response.send_message(
                f"⚠️ `{emoji}` is already an auto-reaction for {channel.mention}.",
                ephemeral=True
            )
            return

        current = self.db.get_reactions_for_channel(interaction.guild.id, channel.id)
        embed = discord.Embed(
            title="✅ Auto-Reaction Added",
            description=(
                f"The bot will now react with **{emoji}** to every message in {channel.mention}.\n\n"
                f"**All reactions for this channel:** {' '.join(current)}"
            ),
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @react_group.command(name="remove", description="Remove a specific auto-reaction from a channel")
    @app_commands.describe(
        channel="The channel to remove the reaction from",
        emoji="The specific emoji to remove"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def remove_reaction(self, interaction: discord.Interaction, channel: discord.TextChannel, emoji: str):
        emoji = emoji.strip()
        removed = self.db.remove_reaction(interaction.guild.id, channel.id, emoji)
        if not removed:
            await interaction.response.send_message(
                f"❌ `{emoji}` was not found as an auto-reaction for {channel.mention}.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Removed `{emoji}` from auto-reactions in {channel.mention}.",
            ephemeral=True
        )

    @react_group.command(name="clear", description="Remove ALL auto-reactions from a channel")
    @app_commands.describe(channel="The channel to clear all auto-reactions from")
    @app_commands.default_permissions(manage_guild=True)
    async def clear_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        count = self.db.clear_channel(interaction.guild.id, channel.id)
        if count == 0:
            await interaction.response.send_message(
                f"❌ No auto-reactions configured for {channel.mention}.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Cleared **{count}** auto-reaction(s) from {channel.mention}.",
            ephemeral=True
        )

    @react_group.command(name="list", description="Show all channels with auto-reactions in this server")
    async def list_reactions(self, interaction: discord.Interaction):
        rows = self.db.get_all_for_guild(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(
                "❌ No auto-reactions configured in this server.\nUse `/autoreact add` to set one up!",
                ephemeral=True
            )
            return

        # Group by channel
        grouped: dict[str, list[str]] = {}
        for row in rows:
            ch_id = row["channel_id"]
            if ch_id not in grouped:
                grouped[ch_id] = []
            grouped[ch_id].append(row["emoji"])

        lines = []
        for ch_id, emojis in grouped.items():
            ch = interaction.guild.get_channel(int(ch_id))
            ch_str = ch.mention if ch else f"<#{ch_id}> *(deleted)*"
            lines.append(f"**{ch_str}** — {' '.join(emojis)}")

        embed = discord.Embed(
            title=f"⚡ Auto-Reactions in {interaction.guild.name}",
            description="\n".join(lines),
            color=0x3498DB
        )
        embed.set_footer(text=f"{len(grouped)} channel(s) configured")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReactionsCog(bot))
    print("⚡ Auto-Reactions system loaded!")
