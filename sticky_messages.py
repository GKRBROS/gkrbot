"""
sticky_messages.py – Sticky Message System for GKR Bot.

A sticky message always stays as the last message in a channel.
When any user sends a message, the bot deletes its old sticky and
resends it at the bottom so it's always visible.

Admin Commands:
  /sticky set   <message>  – Set the sticky message for this channel
  /sticky clear            – Remove the sticky message from this channel
  /sticky view             – Preview the current sticky for this channel
  /sticky list             – List all channels with stickies in this server
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "sticky_messages.sqlite3")

# Per-channel cooldown to avoid spam-deleting/reposting (seconds)
STICKY_COOLDOWN = 2.0


# ---------------------------------------------------------------------------
# Modal
# ---------------------------------------------------------------------------

class StickyModal(discord.ui.Modal, title="📌 Set Sticky Message"):
    content_input = discord.ui.TextInput(
        label="Sticky Message",
        style=discord.TextStyle.paragraph,
        placeholder="Paste your message here. All formatting, newlines and paragraph spacing will be preserved exactly.",
        required=True,
        max_length=2000,
    )

    def __init__(self, db: "StickyDB", channel: discord.TextChannel):
        super().__init__()
        self.db = db
        self.channel = channel

        # Pre-fill with existing content if there is one
        existing = db.get_sticky(channel.id)
        if existing:
            self.content_input.default = existing["content"]

    async def on_submit(self, interaction: discord.Interaction):
        message = str(self.content_input)
        channel = self.channel

        # Delete any previously tracked sticky bot message
        existing = self.db.get_sticky(channel.id)
        if existing and existing["bot_msg_id"]:
            try:
                old = await channel.fetch_message(int(existing["bot_msg_id"]))
                await old.delete()
            except Exception:
                pass

        # Send the sticky wrapped in a code block as requested
        bot_msg = await channel.send(f"📌\n```\n{message}\n```")
        self.db.set_sticky(channel.id, interaction.guild.id, message, bot_msg.id)

        await interaction.response.send_message(
            f"✅ Sticky message set for {channel.mention}! It will always stay at the bottom.",
            ephemeral=True
        )


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class StickyDB:
    def __init__(self):
        self._init()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stickies (
                    channel_id  TEXT PRIMARY KEY,
                    guild_id    TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    bot_msg_id  TEXT
                )
            """)
            conn.commit()

    def set_sticky(self, channel_id: int, guild_id: int, content: str, bot_msg_id: Optional[int] = None):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO stickies (channel_id, guild_id, content, bot_msg_id) VALUES (?, ?, ?, ?)",
                (str(channel_id), str(guild_id), content, str(bot_msg_id) if bot_msg_id else None)
            )
            conn.commit()

    def get_sticky(self, channel_id: int) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM stickies WHERE channel_id = ?",
                (str(channel_id),)
            ).fetchone()

    def update_bot_msg_id(self, channel_id: int, bot_msg_id: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE stickies SET bot_msg_id = ? WHERE channel_id = ?",
                (str(bot_msg_id), str(channel_id))
            )
            conn.commit()

    def remove_sticky(self, channel_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM stickies WHERE channel_id = ?", (str(channel_id),))
            conn.commit()

    def get_all_for_guild(self, guild_id: int) -> list:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM stickies WHERE guild_id = ?",
                (str(guild_id),)
            ).fetchall()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class StickyMessagesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = StickyDB()
        # Track channels that are currently on cooldown to avoid hammering
        self._cooldown: dict[int, asyncio.Task] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore DMs, ignore the bot itself
        if not message.guild or message.author.bot:
            return

        channel_id = message.channel.id
        row = self.db.get_sticky(channel_id)
        if not row:
            return

        # If already cooling down, cancel previous pending task and start fresh
        if channel_id in self._cooldown:
            self._cooldown[channel_id].cancel()

        # Schedule the repost after a short cooldown to batch rapid messages
        task = asyncio.create_task(self._repost_sticky(message.channel, row))
        self._cooldown[channel_id] = task

    async def _repost_sticky(self, channel: discord.TextChannel, row):
        """Delete the old sticky bot message and send a fresh one at the bottom."""
        await asyncio.sleep(STICKY_COOLDOWN)

        # Delete old sticky message if it exists
        old_msg_id = row["bot_msg_id"]
        if old_msg_id:
            try:
                old_msg = await channel.fetch_message(int(old_msg_id))
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden, Exception):
                pass

        # Send the new sticky at the bottom wrapped in a code block
        try:
            new_msg = await channel.send(f"📌\n```\n{row['content']}\n```")
            self.db.update_bot_msg_id(channel.id, new_msg.id)
        except (discord.Forbidden, Exception) as e:
            print(f"[Sticky] ❌ Failed to repost sticky in #{channel.name}: {e}")

        # Remove cooldown entry
        self._cooldown.pop(channel.id, None)

    # ── Slash Commands ────────────────────────────────────────────────────────

    sticky_group = app_commands.Group(
        name="sticky",
        description="Manage sticky messages for this channel"
    )

    @sticky_group.command(name="set", description="Set a sticky message that always stays at the bottom of this channel")
    @app_commands.default_permissions(manage_messages=True)
    async def sticky_set(self, interaction: discord.Interaction):
        """Opens a popup so you can paste multi-line content with full formatting."""
        modal = StickyModal(self.db, interaction.channel)
        await interaction.response.send_modal(modal)

    @sticky_group.command(name="clear", description="Remove the sticky message from this channel")
    @app_commands.default_permissions(manage_messages=True)
    async def sticky_clear(self, interaction: discord.Interaction):
        channel = interaction.channel
        row = self.db.get_sticky(channel.id)
        if not row:
            await interaction.response.send_message("❌ No sticky message is set for this channel.", ephemeral=True)
            return

        # Delete the pinned bot message
        if row["bot_msg_id"]:
            try:
                msg = await channel.fetch_message(int(row["bot_msg_id"]))
                await msg.delete()
            except Exception:
                pass

        self.db.remove_sticky(channel.id)
        await interaction.response.send_message("✅ Sticky message removed from this channel.", ephemeral=True)

    @sticky_group.command(name="view", description="Preview the current sticky message for this channel")
    async def sticky_view(self, interaction: discord.Interaction):
        row = self.db.get_sticky(interaction.channel.id)
        if not row:
            await interaction.response.send_message("❌ No sticky message is set for this channel.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📌 Sticky for #{interaction.channel.name}",
            description=row["content"],
            color=0xFAA61A,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @sticky_group.command(name="list", description="List all channels with sticky messages in this server")
    @app_commands.default_permissions(manage_messages=True)
    async def sticky_list(self, interaction: discord.Interaction):
        rows = self.db.get_all_for_guild(interaction.guild.id)
        if not rows:
            await interaction.response.send_message("❌ No sticky messages set in this server.", ephemeral=True)
            return

        lines = []
        for row in rows:
            ch = interaction.guild.get_channel(int(row["channel_id"]))
            ch_str = ch.mention if ch else f"<#{row['channel_id']}> (deleted)"
            preview = row["content"][:60] + "..." if len(row["content"]) > 60 else row["content"]
            lines.append(f"**{ch_str}** — `{preview}`")

        embed = discord.Embed(
            title=f"📌 Sticky Messages in {interaction.guild.name}",
            description="\n".join(lines),
            color=0xFAA61A,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(StickyMessagesCog(bot))
    print("📌 Sticky Messages system loaded!")
