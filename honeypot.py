"""
honeypot.py – Spam Trap Channel System
Creates a honeypot channel where any user who sends a message gets escalating punishments:
1st Offense: 10 minute timeout
2nd Offense: 1 day timeout
3rd Offense: Kick from server
"""

import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "honeypot.sqlite3")


class HoneypotDB:
    def __init__(self):
        self._init()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            # Store the honeypot channel per guild
            conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL
                )
            """)
            # Store user offense counts
            conn.execute("""
                CREATE TABLE IF NOT EXISTS offenses (
                    guild_id TEXT,
                    user_id TEXT,
                    count INTEGER DEFAULT 0,
                    PRIMARY KEY(guild_id, user_id)
                )
            """)
            conn.commit()

    def set_channel(self, guild_id: int, channel_id: int):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO channels (guild_id, channel_id) VALUES (?, ?)",
                (str(guild_id), str(channel_id))
            )
            conn.commit()

    def get_channel(self, guild_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT channel_id FROM channels WHERE guild_id = ?", (str(guild_id),)).fetchone()
            if row:
                return int(row["channel_id"])
        return None

    def add_offense(self, guild_id: int, user_id: int) -> int:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO offenses (guild_id, user_id, count) VALUES (?, ?, 1) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + 1",
                (str(guild_id), str(user_id))
            )
            row = conn.execute("SELECT count FROM offenses WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id))).fetchone()
            conn.commit()
            return row["count"]

    def clear_offenses(self, guild_id: int, user_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM offenses WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
            conn.commit()


class HoneypotCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = HoneypotDB()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Check if the channel is a configured honeypot
        trap_channel_id = self.db.get_channel(message.guild.id)
        if not trap_channel_id or message.channel.id != trap_channel_id:
            return

        # Ignore admins/mods who might be testing or sending legit messages
        if message.author.guild_permissions.manage_messages:
            return

        # Triggered the trap!
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass

        offense_count = self.db.add_offense(message.guild.id, message.author.id)

        action_taken = ""
        try:
            if offense_count == 1:
                # 1st Offense: 10 minute timeout
                await message.author.timeout(datetime.timedelta(minutes=10), reason="Honeypot Triggered: 1st Offense")
                action_taken = "Timed out for 10 minutes"
            
            elif offense_count == 2:
                # 2nd Offense: 1 day timeout
                await message.author.timeout(datetime.timedelta(days=1), reason="Honeypot Triggered: 2nd Offense")
                action_taken = "Timed out for 1 day (24 hours)"
                
            else:
                # 3rd+ Offense: Kick
                await message.author.kick(reason=f"Honeypot Triggered: {offense_count} Offenses")
                action_taken = "Kicked from the server"
                
        except discord.Forbidden:
            action_taken = f"Attempted to punish, but bot lacks permissions to execute action for offense {offense_count}."
            print(f"[Honeypot] Missing perms to punish {message.author.name} for offense {offense_count}")

        # Send alert in the same channel (or admins could check audit logs)
        alert_embed = discord.Embed(
            title="🚨 Spam Trap Triggered!",
            description=f"**{message.author.mention}** fell into the honeypot.",
            color=0xFF0000
        )
        alert_embed.add_field(name="Offense Level", value=f"Offense #{offense_count}")
        alert_embed.add_field(name="Action Taken", value=action_taken)
        
        try:
            await message.channel.send(embed=alert_embed)
        except discord.Forbidden:
            pass


    # ── Slash Commands ────────────────────────────────────────────────────────

    hp_group = app_commands.Group(
        name="honeypot",
        description="Manage the Honeypot (Spam Trap) Channel system"
    )

    @hp_group.command(name="setchannel", description="Set a channel as the Honeypot/Spam Trap. ANY normal user messaging here will be punished!")
    @app_commands.default_permissions(manage_guild=True)
    async def hp_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.db.set_channel(interaction.guild.id, channel.id)
        embed = discord.Embed(
            title="🚨 Honeypot Channel Set",
            description=f"{channel.mention} is now the Spam Trap channel.\n\n**Warning:** Any normal user who types in that channel will be punished:\n"
                        "• **1st Offense:** 10m Timeout\n"
                        "• **2nd Offense:** 1d Timeout\n"
                        "• **3rd+ Offense:** Kicked",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @hp_group.command(name="clearoffenses", description="Forgive a user and reset their honeypot offense count to 0")
    @app_commands.default_permissions(manage_guild=True)
    async def hp_clear(self, interaction: discord.Interaction, user: discord.User):
        self.db.clear_offenses(interaction.guild.id, user.id)
        await interaction.response.send_message(f"✅ Reset all spam trap offenses for {user.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HoneypotCog(bot))
    print("🚨 Honeypot system loaded!")
