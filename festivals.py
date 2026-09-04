import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import os
import random
import aiohttp
import re
from bs4 import BeautifulSoup
from datetime import datetime, time
import zoneinfo
import holidays
from gkr_ui import embed_success, embed_error, embed_info, C

DB_PATH = os.path.join(os.path.dirname(__file__), "festivals.sqlite3")
IST = zoneinfo.ZoneInfo("Asia/Kolkata")

class FestivalsDB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.cursor = self.conn.cursor()
        self.setup()

    def setup(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS announced_history (
                guild_id INTEGER,
                festival_name TEXT,
                year INTEGER,
                PRIMARY KEY (guild_id, festival_name, year)
            )
        ''')
        self.conn.commit()

    def get_channel(self, guild_id: int):
        self.cursor.execute("SELECT channel_id FROM guild_configs WHERE guild_id = ?", (guild_id,))
        res = self.cursor.fetchone()
        return res[0] if res else None

    def set_channel(self, guild_id: int, channel_id: int):
        self.cursor.execute("""
            INSERT INTO guild_configs (guild_id, channel_id) 
            VALUES (?, ?) 
            ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id
        """, (guild_id, channel_id))
        self.conn.commit()

    def delete_channel(self, guild_id: int):
        self.cursor.execute("DELETE FROM guild_configs WHERE guild_id = ?", (guild_id,))
        self.conn.commit()

    def get_all_configs(self):
        self.cursor.execute("SELECT guild_id, channel_id FROM guild_configs")
        return self.cursor.fetchall()

    def has_announced(self, guild_id: int, festival_name: str, year: int) -> bool:
        self.cursor.execute(
            "SELECT 1 FROM announced_history WHERE guild_id = ? AND festival_name = ? AND year = ?",
            (guild_id, festival_name, year)
        )
        return bool(self.cursor.fetchone())

    def mark_announced(self, guild_id: int, festival_name: str, year: int):
        self.cursor.execute(
            "INSERT OR IGNORE INTO announced_history (guild_id, festival_name, year) VALUES (?, ?, ?)",
            (guild_id, festival_name, year)
        )
        self.conn.commit()

class FestivalsCog(commands.GroupCog, name="festivals"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = FestivalsDB()
        self.announcement_task.start()
        self.bot.loop.create_task(self.startup_check())

    async def startup_check(self):
        await self.bot.wait_until_ready()
        # Initial check on bot start/restart to catch missed announcements
        await self.run_announcements()

    def cog_unload(self):
        self.announcement_task.cancel()

    def get_today_festivals(self):
        """Checks if today is a festival in IST using the holidays module"""
        now = datetime.now(IST)
        
        # Get all Indian + Kerala specific holidays for the current year
        in_holidays = holidays.country_holidays('IN', subdiv='KL', years=now.year)
        
        # Check if today is a holiday
        today_date = now.date()
        if today_date in in_holidays:
            # Some days have multiple holidays separated by semicolon (e.g. "Milad-un-Nabi; Onam")
            return [f.strip() for f in in_holidays[today_date].split(";")]
            
        return []
        
    async def build_festival_embed(self, festival_name: str) -> discord.Embed:
        message = ""
        image = ""
        color = random.choice([0xFFD700, 0xFF9933, 0xFFFF00, 0x138808, 0x008000, 0xFF0000, 0xFFFDD0, 0xFF8C00, 0x00A86B])
        
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Scrape Tenor for GIF
                query_gif = f"{festival_name} festival wishes".replace(' ', '-')
                async with session.get(f"https://tenor.com/search/{query_gif}-gifs", headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        gifs = re.findall(r'src="(https://media\.tenor\.com/[^"]+\.gif)"', html)
                        if gifs:
                            image = random.choice(gifs[:10]) # Pick from top 10 results
                            
                # 2. Scrape DuckDuckGo HTML for a quote
                query_text = f"{festival_name} festival wishes quotes in english"
                async with session.get(f"https://html.duckduckgo.com/html/?q={query_text}", headers={"User-Agent": "Mozilla/5.0"}) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        soup = BeautifulSoup(html, "html.parser")
                        snippets = soup.find_all("a", class_="result__snippet")
                        
                        seo_words = ['share', 'quotes', 'messages', 'captions', 'status', 'ideas', 'download', 'top', 'best', 'collection', '+']
                        valid_quotes = []
                        for s in snippets:
                            text = s.text.strip()
                            # Rigorous SEO filtering
                            if len(text) < 30 or len(text) > 300:
                                continue
                            if text.endswith('...'):
                                continue
                            if any(w in text.lower() for w in seo_words):
                                continue
                            valid_quotes.append(text)
                            
                        if valid_quotes:
                            message = random.choice(valid_quotes)
        except Exception as e:
            print(f"Scraping failed for {festival_name}: {e}")

        # Final Fallback if internet failed
        if not message:
            message = f"Wishing you a very Happy {festival_name}!"
            
        embed = discord.Embed(
            title=f"🎉 Happy {festival_name}! 🎉",
            description=message,
            color=color
        )
        if image:
            embed.set_image(url=image)
        embed.set_footer(text="GKR Automated Announcements | Content sourced dynamically from the web")
        return embed

    async def run_announcements(self):
        todays_festivals = self.get_today_festivals()
        
        if not todays_festivals:
            return
            
        configs = self.db.get_all_configs()
        if not configs:
            return
            
        current_year = datetime.now(IST).year
        
        for festival in todays_festivals:
            # Build embed once per festival to avoid spamming the scraper
            embed = None 
            
            for guild_id, channel_id in configs:
                # Check if this guild already got the announcement for this festival this year
                if not self.db.has_announced(guild_id, festival, current_year):
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        channel = guild.get_channel(channel_id)
                        if channel and isinstance(channel, discord.TextChannel):
                            if embed is None:
                                embed = await self.build_festival_embed(festival)
                                
                            try:
                                await channel.send(
                                    content="@everyone", 
                                    embed=embed, 
                                    allowed_mentions=discord.AllowedMentions(everyone=True)
                                )
                                self.db.mark_announced(guild_id, festival, current_year)
                            except Exception as e:
                                print(f"Failed to send festival announcement in {guild.name}: {e}")

    # Task to run every day at 8:00 AM IST
    @tasks.loop(time=time(hour=8, minute=0, tzinfo=IST))
    async def announcement_task(self):
        await self.bot.wait_until_ready()
        await self.run_announcements()

    @app_commands.command(name="setup", description="Setup automated festival announcements")
    @app_commands.describe(channel="The channel to send announcements in")
    @app_commands.default_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.db.set_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            embed=embed_success(
                "Announcements Enabled", 
                f"Festival announcements will now be sent in {channel.mention} at 8:00 AM IST on special days."
            ),
            ephemeral=True
        )
        # Immediately check for today's announcements so they don't miss it if they just set it up
        await self.run_announcements()

    @app_commands.command(name="disable", description="Disable automated festival announcements")
    @app_commands.default_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction):
        self.db.delete_channel(interaction.guild.id)
        await interaction.response.send_message(
            embed=embed_success("Announcements Disabled", "Festival announcements have been disabled for this server."),
            ephemeral=True
        )

    @app_commands.command(name="force_test", description="(Admin) Force trigger a festival announcement right now")
    @app_commands.describe(festival="The name of the festival to test (e.g. Onam)")
    @app_commands.default_permissions(administrator=True)
    async def force_test(self, interaction: discord.Interaction, festival: str):
        channel_id = self.db.get_channel(interaction.guild.id)
        if not channel_id:
            await interaction.response.send_message(
                embed=embed_error("Not Configured", "Please use `/festivals setup` first."),
                ephemeral=True
            )
            return
            
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await interaction.response.send_message("Configured channel not found.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        embed = await self.build_festival_embed(festival)
        await channel.send(
            content="@everyone", 
            embed=embed, 
            allowed_mentions=discord.AllowedMentions(everyone=True)
        )
        await interaction.followup.send(f"✅ Test announcement sent to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="next", description="See upcoming festivals and how many days are left")
    async def next(self, interaction: discord.Interaction):
        now = datetime.now(IST)
        today_date = now.date()
        
        in_holidays = holidays.country_holidays('IN', subdiv='KL', years=now.year)
        
        upcoming = []
        for hol_date, hol_names in in_holidays.items():
            if hol_date >= today_date:
                days_left = (hol_date - today_date).days
                for hol_name in hol_names.split(";"):
                    upcoming.append((hol_date, hol_name.strip(), days_left))
                    
        if not upcoming:
            await interaction.response.send_message("No upcoming festivals found for the rest of this year.", ephemeral=True)
            return
            
        upcoming.sort(key=lambda x: x[0])
        
        desc = "**Upcoming Festivals in India/Kerala:**\n\n"
        for date_obj, name, days in upcoming[:10]: # show next 10
            days_str = "Today!" if days == 0 else "Tomorrow!" if days == 1 else f"in {days} days"
            desc += f"📅 **{date_obj.strftime('%b %d, %Y')}** — {name} *( {days_str} )*\n"
            
        embed = discord.Embed(title="🗓️ Festival Calendar", description=desc, color=C.INFO)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FestivalsCog(bot))
    print("🎊 Fully Dynamic Web-Scraping Festivals system loaded!")
