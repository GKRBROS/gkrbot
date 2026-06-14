import os
import io
import aiohttp
import sqlite3
from PIL import Image, ImageDraw, ImageFont, ImageOps
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Tuple
from dataclasses import dataclass

DB_PATH = os.path.join(os.path.dirname(__file__), "font_sync.sqlite3")
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "welcome_assets")

FONT_BOLD_URL = "https://github.com/google/fonts/raw/main/ofl/outfit/Outfit-Bold.ttf"
FONT_REGULAR_URL = "https://github.com/google/fonts/raw/main/ofl/outfit/Outfit-Regular.ttf"

FONT_BOLD_PATH = os.path.join(ASSETS_DIR, "Outfit-Bold.ttf")
FONT_REGULAR_PATH = os.path.join(ASSETS_DIR, "Outfit-Regular.ttf")

# Ensure assets directory exists
os.makedirs(ASSETS_DIR, exist_ok=True)


@dataclass
class WelcomeConfig:
    guild_id: int
    enabled: bool = True
    channel_id: Optional[int] = None
    welcome_message: str = "**Welcome to FAMILY** 🎉\n\nWelcome to **{server}** – Where Friends Become Family! 🎉\n\nHey besties! 👋 This is your ultimate hangout spot for memes, gaming, late-night talks, and everything in between.\n\nWhether we're roasting each other, sharing life updates, or just vibing — this server is our digital home."
    background_path: Optional[str] = None


class WelcomeDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS welcome_configs (
                    guild_id        TEXT PRIMARY KEY,
                    enabled         INTEGER NOT NULL DEFAULT 1,
                    channel_id      TEXT,
                    welcome_message TEXT NOT NULL DEFAULT 'Welcome {member} to {server}! 🎉',
                    background_path TEXT
                )
                """
            )
            conn.commit()

        # One-time migration: replace any literal \n in stored messages
        with self._connect() as conn:
            rows = conn.execute("SELECT guild_id, welcome_message FROM welcome_configs").fetchall()
            for row in rows:
                if "\\n" in row["welcome_message"]:
                    fixed = row["welcome_message"].replace("\\n", "\n")
                    conn.execute(
                        "UPDATE welcome_configs SET welcome_message = ? WHERE guild_id = ?",
                        (fixed, row["guild_id"]),
                    )
            conn.commit()

    def get_config(self, guild_id: int) -> WelcomeConfig:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM welcome_configs WHERE guild_id = ?",
                (str(guild_id),),
            ).fetchone()

        if not row:
            return WelcomeConfig(guild_id=guild_id)

        # Decode stored \n escape sequences into real newlines so Discord
        # renders line breaks correctly in embed descriptions.
        raw_msg = row["welcome_message"]
        decoded_msg = raw_msg.replace("\\n", "\n")

        return WelcomeConfig(
            guild_id=guild_id,
            enabled=bool(row["enabled"]),
            channel_id=int(row["channel_id"]) if row["channel_id"] else None,
            welcome_message=decoded_msg,
            background_path=row["background_path"],
        )

    def save_config(self, config: WelcomeConfig) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO welcome_configs (
                    guild_id, enabled, channel_id, welcome_message, background_path
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled         = excluded.enabled,
                    channel_id      = excluded.channel_id,
                    welcome_message = excluded.welcome_message,
                    background_path = excluded.background_path
                """,
                (
                    str(config.guild_id),
                    1 if config.enabled else 0,
                    str(config.channel_id) if config.channel_id else None,
                    config.welcome_message,
                    config.background_path,
                ),
            )
            conn.commit()


# Helper to download fonts
async def download_fonts() -> None:
    async with aiohttp.ClientSession() as session:
        for url, path in [(FONT_BOLD_URL, FONT_BOLD_PATH), (FONT_REGULAR_URL, FONT_REGULAR_PATH)]:
            if not os.path.exists(path):
                print(f"[Welcome] Downloading font from {url}...")
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            with open(path, "wb") as f:
                                f.write(await resp.read())
                            print(f"[Welcome] Font saved to {path}")
                        else:
                            print(f"[Welcome] Failed to download font: HTTP {resp.status}")
                except Exception as exc:
                    print(f"[Welcome] Failed to download font: {exc}")


def generate_default_bg() -> Image.Image:
    # Create deep dark purple/black gradient background
    base = Image.new("RGBA", (1024, 500), (15, 10, 20, 255))
    draw = ImageDraw.Draw(base)
    for y in range(500):
        # Deep crimson red to dark space black gradient
        r = int(35 - (25 * (y / 500)))
        g = int(10 - (8 * (y / 500)))
        b = int(15 - (10 * (y / 500)))
        draw.line([(0, y), (1024, y)], fill=(r, g, b, 255))
    return base


def make_circle_avatar(avatar_image: Image.Image, size: int = 220, border_color: Tuple[int, int, int] = (255, 40, 40), border_width: int = 7) -> Image.Image:
    # Resize and crop to square
    avatar_image = avatar_image.convert("RGBA")
    avatar_image = ImageOps.fit(avatar_image, (size, size), Image.Resampling.LANCZOS)

    # Circular mask
    mask = Image.new("L", (size, size), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, size, size), fill=255)

    # Circular avatar
    circle_avatar = Image.new("RGBA", (size, size))
    circle_avatar.paste(avatar_image, (0, 0), mask=mask)

    # Border frame
    total_size = size + (border_width * 2)
    bordered = Image.new("RGBA", (total_size, total_size), (0, 0, 0, 0))
    draw_border = ImageDraw.Draw(bordered)
    draw_border.ellipse((0, 0, total_size, total_size), fill=border_color)
    bordered.paste(circle_avatar, (border_width, border_width), mask=circle_avatar)
    
    return bordered


def render_welcome_card(
    avatar_bytes: bytes,
    username: str,
    member_count: int,
    background_path: Optional[str] = None
) -> io.BytesIO:
    W, H = 1024, 500

    # Load background or fallback
    if background_path and os.path.exists(background_path):
        try:
            bg = Image.open(background_path).convert("RGBA")
            bg = ImageOps.fit(bg, (W, H), Image.Resampling.LANCZOS)
        except Exception:
            bg = generate_default_bg()
    else:
        bg = generate_default_bg()

    # Draw a dark overlay for legibility
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 130))
    bg = Image.alpha_composite(bg, overlay)

    draw = ImageDraw.Draw(bg)

    # --- Avatar ---
    try:
        avatar_img = Image.open(io.BytesIO(avatar_bytes))
    except Exception:
        avatar_img = Image.new("RGBA", (220, 220), (120, 120, 120, 255))

    circle_avatar = make_circle_avatar(avatar_img)  # 220 + 7*2 = 234px
    avatar_w, avatar_h = circle_avatar.size
    avatar_x = (W - avatar_w) // 2
    avatar_y = 30
    bg.paste(circle_avatar, (avatar_x, avatar_y), mask=circle_avatar)

    # --- Fonts ---
    try:
        # Large: username (bold, big)
        font_username = ImageFont.truetype(FONT_BOLD_PATH, 72)
        # Medium: WELCOME label
        font_welcome = ImageFont.truetype(FONT_BOLD_PATH, 52)
        # Small: member count
        font_count = ImageFont.truetype(FONT_REGULAR_PATH, 34)
    except Exception:
        font_username = ImageFont.load_default()
        font_welcome = ImageFont.load_default()
        font_count = ImageFont.load_default()

    # --- Layout: text starts below avatar ---
    # Avatar bottom edge = avatar_y + avatar_h  (approx 30 + 234 = 264)
    text_start_y = avatar_y + avatar_h + 18  # a little breathing room

    # Draw WELCOME Title first (above username)
    draw.text(
        (W // 2, text_start_y),
        "WELCOME",
        font=font_welcome,
        fill=(255, 255, 255, 255),
        anchor="mt",
        stroke_width=3,
        stroke_fill=(0, 0, 0, 255),
    )

    # Measure WELCOME height to position username below it
    welcome_bbox = draw.textbbox((0, 0), "WELCOME", font=font_welcome)
    welcome_h = welcome_bbox[3] - welcome_bbox[1]

    username_y = text_start_y + welcome_h + 8
    username_clean = username.upper()
    draw.text(
        (W // 2, username_y),
        username_clean,
        font=font_username,
        fill=(255, 40, 40, 255),
        anchor="mt",
        stroke_width=4,
        stroke_fill=(0, 0, 0, 255),
    )

    # Measure username height to position member count below it
    user_bbox = draw.textbbox((0, 0), username_clean, font=font_username)
    user_h = user_bbox[3] - user_bbox[1]

    count_y = username_y + user_h + 10
    count_text = f"YOU ARE OUR {member_count}{'th' if 11 <= (member_count % 100) <= 13 else ['th','st','nd','rd','th'][min(member_count % 10, 4)]} MEMBER!"
    # Clamp count_y so it doesn't go below the card
    count_y = min(count_y, H - 50)
    draw.text(
        (W // 2, count_y),
        count_text,
        font=font_count,
        fill=(200, 200, 200, 255),
        anchor="mt",
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255),
    )

    # Export to BytesIO
    output = io.BytesIO()
    bg.convert("RGB").save(output, format="JPEG", quality=92)
    output.seek(0)
    return output


async def send_welcome(member: discord.Member, config: WelcomeConfig) -> None:
    if not config.enabled or not config.channel_id:
        return

    channel = member.guild.get_channel(config.channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
        return

    # Fetch avatar
    try:
        avatar_bytes = await member.display_avatar.read()
    except Exception:
        avatar_bytes = b""

    member_count = member.guild.member_count

    # Render card
    card_file_bytes = render_welcome_card(
        avatar_bytes=avatar_bytes,
        username=member.name,
        member_count=member_count,
        background_path=config.background_path
    )

    # Format custom message inside the embed box description
    description_text = config.welcome_message.format(
        member=member.mention,
        server=member.guild.name,
        member_count=member_count
    )

    discord_file = discord.File(card_file_bytes, filename=f"welcome_{member.id}.jpg")
    
    # Construct premium Embed matching the screenshot
    embed = discord.Embed(
        title="WELCOME",
        description=description_text,
        color=0xFF2828  # Red matching the sidebar
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=f"attachment://welcome_{member.id}.jpg")
    embed.set_footer(text=f"© {member.guild.name} • {discord.utils.utcnow().strftime('%m-%d-%Y %I:%M %p')}", icon_url=member.guild.icon.url if member.guild.icon else None)

    # Short mention text outside the embed
    content = f"Welcome {member.mention}!"
    await channel.send(content=content, embed=embed, file=discord_file)


# Slash command setup
def setup_welcome(bot: commands.Bot, guild_id: int) -> None:
    db = WelcomeDatabase()
    db.initialize()

    # Pre-download fonts when the bot is ready and the loop is running
    @bot.listen("on_ready")
    async def on_welcome_ready():
        await download_fonts()

    welcome_group = app_commands.Group(name="welcome", description="Manage Server Welcome messages & cards")

    @welcome_group.command(name="status", description="Show the current welcome settings configuration")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(interaction: discord.Interaction) -> None:
        config = db.get_config(interaction.guild.id)
        embed = discord.Embed(
            title="👋 Welcome System Settings",
            description="Displaying config for member join welcome greetings.",
            color=0x00FF88 if config.enabled else 0x808080
        )
        embed.add_field(name="Enabled", value="Yes" if config.enabled else "No", inline=True)
        
        channel_val = "Not Set"
        if config.channel_id:
            chan = interaction.guild.get_channel(config.channel_id)
            if chan:
                channel_val = chan.mention
        embed.add_field(name="Welcome Channel", value=channel_val, inline=True)
        embed.add_field(name="Message Text", value=f"`{config.welcome_message}`", inline=False)
        
        bg_status = "Default Dark Theme"
        if config.background_path and os.path.exists(config.background_path):
            bg_status = "Custom Background Image"
        embed.add_field(name="Card Background", value=bg_status, inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @welcome_group.command(name="toggle", description="Toggle the welcome greeting system on or off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def toggle(interaction: discord.Interaction) -> None:
        config = db.get_config(interaction.guild.id)
        config.enabled = not config.enabled
        db.save_config(config)
        status_str = "ENABLED" if config.enabled else "DISABLED"
        await interaction.response.send_message(f"✅ Welcome system is now **{status_str}**.", ephemeral=True)

    @welcome_group.command(name="channel", description="Set the channel where welcome greetings will be posted")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        config = db.get_config(interaction.guild.id)
        config.channel_id = channel.id
        db.save_config(config)
        await interaction.response.send_message(f"✅ Welcome channel successfully set to {channel.mention}.", ephemeral=True)

    @welcome_group.command(name="message", description="Set a custom message text to send alongside the welcome card")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_message(interaction: discord.Interaction, message: str) -> None:
        config = db.get_config(interaction.guild.id)
        # Decode any \n the user typed so they become real newlines in the embed
        decoded = message.replace("\\n", "\n")
        config.welcome_message = decoded
        db.save_config(config)
        preview = decoded[:200] + "..." if len(decoded) > 200 else decoded
        await interaction.response.send_message(f"✅ Welcome message set:\n>>> {preview}", ephemeral=True)

    @welcome_group.command(name="setbg", description="Upload a custom background image (Recommended 1024x500)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_bg(interaction: discord.Interaction, image: discord.Attachment) -> None:
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message("❌ Uploaded file must be an image.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            bg_data = await image.read()
            # Test loading image to verify it's valid
            img = Image.open(io.BytesIO(bg_data))
            img.verify()

            # Save locally
            filename = f"bg_{interaction.guild.id}.png"
            dest_path = os.path.join(ASSETS_DIR, filename)
            with open(dest_path, "wb") as f:
                f.write(bg_data)

            config = db.get_config(interaction.guild.id)
            config.background_path = dest_path
            db.save_config(config)

            await interaction.followup.send("✅ Custom background image successfully updated!", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to process uploaded image: {exc}", ephemeral=True)

    @welcome_group.command(name="test", description="Simulate a welcome card message inside the setup channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test_welcome(interaction: discord.Interaction) -> None:
        config = db.get_config(interaction.guild.id)
        if not config.channel_id:
            await interaction.response.send_message("❌ Please set a welcome channel first using `/welcome channel`.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await send_welcome(interaction.user, config)
            await interaction.followup.send("✅ Test welcome message dispatched successfully!", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to run welcome test: {exc}", ephemeral=True)

    # Register command group
    bot.tree.add_command(welcome_group, guild=discord.Object(id=guild_id))
