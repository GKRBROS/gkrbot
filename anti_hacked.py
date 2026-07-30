"""
anti_hacked.py – Anti Hacked Account Protection
Detects compromised accounts sending scam images or mass pings across multiple channels quickly.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import os
import time
import datetime
from collections import defaultdict
import asyncio

DB_PATH = os.path.join(os.path.dirname(__file__), "anti_hacked.sqlite3")

# Roles with any of these permissions are considered "Powerful"
POWERFUL_PERMS = [
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "ban_members",
    "kick_members",
    "moderate_members",  # Timeout Members
    "mention_everyone",
    "manage_messages",
]

class AntiHackedDB:
    def __init__(self):
        self._init()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    guild_id TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    log_channel_id TEXT
                )
            """)
            conn.commit()

    def get_config(self, guild_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM config WHERE guild_id = ?", (str(guild_id),)).fetchone()
            if not row:
                return {"enabled": 1, "log_channel_id": None}
            return dict(row)

    def set_config(self, guild_id: int, key: str, value):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO config (guild_id, enabled) VALUES (?, 1) ON CONFLICT(guild_id) DO NOTHING",
                (str(guild_id),)
            )
            conn.execute(f"UPDATE config SET {key} = ? WHERE guild_id = ?", (value, str(guild_id)))
            conn.commit()


class AntiHackedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = AntiHackedDB()
        # guild_id -> user_id -> list of (timestamp, discord.Message)
        self.tracker = defaultdict(lambda: defaultdict(list))
        self.cleanup_tracker.start()

    def cog_unload(self):
        self.cleanup_tracker.cancel()

    @tasks.loop(minutes=5)
    async def cleanup_tracker(self):
        """Runs every 5 minutes to clear out old tracked messages and prevent memory leaks."""
        now = time.time()
        for guild_id in list(self.tracker.keys()):
            for user_id in list(self.tracker[guild_id].keys()):
                # Keep only messages from the last 20 seconds
                self.tracker[guild_id][user_id] = [(t, msg) for t, msg in self.tracker[guild_id][user_id] if now - t <= 20.0]
                if not self.tracker[guild_id][user_id]:
                    del self.tracker[guild_id][user_id]
            if not self.tracker[guild_id]:
                del self.tracker[guild_id]

    def is_staff(self, member: discord.Member) -> bool:
        """Check if the user has any powerful permissions natively."""
        # Check base permissions (without channel overrides)
        perms = member.guild_permissions
        for perm in POWERFUL_PERMS:
            if getattr(perms, perm, False):
                return True
        return False

    def is_spam_message(self, message: discord.Message) -> bool:
        """Check if message matches the 'Image + ping' or 'Image spam' criteria."""
        has_image = any(a.content_type and a.content_type.startswith('image/') for a in message.attachments)
        has_mass_ping = message.mention_everyone or len(message.role_mentions) > 0
        
        # Consider it spam if it has an image (image spam) OR it's a mass ping
        # Hackers often post an image with @everyone or just an image link
        has_link = "http://" in message.content or "https://" in message.content
        
        return has_image or has_mass_ping or (has_link and has_mass_ping)

    async def execute_lockdown(self, member: discord.Member, spam_messages: list[discord.Message], config: dict):
        guild = member.guild
        
        # 1. Delete messages
        for msg in spam_messages:
            try:
                await msg.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass

        # 2. Remove powerful roles
        roles_removed = []
        roles_to_remove = []
        for role in member.roles:
            # Skip @everyone and roles we can't touch (higher than bot)
            if role.is_default() or role.managed or role >= guild.me.top_role:
                continue
                
            # Check if role grants powerful perms
            role_perms = role.permissions
            is_powerful = any(getattr(role_perms, p, False) for p in POWERFUL_PERMS)
            if is_powerful:
                roles_to_remove.append(role)
                roles_removed.append(role.name)
                
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason="Anti-Hacked Protection: Removed powerful roles")
            except discord.Forbidden:
                pass

        # 3. Timeout for 25 minutes
        timeout_duration = datetime.timedelta(minutes=25)
        try:
            await member.timeout(timeout_duration, reason="Anti-Hacked Protection Triggered")
        except discord.Forbidden:
            pass

        # 4. Log it
        if config["log_channel_id"]:
            log_chan = guild.get_channel(int(config["log_channel_id"]))
            if log_chan:
                embed = discord.Embed(
                    title="🛡️ Hacked Account Protected!",
                    description=f"**{member.mention}** was detected sending cross-channel spam and has been neutralized.",
                    color=0xE74C3C
                )
                embed.add_field(name="Action Taken", value="⏳ Timed out for 25 minutes", inline=False)
                
                if roles_removed:
                    embed.add_field(name="⚠️ Powerful Roles Removed", value=", ".join(roles_removed), inline=False)
                else:
                    embed.add_field(name="⚠️ Powerful Roles Removed", value="None", inline=False)
                    
                embed.add_field(name="Deleted Spam", value=f"{len(spam_messages)} messages across multiple channels.", inline=False)
                
                try:
                    await log_chan.send(embed=embed)
                except discord.Forbidden:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = self.db.get_config(message.guild.id)
        if not config["enabled"]:
            return

        if not self.is_spam_message(message):
            return

        guild_id = message.guild.id
        user_id = message.author.id
        now = time.time()

        # Clean up old messages (keep only last 20 seconds)
        user_tracker = self.tracker[guild_id][user_id]
        self.tracker[guild_id][user_id] = [(t, msg) for t, msg in user_tracker if now - t <= 20.0]
        
        # Add current message
        self.tracker[guild_id][user_id].append((now, message))

        # Check unique channels in the tracker
        unique_channels = set(msg.channel.id for _, msg in self.tracker[guild_id][user_id])
        channel_count = len(unique_channels)

        # Determine threshold
        is_staff_member = self.is_staff(message.author)
        threshold = 3 if is_staff_member else 2

        if channel_count >= threshold:
            # TRIGGER LOCKDOWN
            spam_messages = [msg for _, msg in self.tracker[guild_id][user_id]]
            self.tracker[guild_id][user_id] = [] # Reset tracker
            
            # Execute lockdown asynchronously so we don't block the event loop
            asyncio.create_task(self.execute_lockdown(message.author, spam_messages, config))


    # ── Slash Commands ────────────────────────────────────────────────────────

    antihack_group = app_commands.Group(
        name="antihacked",
        description="Manage the Anti-Hacked Account Protection system"
    )

    @antihack_group.command(name="toggle", description="Enable or disable the Anti-Hacked Protection")
    @app_commands.default_permissions(manage_guild=True)
    async def ah_toggle(self, interaction: discord.Interaction):
        config = self.db.get_config(interaction.guild.id)
        new_state = 0 if config["enabled"] else 1
        self.db.set_config(interaction.guild.id, "enabled", new_state)
        
        status = "✅ **Enabled**" if new_state else "❌ **Disabled**"
        await interaction.response.send_message(f"Anti-Hacked Protection is now {status}.", ephemeral=True)

    @antihack_group.command(name="logchannel", description="Set the channel where protection logs will be sent")
    @app_commands.default_permissions(manage_guild=True)
    async def ah_logchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.db.set_config(interaction.guild.id, "log_channel_id", str(channel.id))
        await interaction.response.send_message(f"✅ Anti-Hacked logs will now be sent to {channel.mention}.", ephemeral=True)

    @antihack_group.command(name="status", description="Show the Anti-Hacked Protection status")
    @app_commands.default_permissions(manage_guild=True)
    async def ah_status(self, interaction: discord.Interaction):
        config = self.db.get_config(interaction.guild.id)
        embed = discord.Embed(
            title="🛡️ Anti-Hacked Status",
            color=0x2ECC71 if config["enabled"] else 0xE74C3C
        )
        embed.add_field(name="Protection", value="✅ ON" if config["enabled"] else "❌ OFF", inline=False)
        
        log_ch = f"<#{config['log_channel_id']}>" if config["log_channel_id"] else "Not Set"
        embed.add_field(name="Log Channel", value=log_ch, inline=False)
        
        embed.add_field(
            name="Rules",
            value="• Normal Members: Blocked if spamming in **2** channels within 20s\n"
                  "• Staff/Admins: Blocked if spamming in **3** channels within 20s",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiHackedCog(bot))
    print("🛡️ Anti-Hacked system loaded!")
