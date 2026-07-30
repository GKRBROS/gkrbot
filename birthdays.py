"""
birthdays.py – Birthday tracking and automatic wishing system for GKR Bot.

Features:
  • Store birthday (day + month) per Discord user ID, per guild.
  • Daily task loop that fires at 00:00 UTC, checks today's birthdays,
    and posts a beautiful embed in the configured birthday channel.
  • Slash commands: /birthday add, /birthday list, /birthday remove, /birthday setchannel
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import os
import datetime
import asyncio
from typing import Optional


# ── Database ─────────────────────────────────────────────────────────────────

BIRTHDAY_DB_PATH = os.path.join(os.path.dirname(__file__), "birthdays.sqlite3")

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

BIRTHDAY_EMOJIS = ["🎂", "🎉", "🥳", "🎊", "🎈", "🎁", "✨", "🌟"]


class BirthdayDatabase:
    def __init__(self, db_path: str = BIRTHDAY_DB_PATH):
        self.db_path = db_path
        self._initialize()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _initialize(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS birthdays (
                    guild_id   INTEGER NOT NULL,
                    user_id    INTEGER NOT NULL,
                    username   TEXT    NOT NULL,
                    birth_day  INTEGER NOT NULL,
                    birth_month INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS birthday_channels (
                    guild_id   INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS global_state (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    last_checked_date TEXT
                )
            """)
            conn.execute("INSERT OR IGNORE INTO global_state (id) VALUES (1)")
            conn.commit()

    def get_last_checked_date(self) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("SELECT last_checked_date FROM global_state WHERE id = 1").fetchone()
        return row[0] if row else None

    def set_last_checked_date(self, date_str: str):
        with self._conn() as conn:
            conn.execute("UPDATE global_state SET last_checked_date = ? WHERE id = 1", (date_str,))
            conn.commit()

    # ── Birthday CRUD ─────────────────────────────────────────────────────────

    def add_birthday(self, guild_id: int, user_id: int, username: str,
                     day: int, month: int):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO birthdays (guild_id, user_id, username, birth_day, birth_month)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    username    = excluded.username,
                    birth_day   = excluded.birth_day,
                    birth_month = excluded.birth_month
            """, (guild_id, user_id, username, day, month))
            conn.commit()

    def remove_birthday(self, guild_id: int, user_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_birthday(self, guild_id: int, user_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT username, birth_day, birth_month FROM birthdays "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ).fetchone()
        if row:
            return {"username": row[0], "day": row[1], "month": row[2]}
        return None

    def get_all_birthdays(self, guild_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT user_id, username, birth_day, birth_month "
                "FROM birthdays WHERE guild_id = ? "
                "ORDER BY birth_month, birth_day",
                (guild_id,)
            ).fetchall()
        return [
            {"user_id": r[0], "username": r[1], "day": r[2], "month": r[3]}
            for r in rows
        ]

    def get_todays_birthdays(self, day: int, month: int) -> list[dict]:
        """Return all birthday entries across ALL guilds that match today."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT guild_id, user_id, username "
                "FROM birthdays WHERE birth_day = ? AND birth_month = ?",
                (day, month)
            ).fetchall()
        return [
            {"guild_id": r[0], "user_id": r[1], "username": r[2]}
            for r in rows
        ]

    # ── Channel config ────────────────────────────────────────────────────────

    def set_birthday_channel(self, guild_id: int, channel_id: int):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO birthday_channels (guild_id, channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
            """, (guild_id, channel_id))
            conn.commit()

    def get_birthday_channel(self, guild_id: int) -> Optional[int]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT channel_id FROM birthday_channels WHERE guild_id = ?",
                (guild_id,)
            ).fetchone()
        return row[0] if row else None


# ── Birthday GIF Generator ────────────────────────────────────────────────────
import io
import requests
from PIL import Image, ImageDraw, ImageFont, ImageSequence

def get_birthday_gif_with_name(name: str) -> io.BytesIO:
    # Use a solid birthday GIF (or download a random one)
    gif_url = "https://media.giphy.com/media/l4KibWpBGWchSqCRy/giphy.gif"
    try:
        resp = requests.get(gif_url, timeout=10)
        if resp.status_code != 200:
            return None
            
        im = Image.open(io.BytesIO(resp.content))
        frames = []
        
        try:
            font = ImageFont.truetype("arialbd.ttf", 40)
        except Exception:
            font = ImageFont.load_default()
            
        for frame in ImageSequence.Iterator(im):
            frame = frame.convert("RGBA")
            draw = ImageDraw.Draw(frame)
            
            text = f"Happy Birthday\n{name}!"
            bbox = draw.textbbox((0, 0), text, font=font, align="center")
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            
            x = (frame.width - text_w) / 2
            y = frame.height - text_h - 30
            
            # Draw shadow
            draw.text((x+2, y+2), text, font=font, fill="black", align="center")
            draw.text((x, y), text, font=font, fill="white", align="center")
            
            frames.append(frame)
            
        out = io.BytesIO()
        frames[0].save(
            out, 
            format="GIF", 
            save_all=True, 
            append_images=frames[1:], 
            loop=0, 
            duration=im.info.get("duration", 100)
        )
        out.seek(0)
        return out
    except Exception as e:
        print(f"Failed to generate birthday GIF: {e}")
        return None

# ── Birthday embed builder ────────────────────────────────────────────────────

def build_birthday_embed(member: discord.Member, day: int, month: int) -> discord.Embed:
    """Build a beautiful birthday announcement embed."""
    import random
    emoji = random.choice(BIRTHDAY_EMOJIS)
    month_name = MONTH_NAMES[month]

    embed = discord.Embed(
        title=f"{emoji}  Happy Birthday, {member.display_name}!  {emoji}",
        description=(
            f"🎂 **{member.mention}** is celebrating their birthday today!\n\n"
            f"🗓️ **{day} {month_name}**\n\n"
            "Wishing you an amazing day full of joy, laughter, and good vibes! 🥳✨\n"
            f"The {member.guild.name} family loves you! 💜"
        ),
        color=0x9B59B6,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(
        text=f"{member.guild.name} Birthday Wishes 🎊",
        icon_url=member.display_avatar.url
    )
    return embed


def build_birthday_list_embed(guild: discord.Guild, birthdays: list[dict]) -> discord.Embed:
    """Build a paginated-friendly embed listing all stored birthdays."""
    embed = discord.Embed(
        title="🎂  Birthday List",
        description=f"All registered birthdays in **{guild.name}**",
        color=0x9B59B6,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

    if not birthdays:
        embed.description = (
            f"No birthdays registered yet in **{guild.name}**.\n"
            "Use `/birthday add` to add one!"
        )
        return embed

    lines = []
    today = datetime.date.today()

    for entry in birthdays:
        month_name = MONTH_NAMES[entry["month"]]
        member = guild.get_member(entry["user_id"])
        display = member.mention if member else f"@{entry['username']}"

        # Mark today's birthday
        is_today = (entry["day"] == today.day and entry["month"] == today.month)
        star = " 🎉 **TODAY!**" if is_today else ""

        lines.append(f"**{entry['day']} {month_name}** — {display}{star}")

    # Split into chunks if many birthdays to respect embed field limits
    chunk_size = 15
    for i in range(0, len(lines), chunk_size):
        chunk = lines[i:i + chunk_size]
        field_name = "🗓️ Birthdays" if i == 0 else "\u200b"
        embed.add_field(name=field_name, value="\n".join(chunk), inline=False)

    embed.set_footer(text=f"Total: {len(birthdays)} birthday(s) registered  •  GKR Bot")
    return embed


# ── Cog ───────────────────────────────────────────────────────────────────────

class BirthdayCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = BirthdayDatabase()
        self._wish_loop_started = False
        self._last_checked_date = None

    # ── Task loop ─────────────────────────────────────────────────────────────

    @tasks.loop(hours=1)
    async def check_birthdays(self):
        """Every hour, check if it is anyone's birthday. Tracks the date persistently to ensure it fires once per day."""
        # Convert to Indian Standard Time (IST) UTC+05:30
        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now = datetime.datetime.now(ist)
        current_date_str = now.date().isoformat()
        
        # If we already sent wishes for today (persisted in DB), do nothing.
        last_checked = self.db.get_last_checked_date()
        if last_checked == current_date_str:
            return
            
        self.db.set_last_checked_date(current_date_str)
        await self._send_birthday_wishes(now.day, now.month)

    async def _send_birthday_wishes(self, day: int, month: int):
        """Find today's birthdays and send wishes in each guild's birthday channel."""
        entries = self.db.get_todays_birthdays(day, month)
        if not entries:
            return

        print(f"🎂 Birthday check: {len(entries)} birthday(s) found for {day}/{month}")

        for entry in entries:
            guild = self.bot.get_guild(entry["guild_id"])
            if not guild:
                continue

            channel_id = self.db.get_birthday_channel(guild.id)
            if not channel_id:
                print(f"⚠️ No birthday channel set for guild: {guild.name}")
                continue

            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                print(f"⚠️ Birthday channel not found in guild: {guild.name}")
                continue

            member = guild.get_member(entry["user_id"])
            if not member:
                try:
                    member = await guild.fetch_member(entry["user_id"])
                except Exception:
                    print(f"⚠️ Could not find member {entry['user_id']} in {guild.name}")
                    continue

            try:
                embed = build_birthday_embed(member, day, month)
                
                # Generate custom GIF
                gif_bytes = get_birthday_gif_with_name(member.display_name)
                
                if gif_bytes:
                    file = discord.File(gif_bytes, filename="birthday.gif")
                    embed.set_image(url="attachment://birthday.gif")
                    await channel.send(content="@everyone", embed=embed, file=file)
                else:
                    await channel.send(content="@everyone", embed=embed)
                    
                print(f"🎉 Sent birthday wish for {member.display_name} in {guild.name}")
            except Exception as e:
                print(f"❌ Failed to send birthday wish in {guild.name}: {e}")

    @check_birthdays.before_loop
    async def before_check_birthdays(self):
        await self.bot.wait_until_ready()

    def cog_load(self):
        if not self.check_birthdays.is_running():
            self.check_birthdays.start()
            print("🎂 Birthday check loop started!")

    def cog_unload(self):
        self.check_birthdays.cancel()

    # ── Slash commands ────────────────────────────────────────────────────────

    birthday_group = app_commands.Group(
        name="birthday",
        description="Birthday tracking commands"
    )

    @birthday_group.command(name="add", description="Add or update a birthday")
    @app_commands.describe(
        day="Day of birth (1–31)",
        month="Month of birth (1–12)",
        user="Admin only: Set someone else's birthday"
    )
    async def birthday_add(
        self,
        interaction: discord.Interaction,
        day: int,
        month: int,
        user: Optional[discord.Member] = None
    ):
        """Add or update a birthday entry."""
        target_user = user or interaction.user
        
        # Require manage_guild if setting someone else's birthday
        if target_user != interaction.user and not interaction.permissions.manage_guild:
            await interaction.response.send_message("❌ You need Manage Server permissions to set someone else's birthday!", ephemeral=True)
            return
        if not (1 <= day <= 31):
            await interaction.response.send_message(
                "❌ Day must be between **1** and **31**.", ephemeral=True
            )
            return
        if not (1 <= month <= 12):
            await interaction.response.send_message(
                "❌ Month must be between **1** and **12**.", ephemeral=True
            )
            return

        # Basic validation: reject impossible dates
        try:
            datetime.date(2000, month, day)  # Use a leap year for Feb 29
        except ValueError:
            await interaction.response.send_message(
                f"❌ **{day}/{month}** is not a valid date.", ephemeral=True
            )
            return

        self.db.add_birthday(
            guild_id=interaction.guild.id,
            user_id=target_user.id,
            username=target_user.display_name,
            day=day,
            month=month
        )

        month_name = MONTH_NAMES[month]
        embed = discord.Embed(
            title="🎂  Birthday Added!",
            description=(
                f"Successfully stored the birthday for {target_user.mention}!\n\n"
                f"🗓️ **Date:** {day} {month_name}"
            ),
            color=0x9B59B6,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"Added by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed, ephemeral=False)

    @birthday_group.command(name="remove", description="Remove a birthday")
    @app_commands.describe(user="Admin only: The user whose birthday to remove")
    async def birthday_remove(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Remove a birthday entry."""
        target_user = user or interaction.user
        
        if target_user != interaction.user and not interaction.permissions.manage_guild:
            await interaction.response.send_message("❌ You need Manage Server permissions to remove someone else's birthday!", ephemeral=True)
            return

        deleted = self.db.remove_birthday(interaction.guild.id, target_user.id)
        if deleted:
            await interaction.response.send_message(
                f"✅ Successfully removed the birthday entry for {target_user.mention}.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ No birthday entry found for {target_user.mention}.",
                ephemeral=True
            )

    @birthday_group.command(name="list", description="Show all registered birthdays in this server")
    async def birthday_list(self, interaction: discord.Interaction):
        """Display the full birthday list for this guild."""
        birthdays = self.db.get_all_birthdays(interaction.guild.id)
        embed = build_birthday_list_embed(interaction.guild, birthdays)
        await interaction.response.send_message(embed=embed)

    @birthday_group.command(name="check", description="Check a specific user's stored birthday")
    @app_commands.describe(user="The Discord user to look up")
    async def birthday_check(self, interaction: discord.Interaction, user: discord.Member):
        """Look up a specific user's birthday."""
        entry = self.db.get_birthday(interaction.guild.id, user.id)
        if not entry:
            await interaction.response.send_message(
                f"⚠️ No birthday stored for {user.mention}.", ephemeral=True
            )
            return

        month_name = MONTH_NAMES[entry["month"]]
        embed = discord.Embed(
            title=f"🗓️  Birthday Info — {user.display_name}",
            description=f"**Date:** {entry['day']} {month_name}",
            color=0x9B59B6
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @birthday_group.command(
        name="setchannel",
        description="Set the channel where birthday wishes will be sent"
    )
    @app_commands.describe(channel="The text channel for birthday announcements")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def birthday_setchannel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Configure the birthday announcement channel for this guild."""
        self.db.set_birthday_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"✅ Birthday announcements will now be sent to {channel.mention}! 🎂",
            ephemeral=True
        )

    @birthday_group.command(
        name="testwish",
        description="Manually trigger a birthday wish for a user (for testing)"
    )
    @app_commands.describe(user="The user to test the birthday wish for")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def birthday_testwish(self, interaction: discord.Interaction, user: discord.Member):
        """Test the birthday wish system by sending a wish immediately."""
        channel_id = self.db.get_birthday_channel(interaction.guild.id)
        if not channel_id:
            await interaction.response.send_message(
                "❌ No birthday channel set! Use `/birthday setchannel` first.",
                ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Birthday channel not found. Please re-set it with `/birthday setchannel`.",
                ephemeral=True
            )
            return

        today = datetime.date.today()
        embed = build_birthday_embed(user, today.day, today.month)

        await channel.send(content="@everyone", embed=embed)
        await interaction.response.send_message(
            f"✅ Test birthday wish sent for {user.mention} in {channel.mention}!",
            ephemeral=True
        )


# ── Setup helper ──────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    """Add the BirthdayCog to the bot and start the birthday check loop."""
    await bot.add_cog(BirthdayCog(bot))
    print("🎂 Birthday system loaded!")
