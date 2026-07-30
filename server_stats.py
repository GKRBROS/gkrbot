import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import os
import asyncio

DB_PATH = os.path.join(os.path.dirname(__file__), "server_stats.sqlite3")

class StatsDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS server_stats (
                    guild_id TEXT PRIMARY KEY,
                    category_id TEXT,
                    total_channel_id TEXT,
                    humans_channel_id TEXT,
                    bots_channel_id TEXT
                )
            """)
            conn.commit()

    def get_config(self, guild_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM server_stats WHERE guild_id = ?", (str(guild_id),)).fetchone()
            if row:
                return dict(row)
        return None

    def set_config(self, guild_id: int, cat_id: int, total_id: int, humans_id: int, bots_id: int) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO server_stats (guild_id, category_id, total_channel_id, humans_channel_id, bots_channel_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    category_id = excluded.category_id,
                    total_channel_id = excluded.total_channel_id,
                    humans_channel_id = excluded.humans_channel_id,
                    bots_channel_id = excluded.bots_channel_id
            """, (str(guild_id), str(cat_id), str(total_id), str(humans_id), str(bots_id)))
            conn.commit()

    def remove_config(self, guild_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM server_stats WHERE guild_id = ?", (str(guild_id),))
            conn.commit()


class ServerStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = StatsDB()
        self.update_stats_task.start()
        
    def cog_unload(self):
        self.update_stats_task.cancel()

    stats_group = app_commands.Group(name="stats", description="Configure server stats channels")

    @stats_group.command(name="setup", description="Create Server Stats category and channels")
    @app_commands.default_permissions(manage_guild=True)
    async def setup_stats(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)
        
        # Check if already setup
        existing = self.db.get_config(guild.id)
        if existing:
            await interaction.followup.send("⚠️ Stats channels are already set up for this server! Use `/stats remove` if you want to recreate them.", ephemeral=True)
            return

        # Calculate initial stats
        total = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        humans = total - bots
        
        # Create permissions (deny connect for everyone)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)
        }
        
        try:
            # Create category
            category = await guild.create_category(name="📊 Server Stats", overwrites=overwrites)
            
            # Create voice channels
            total_ch = await guild.create_voice_channel(name=f"👥 Total Members: {total}", category=category)
            humans_ch = await guild.create_voice_channel(name=f"🧑 Humans: {humans}", category=category)
            bots_ch = await guild.create_voice_channel(name=f"🤖 Bots: {bots}", category=category)
            
            # Save to DB
            self.db.set_config(guild.id, category.id, total_ch.id, humans_ch.id, bots_ch.id)
            
            await interaction.followup.send("✅ Server stats category and channels created successfully! They will automatically update every 10 minutes to respect Discord rate limits.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I do not have permission to create channels!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

    @stats_group.command(name="remove", description="Remove the Server Stats category and channels")
    @app_commands.default_permissions(manage_guild=True)
    async def remove_stats(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)
        
        cfg = self.db.get_config(guild.id)
        if not cfg:
            await interaction.followup.send("⚠️ Stats channels are not set up on this server.", ephemeral=True)
            return
            
        try:
            for ch_id in [cfg['total_channel_id'], cfg['humans_channel_id'], cfg['bots_channel_id'], cfg['category_id']]:
                if ch_id:
                    channel = guild.get_channel(int(ch_id))
                    if channel:
                        await channel.delete()
                        
            self.db.remove_config(guild.id)
            await interaction.followup.send("✅ Server stats channels removed.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I do not have permission to delete the channels!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

    @tasks.loop(minutes=10.0)
    async def update_stats_task(self):
        """Update the channel names periodically. Discord rate limits channel renames to 2 per 10 minutes."""
        for guild in self.bot.guilds:
            cfg = self.db.get_config(guild.id)
            if not cfg:
                continue
                
            total = guild.member_count
            bots = sum(1 for m in guild.members if m.bot)
            humans = total - bots
            
            # Fetch channels
            total_ch = guild.get_channel(int(cfg['total_channel_id'])) if cfg['total_channel_id'] else None
            humans_ch = guild.get_channel(int(cfg['humans_channel_id'])) if cfg['humans_channel_id'] else None
            bots_ch = guild.get_channel(int(cfg['bots_channel_id'])) if cfg['bots_channel_id'] else None
            
            # Update names if needed
            try:
                if total_ch and str(total) not in total_ch.name:
                    await total_ch.edit(name=f"👥 Total Members: {total}")
                if humans_ch and str(humans) not in humans_ch.name:
                    await humans_ch.edit(name=f"🧑 Humans: {humans}")
                if bots_ch and str(bots) not in bots_ch.name:
                    await bots_ch.edit(name=f"🤖 Bots: {bots}")
            except Exception as e:
                print(f"[Server Stats] Failed to update stats for guild {guild.id}: {e}")

    @update_stats_task.before_loop
    async def before_update_stats(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatsCog(bot))
    print("📊 Server Stats system loaded!")
