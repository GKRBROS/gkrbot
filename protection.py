"""
protection.py — Advanced Server Protection System for GKR Bot.
Features Anti-Raid, Anti-Spam, and Anti-Link modules.
"""

import os
import time
import re
import asyncio
import datetime
import sqlite3
from collections import defaultdict
from typing import Dict, List

import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = os.path.join(os.path.dirname(__file__), "protection.sqlite3")

class ProtectionDB:
    def __init__(self):
        self.db_path = DB_PATH
        
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS protection_config (
                    guild_id TEXT PRIMARY KEY,
                    anti_link INTEGER DEFAULT 0,
                    anti_spam INTEGER DEFAULT 0,
                    anti_raid INTEGER DEFAULT 0,
                    log_channel_id TEXT DEFAULT NULL
                )
            """)
            conn.commit()

    def get_config(self, guild_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM protection_config WHERE guild_id = ?", (str(guild_id),)).fetchone()
            if not row:
                return {"anti_link": 0, "anti_spam": 0, "anti_raid": 0, "log_channel_id": None}
            return dict(row)

    def set_config(self, guild_id: int, key: str, value):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO protection_config (guild_id, anti_link, anti_spam, anti_raid)
                VALUES (?, 0, 0, 0)
                ON CONFLICT(guild_id) DO NOTHING
            """, (str(guild_id),))
            conn.execute(f"UPDATE protection_config SET {key} = ? WHERE guild_id = ?", (value, str(guild_id)))
            conn.commit()

# URL Regex for Anti-Link
URL_REGEX = re.compile(r"(https?://\S+|www\.\S+|\w+\.\w{2,3}/\S*)")
DISCORD_INVITE_REGEX = re.compile(r"(discord\.gg/|discord\.com/invite/)")

class ProtectionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ProtectionDB()
        self.db.initialize()
        
        # State tracking for Anti-Spam and Anti-Raid
        self.spam_tracker = defaultdict(list) # user_id -> list of timestamps
        self.image_spam_tracker = defaultdict(list) # user_id -> list of (timestamp, message_obj)
        self.join_tracker = defaultdict(list) # guild_id -> list of join timestamps

    async def _log_action(self, guild: discord.Guild, embed: discord.Embed):
        cfg = self.db.get_config(guild.id)
        if cfg["log_channel_id"]:
            chan = guild.get_channel(int(cfg["log_channel_id"]))
            if chan:
                try:
                    await chan.send(embed=embed)
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Skip checks if user is admin
        if message.author.guild_permissions.manage_messages:
            return

        cfg = self.db.get_config(message.guild.id)

        # ---------------------------------------------------------
        # Anti-Link
        # ---------------------------------------------------------
        if cfg["anti_link"]:
            if DISCORD_INVITE_REGEX.search(message.content) or URL_REGEX.search(message.content):
                try:
                    await message.delete()
                    warn_msg = await message.channel.send(f"⚠️ {message.author.mention}, posting links is disabled in this server!")
                    
                    embed = discord.Embed(title="🛡️ Anti-Link Triggered", color=0xE74C3C)
                    embed.add_field(name="User", value=f"{message.author.mention} ({message.author.id})")
                    embed.add_field(name="Channel", value=message.channel.mention)
                    embed.add_field(name="Content", value=message.content[:1024], inline=False)
                    await self._log_action(message.guild, embed)
                    
                    await asyncio.sleep(5)
                    await warn_msg.delete()
                    return # Stop processing this message further
                except discord.Forbidden:
                    pass

        # ---------------------------------------------------------
        # Anti-Spam (5 messages in 3 seconds = Timeout)
        # ---------------------------------------------------------
        if cfg["anti_spam"]:
            user_id = message.author.id
            now = time.time()
            
            # Clean up old messages
            self.spam_tracker[user_id] = [t for t in self.spam_tracker[user_id] if now - t < 3.0]
            self.spam_tracker[user_id].append(now)
            
            if len(self.spam_tracker[user_id]) >= 5:
                # Spam detected
                self.spam_tracker[user_id] = [] # Reset to prevent multiple timeouts
                try:
                    timeout_duration = datetime.timedelta(minutes=5)
                    await message.author.timeout(timeout_duration, reason="Anti-Spam Triggered")
                    await message.channel.send(f"🚫 {message.author.mention} has been timed out for 5 minutes for spamming.")
                    
                    embed = discord.Embed(title="🛡️ Anti-Spam Triggered", color=0xE74C3C)
                    embed.add_field(name="User", value=f"{message.author.mention} ({message.author.id})")
                    embed.add_field(name="Channel", value=message.channel.mention)
                    embed.add_field(name="Action", value="Timed out for 5 minutes")
                    await self._log_action(message.guild, embed)
                except discord.Forbidden:
                    pass

        # ---------------------------------------------------------
        # Anti-Spam (Image Spam Detection)
        # ---------------------------------------------------------
        if cfg["anti_spam"]:
            # Check for images in attachments
            image_count = sum(1 for a in message.attachments if a.content_type and a.content_type.startswith('image/'))
            if image_count > 0:
                user_id = message.author.id
                now = time.time()
                
                # Clean up old messages (track over 5 seconds)
                self.image_spam_tracker[user_id] = [(t, m) for t, m in self.image_spam_tracker[user_id] if now - t < 5.0]
                
                # Add the current message multiple times if it has multiple images
                for _ in range(image_count):
                    self.image_spam_tracker[user_id].append((now, message))
                
                if len(self.image_spam_tracker[user_id]) >= 3:
                    # Collect all messages that contributed to this spam
                    spam_msgs = set([m for _, m in self.image_spam_tracker[user_id]])
                    self.image_spam_tracker[user_id] = [] # Reset
                    
                    try:
                        # Try to bulk delete or individually delete the spam messages
                        for m in spam_msgs:
                            try:
                                await m.delete()
                            except discord.NotFound:
                                pass
                                
                        timeout_duration = datetime.timedelta(minutes=10)
                        await message.author.timeout(timeout_duration, reason="Anti-Spam Triggered (Image Spam)")
                        await message.channel.send(f"🚫 {message.author.mention} has been timed out for 10 minutes for spamming images.")
                        
                        embed = discord.Embed(title="🛡️ Anti-Spam Triggered (Image Spam)", color=0xE74C3C)
                        embed.add_field(name="User", value=f"{message.author.mention} ({message.author.id})")
                        embed.add_field(name="Channel", value=message.channel.mention)
                        embed.add_field(name="Action", value="Timed out for 10 minutes")
                        await self._log_action(message.guild, embed)
                    except discord.Forbidden:
                        pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self.db.get_config(member.guild.id)
        
        # ---------------------------------------------------------
        # Anti-Raid (Mass Join Detection: 10 joins in 10 seconds)
        # ---------------------------------------------------------
        if cfg["anti_raid"]:
            guild_id = member.guild.id
            now = time.time()
            
            self.join_tracker[guild_id] = [t for t in self.join_tracker[guild_id] if now - t < 10.0]
            self.join_tracker[guild_id].append(now)
            
            if len(self.join_tracker[guild_id]) >= 10:
                # RAID DETECTED
                self.join_tracker[guild_id] = [] # Reset to prevent multiple triggers
                
                # Lockdown server (remove send_messages from @everyone in all text channels)
                # Note: Modifying all channels can be extremely rate-limited, so we modify the guild default role instead
                try:
                    everyone = member.guild.default_role
                    perms = everyone.permissions
                    perms.update(send_messages=False)
                    await everyone.edit(permissions=perms, reason="🛡️ ANTI-RAID LOCKDOWN")
                    
                    embed = discord.Embed(title="🚨 ANTI-RAID LOCKDOWN 🚨", color=0xFF0000)
                    embed.description = "Mass join detected (>10 users in 10s). The server has been locked down automatically."
                    embed.add_field(name="Action Taken", value="Removed `Send Messages` permission from `@everyone`")
                    await self._log_action(member.guild, embed)
                except discord.Forbidden:
                    print("Failed to lock down server - Missing Permissions")

    # -----------------------------------------------------------------------
    # Slash Commands
    # -----------------------------------------------------------------------

    protect_group = app_commands.Group(name="protection", description="Advanced Server Protection settings")

    @protect_group.command(name="status", description="Check current protection status")
    @app_commands.default_permissions(manage_guild=True)
    async def p_status(self, interaction: discord.Interaction):
        cfg = self.db.get_config(interaction.guild.id)
        embed = discord.Embed(title="🛡️ Protection Status", color=0x3498DB)
        
        embed.add_field(name="Anti-Link", value="✅ Enabled" if cfg["anti_link"] else "❌ Disabled")
        embed.add_field(name="Anti-Spam", value="✅ Enabled" if cfg["anti_spam"] else "❌ Disabled")
        embed.add_field(name="Anti-Raid", value="✅ Enabled" if cfg["anti_raid"] else "❌ Disabled")
        
        log_ch = f"<#{cfg['log_channel_id']}>" if cfg["log_channel_id"] else "None"
        embed.add_field(name="Log Channel", value=log_ch, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @protect_group.command(name="toggle", description="Toggle a protection feature")
    @app_commands.describe(feature="The feature to toggle")
    @app_commands.choices(feature=[
        app_commands.Choice(name="Anti-Link", value="anti_link"),
        app_commands.Choice(name="Anti-Spam", value="anti_spam"),
        app_commands.Choice(name="Anti-Raid", value="anti_raid"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def p_toggle(self, interaction: discord.Interaction, feature: str):
        cfg = self.db.get_config(interaction.guild.id)
        new_val = 0 if cfg[feature] else 1
        self.db.set_config(interaction.guild.id, feature, new_val)
        
        status = "Enabled" if new_val else "Disabled"
        await interaction.response.send_message(f"✅ **{feature.replace('_', ' ').title()}** is now **{status}**.", ephemeral=True)

    @protect_group.command(name="set_log_channel", description="Set the channel where protection alerts go")
    @app_commands.default_permissions(manage_guild=True)
    async def p_set_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.db.set_config(interaction.guild.id, "log_channel_id", str(channel.id))
        await interaction.response.send_message(f"✅ Protection logs will now be sent to {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProtectionCog(bot))
    print("🛡️ Protection system loaded!")
