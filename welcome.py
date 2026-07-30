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
    show_avatar: bool = True       # Embed thumbnail toggle
    show_guild_icon: bool = False   # Server icon drawing toggle
    draw_avatar: bool = True        # User avatar drawing toggle
    draw_text: bool = True          # Text overlay drawing toggle
    welcome_role_id: Optional[int] = None # Auto-assign role on join
    bot_role_id: Optional[int] = None # Auto-assign role for bots on join
    
    # Leave settings
    leave_enabled: bool = False
    leave_channel_id: Optional[int] = None
    leave_message: str = "**{user}** left the server."
    leave_image_url: Optional[str] = None


def load_font(font_path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        # Fallback list of common system fonts on Windows and Linux
        fallbacks = [
            "arial.ttf",
            "DejaVuSans-Bold.ttf" if "Bold" in font_path else "DejaVuSans.ttf",
            "LiberationSans-Bold.ttf" if "Bold" in font_path else "LiberationSans.ttf",
            "Helvetica.ttf",
            "Tahoma.ttf"
        ]
        for f in fallbacks:
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
        # If all else fails, use load_default
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


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
                    background_path TEXT,
                    show_avatar     INTEGER NOT NULL DEFAULT 1,
                    show_guild_icon INTEGER NOT NULL DEFAULT 0,
                    draw_avatar     INTEGER NOT NULL DEFAULT 1,
                    draw_text       INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.commit()

        # Schema migrations for existing databases
        with self._connect() as conn:
            cursor = conn.execute("PRAGMA table_info(welcome_configs)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "show_avatar" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN show_avatar INTEGER NOT NULL DEFAULT 1")
            if "show_guild_icon" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN show_guild_icon INTEGER NOT NULL DEFAULT 0")
            if "draw_avatar" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN draw_avatar INTEGER NOT NULL DEFAULT 1")
            if "draw_text" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN draw_text INTEGER NOT NULL DEFAULT 1")
            if "welcome_role_id" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN welcome_role_id TEXT")
            if "bot_role_id" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN bot_role_id TEXT")
            if "leave_enabled" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN leave_enabled INTEGER NOT NULL DEFAULT 0")
            if "leave_channel_id" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN leave_channel_id TEXT")
            if "leave_message" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN leave_message TEXT NOT NULL DEFAULT '**{user}** left the server.'")
            if "leave_image_url" not in columns:
                conn.execute("ALTER TABLE welcome_configs ADD COLUMN leave_image_url TEXT")
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

        show_avatar = True
        show_guild_icon = False
        draw_avatar = True
        draw_text = True
        try:
            if "show_avatar" in row.keys():
                show_avatar = bool(row["show_avatar"])
            if "show_guild_icon" in row.keys():
                show_guild_icon = bool(row["show_guild_icon"])
            if "draw_avatar" in row.keys():
                draw_avatar = bool(row["draw_avatar"])
            if "draw_text" in row.keys():
                draw_text = bool(row["draw_text"])
        except Exception:
            pass

        return WelcomeConfig(
            guild_id=guild_id,
            enabled=bool(row["enabled"]),
            channel_id=int(row["channel_id"]) if row["channel_id"] else None,
            welcome_message=decoded_msg,
            background_path=row["background_path"],
            show_avatar=show_avatar,
            show_guild_icon=show_guild_icon,
            draw_avatar=draw_avatar,
            draw_text=draw_text,
            welcome_role_id=int(row["welcome_role_id"]) if "welcome_role_id" in row.keys() and row["welcome_role_id"] else None,
            bot_role_id=int(row["bot_role_id"]) if "bot_role_id" in row.keys() and row["bot_role_id"] else None,
            leave_enabled=bool(row["leave_enabled"]) if "leave_enabled" in row.keys() else False,
            leave_channel_id=int(row["leave_channel_id"]) if "leave_channel_id" in row.keys() and row["leave_channel_id"] else None,
            leave_message=row["leave_message"].replace("\\n", "\n") if "leave_message" in row.keys() else "**{user}** left the server.",
            leave_image_url=row["leave_image_url"] if "leave_image_url" in row.keys() else None,
        )

    def save_config(self, config: WelcomeConfig) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO welcome_configs (
                    guild_id, enabled, channel_id, welcome_message, background_path, show_avatar, show_guild_icon, draw_avatar, draw_text, welcome_role_id, bot_role_id,
                    leave_enabled, leave_channel_id, leave_message, leave_image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled         = excluded.enabled,
                    channel_id      = excluded.channel_id,
                    welcome_message = excluded.welcome_message,
                    background_path = excluded.background_path,
                    show_avatar     = excluded.show_avatar,
                    show_guild_icon = excluded.show_guild_icon,
                    draw_avatar     = excluded.draw_avatar,
                    draw_text       = excluded.draw_text,
                    welcome_role_id = excluded.welcome_role_id,
                    bot_role_id     = excluded.bot_role_id,
                    leave_enabled    = excluded.leave_enabled,
                    leave_channel_id = excluded.leave_channel_id,
                    leave_message    = excluded.leave_message,
                    leave_image_url  = excluded.leave_image_url
                """,
                (
                    str(config.guild_id),
                    1 if config.enabled else 0,
                    str(config.channel_id) if config.channel_id else None,
                    config.welcome_message,
                    config.background_path,
                    1 if config.show_avatar else 0,
                    1 if config.show_guild_icon else 0,
                    1 if config.draw_avatar else 0,
                    1 if config.draw_text else 0,
                    str(config.welcome_role_id) if config.welcome_role_id else None,
                    str(config.bot_role_id) if config.bot_role_id else None,
                    1 if config.leave_enabled else 0,
                    str(config.leave_channel_id) if config.leave_channel_id else None,
                    config.leave_message,
                    config.leave_image_url,
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
    guild_icon_bytes: bytes,
    username: str,
    member_count: int,
    background_path: Optional[str] = None,
    draw_avatar: bool = True,
    show_guild_icon: bool = False,
    draw_text: bool = True
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

    # --- Avatar & Server Icon Layout ---
    avatar_img = None
    if draw_avatar and avatar_bytes:
        try:
            avatar_img = Image.open(io.BytesIO(avatar_bytes))
        except Exception:
            avatar_img = Image.new("RGBA", (220, 220), (120, 120, 120, 255))

    guild_icon_img = None
    if show_guild_icon and guild_icon_bytes:
        try:
            guild_icon_img = Image.open(io.BytesIO(guild_icon_bytes))
        except Exception:
            guild_icon_img = Image.new("RGBA", (220, 220), (120, 120, 120, 255))

    # Prepare circular items
    avatar_w, avatar_h = 0, 0
    circle_avatar = None
    if avatar_img:
        circle_avatar = make_circle_avatar(avatar_img)
        avatar_w, avatar_h = circle_avatar.size

    icon_w, icon_h = 0, 0
    circle_icon = None
    if guild_icon_img:
        circle_icon = make_circle_avatar(guild_icon_img, border_color=(255, 255, 255)) # White border for server icon
        icon_w, icon_h = circle_icon.size

    avatar_y = 30
    icon_y = 30
    
    if circle_avatar and circle_icon:
        # Both shown side-by-side
        gap = 40
        total_width = avatar_w + icon_w + gap
        start_x = (W - total_width) // 2
        
        avatar_x = start_x
        icon_x = start_x + avatar_w + gap
        
        bg.paste(circle_avatar, (avatar_x, avatar_y), mask=circle_avatar)
        bg.paste(circle_icon, (icon_x, icon_y), mask=circle_icon)
        text_start_y = avatar_y + max(avatar_h, icon_h) + 18
    elif circle_avatar:
        # Only avatar
        avatar_x = (W - avatar_w) // 2
        bg.paste(circle_avatar, (avatar_x, avatar_y), mask=circle_avatar)
        text_start_y = avatar_y + avatar_h + 18
    elif circle_icon:
        # Only server icon
        icon_x = (W - icon_w) // 2
        bg.paste(circle_icon, (icon_x, icon_y), mask=circle_icon)
        text_start_y = icon_y + icon_h + 18
    else:
        # Neither
        text_start_y = 80

    if draw_text:
        # --- Fonts ---
        font_username = load_font(FONT_BOLD_PATH, 72)
        font_welcome = load_font(FONT_BOLD_PATH, 52)
        font_count = load_font(FONT_REGULAR_PATH, 34)

        # Draw WELCOME Title
        draw.text(
            (W // 2, text_start_y),
            "WELCOME",
            font=font_welcome,
            fill=(255, 255, 255, 255),
            anchor="mt",
            stroke_width=3,
            stroke_fill=(0, 0, 0, 255),
        )

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

        user_bbox = draw.textbbox((0, 0), username_clean, font=font_username)
        user_h = user_bbox[3] - user_bbox[1]

        count_y = username_y + user_h + 10
        count_text = f"YOU ARE OUR {member_count}{'th' if 11 <= (member_count % 100) <= 13 else ['th','st','nd','rd','th'][min(member_count % 10, 4)]} MEMBER!"
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

    member_count = member.guild.member_count

    is_gif = config.background_path and config.background_path.lower().endswith(".gif")
    
    # If it's a GIF or all overlays are disabled, send the raw file directly
    if (is_gif or (not config.draw_avatar and not config.show_guild_icon and not config.draw_text)) and config.background_path and os.path.exists(config.background_path):
        filename = "welcome.gif" if is_gif else "welcome.png"
        discord_file = discord.File(config.background_path, filename=filename)
        image_url = f"attachment://{filename}"
    else:
        # Fetch avatar if either embed thumbnail or card drawing is enabled
        avatar_bytes = b""
        if config.show_avatar or config.draw_avatar:
            try:
                avatar_bytes = await member.display_avatar.read()
            except Exception:
                pass

        # Fetch guild icon if enabled
        guild_icon_bytes = b""
        if config.show_guild_icon and member.guild.icon:
            try:
                guild_icon_bytes = await member.guild.icon.read()
            except Exception:
                pass

        # Render card
        card_file_bytes = render_welcome_card(
            avatar_bytes=avatar_bytes,
            guild_icon_bytes=guild_icon_bytes,
            username=member.name,
            member_count=member_count,
            background_path=config.background_path,
            draw_avatar=config.draw_avatar,
            show_guild_icon=config.show_guild_icon,
            draw_text=config.draw_text
        )
        discord_file = discord.File(card_file_bytes, filename=f"welcome_{member.id}.jpg")
        image_url = f"attachment://welcome_{member.id}.jpg"

    # Format custom message inside the embed box description
    import string
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
            
    description_text = string.Formatter().vformat(
        config.welcome_message, (), SafeDict(
            member=member.mention,
            server=member.guild.name,
            member_count=member_count
        )
    )

    # Construct premium Embed
    embed = discord.Embed(
        title="WELCOME",
        description=description_text,
        color=0xFF2828  # Red
    )
    if config.show_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=image_url)
    embed.set_footer(text=f"© {member.guild.name} • {discord.utils.utcnow().strftime('%m-%d-%Y %I:%M %p')}", icon_url=member.guild.icon.url if member.guild.icon else None)

    # Short mention text outside the embed
    content = f"Welcome {member.mention}!"
    await channel.send(content=content, embed=embed, file=discord_file)


async def send_leave(member: discord.Member, config: WelcomeConfig) -> None:
    if not config.leave_enabled or not config.leave_channel_id:
        return

    channel = member.guild.get_channel(config.leave_channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
        return

    import string
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"
            
    description_text = string.Formatter().vformat(
        config.leave_message, (), SafeDict(
            user=member.name,
            member=member.mention,
            server=member.guild.name,
            member_count=member.guild.member_count
        )
    )

    embed = discord.Embed(
        title="MEMBER LEFT",
        description=description_text,
        color=0x2b2d31  # Dark theme color
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if config.leave_image_url:
        embed.set_image(url=config.leave_image_url)
    embed.set_footer(text=f"© {member.guild.name} • {discord.utils.utcnow().strftime('%m-%d-%Y %I:%M %p')}", icon_url=member.guild.icon.url if member.guild.icon else None)

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        print(f"[Welcome] ❌ Missing permissions to send leave message in #{channel.name}")
    except Exception as e:
        print(f"[Welcome] ❌ Error sending leave message: {e}")


class WelcomeMessageModal(discord.ui.Modal, title="👋 Set Welcome Message"):
    """Popup dialog capturing multi-line welcome message — newlines and spacing are fully preserved."""
    message_text = discord.ui.TextInput(
        label="Welcome Message",
        style=discord.TextStyle.paragraph,
        placeholder="Use {member}, {server}, {member_count}. Newlines & spacing preserved exactly.",
        required=True,
        max_length=4000,
    )

    def __init__(self, db: "WelcomeDatabase", guild_id: int):
        super().__init__()
        self._db = db
        self._guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        config = self._db.get_config(self._guild_id)
        config.welcome_message = str(self.message_text)
        self._db.save_config(config)
        preview = config.welcome_message[:200] + "..." if len(config.welcome_message) > 200 else config.welcome_message
        await interaction.response.send_message(f"✅ Welcome message set:\n>>> {preview}", ephemeral=True)


class LeaveMessageModal(discord.ui.Modal, title="👋 Set Leave Message"):
    """Popup dialog capturing multi-line leave message — newlines and spacing are fully preserved."""
    message_text = discord.ui.TextInput(
        label="Leave Message",
        style=discord.TextStyle.paragraph,
        placeholder="Use {user}, {member}, {server}, {member_count}. Newlines & spacing preserved exactly.",
        required=True,
        max_length=4000,
    )

    def __init__(self, db: "WelcomeDatabase", guild_id: int):
        super().__init__()
        self._db = db
        self._guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        config = self._db.get_config(self._guild_id)
        config.leave_message = str(self.message_text)
        self._db.save_config(config)
        preview = config.leave_message[:200] + "..." if len(config.leave_message) > 200 else config.leave_message
        await interaction.response.send_message(f"✅ Leave message set:\n>>> {preview}", ephemeral=True)


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = WelcomeDatabase()
        self.db.initialize()
        
        self.welcome_group = app_commands.Group(name="welcome", description="Manage Server Welcome messages & cards")
        self.leave_group = app_commands.Group(name="leave", description="Manage Server Leave messages")
        
        # We assign the commands to the group
        self.welcome_group.add_command(app_commands.Command(name="status", description="Show the current welcome settings configuration", callback=self.status))
        self.welcome_group.add_command(app_commands.Command(name="toggle", description="Toggle the welcome greeting system on or off", callback=self.toggle))
        self.welcome_group.add_command(app_commands.Command(name="channel", description="Set the channel where welcome greetings will be posted", callback=self.set_channel))
        self.welcome_group.add_command(app_commands.Command(name="message", description="Set a custom message text to send alongside the welcome card", callback=self.set_message))
        self.welcome_group.add_command(app_commands.Command(name="showavatar", description="Choose whether to show the joining user's avatar as the Embed thumbnail on the card", callback=self.toggle_show_avatar))
        self.welcome_group.add_command(app_commands.Command(name="drawavatar", description="Choose whether to draw the user avatar circle on the welcome card image", callback=self.toggle_draw_avatar))
        self.welcome_group.add_command(app_commands.Command(name="showservericon", description="Choose whether to display the server icon on the welcome card", callback=self.toggle_server_icon))
        self.welcome_group.add_command(app_commands.Command(name="drawtext", description="Choose whether to draw text overlay (WELCOME, username, etc.) on the welcome card image", callback=self.toggle_draw_text))
        self.welcome_group.add_command(app_commands.Command(name="role", description="Set a role to automatically give to new and existing members", callback=self.set_role))
        self.welcome_group.add_command(app_commands.Command(name="botrole", description="Set a role to automatically give specifically to newly added BOTS", callback=self.set_bot_role))
        self.welcome_group.add_command(app_commands.Command(name="setbg", description="Upload a custom background image or GIF (Recommended 1024x500)", callback=self.set_bg))
        self.welcome_group.add_command(app_commands.Command(name="setbgurl", description="Set a custom background image or GIF from a direct URL", callback=self.set_bg_url))
        self.welcome_group.add_command(app_commands.Command(name="test", description="Simulate a welcome card message inside the setup channel", callback=self.test_welcome))
        
        
        self.bot.tree.add_command(self.welcome_group)
        
        # We assign the commands to the leave group
        self.leave_group.add_command(app_commands.Command(name="toggle", description="Toggle the leave message system on or off", callback=self.leave_toggle))
        self.leave_group.add_command(app_commands.Command(name="channel", description="Set the channel where leave messages will be posted", callback=self.leave_set_channel))
        self.leave_group.add_command(app_commands.Command(name="message", description="Set a custom message text to send on leave", callback=self.leave_set_message))
        self.leave_group.add_command(app_commands.Command(name="image", description="Set a custom image/GIF URL for the leave embed", callback=self.leave_set_image))
        self.leave_group.add_command(app_commands.Command(name="test", description="Simulate a leave message in the setup channel", callback=self.test_leave))
        
        self.bot.tree.add_command(self.leave_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.welcome_group.name)
        self.bot.tree.remove_command(self.leave_group.name)

    @commands.Cog.listener()
    async def on_ready(self):
        await download_fonts()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = self.db.get_config(member.guild.id)
        if config.enabled:
            await send_welcome(member, config)
            
        if member.bot and config.bot_role_id:
            role = member.guild.get_role(config.bot_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Bot auto-role on join")
                except Exception as e:
                    print(f"[Welcome] Failed to add bot role on join: {e}")
        elif not member.bot and config.welcome_role_id:
            role = member.guild.get_role(config.welcome_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Member auto-role on join")
                except Exception as e:
                    print(f"[Welcome] Failed to add member role on join: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        config = self.db.get_config(member.guild.id)
        if config.leave_enabled:
            await send_leave(member, config)

    @app_commands.default_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
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
        
        bg_status = "Default Dark Theme"
        if config.background_path and os.path.exists(config.background_path):
            bg_status = "Custom Background Image"
        embed.add_field(name="Card Background", value=bg_status, inline=True)
        
        embed.add_field(name="Show Embed Thumbnail", value="Yes" if config.show_avatar else "No", inline=True)
        embed.add_field(name="Draw Avatar on Card", value="Yes" if config.draw_avatar else "No", inline=True)
        embed.add_field(name="Draw Server Icon on Card", value="Yes" if config.show_guild_icon else "No", inline=True)
        embed.add_field(name="Draw Text on Card", value="Yes" if config.draw_text else "No", inline=True)
        
        role_val = "Not Set"
        if config.welcome_role_id:
            r = interaction.guild.get_role(config.welcome_role_id)
            if r:
                role_val = r.mention
        embed.add_field(name="Auto-Role (Members)", value=role_val, inline=True)

        bot_role_val = "Not Set"
        if config.bot_role_id:
            br = interaction.guild.get_role(config.bot_role_id)
            if br:
                bot_role_val = br.mention
        embed.add_field(name="Auto-Role (Bots)", value=bot_role_val, inline=True)
        
        embed.add_field(name="Message Text", value=f"`{config.welcome_message}`", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def toggle(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.enabled = not config.enabled
        self.db.save_config(config)
        status_str = "ENABLED" if config.enabled else "DISABLED"
        await interaction.response.send_message(f"✅ Welcome system is now **{status_str}**.", ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.channel_id = channel.id
        self.db.save_config(config)
        await interaction.response.send_message(f"✅ Welcome channel successfully set to {channel.mention}.", ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def set_message(self, interaction: discord.Interaction) -> None:
        """Open a multi-line welcome message modal — newlines and spacing are fully preserved."""
        await interaction.response.send_modal(WelcomeMessageModal(self.db, interaction.guild.id))

    @app_commands.describe(show="Select True/False")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle_show_avatar(self, interaction: discord.Interaction, show: bool) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.show_avatar = show
        self.db.save_config(config)
        status_str = "will now" if show else "will no longer"
        await interaction.response.send_message(f"✅ User avatar {status_str} be displayed as the Discord Embed thumbnail.", ephemeral=True)

    @app_commands.describe(show="Select True/False")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle_draw_avatar(self, interaction: discord.Interaction, show: bool) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.draw_avatar = show
        self.db.save_config(config)
        status_str = "will now" if show else "will no longer"
        await interaction.response.send_message(f"✅ User avatar drawing {status_str} be enabled on the welcome card image.", ephemeral=True)

    @app_commands.describe(show="Select True/False")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle_server_icon(self, interaction: discord.Interaction, show: bool) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.show_guild_icon = show
        self.db.save_config(config)
        status_str = "will now" if show else "will no longer"
        await interaction.response.send_message(f"✅ Server icon {status_str} be displayed on the welcome card.", ephemeral=True)

    @app_commands.describe(show="Select True/False")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle_draw_text(self, interaction: discord.Interaction, show: bool) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.draw_text = show
        self.db.save_config(config)
        status_str = "will now" if show else "will no longer"
        await interaction.response.send_message(f"✅ Card text overlay {status_str} be drawn on the welcome card image.", ephemeral=True)

    @app_commands.describe(role="The role to assign")
    @app_commands.default_permissions(manage_guild=True)
    async def set_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.welcome_role_id = role.id
        self.db.save_config(config)
        
        await interaction.response.send_message(
            f"✅ Welcome auto-role set to {role.mention}! I will automatically give this to new members when they join.\\n"
            f"🔄 Background sync started: I am now assigning this role to all existing members...",
            ephemeral=True
        )

        async def sync_role_task(guild: discord.Guild, target_role: discord.Role):
            added = 0
            try:
                print(f"[Welcome] Fetching all members for {guild.name}...")
                members = [m async for m in guild.fetch_members(limit=None)]
                print(f"[Welcome] Found {len(members)} members. Starting role assignment for '{target_role.name}'...")
                
                for member in members:
                    if member.bot: continue
                    if any(r.id == target_role.id for r in member.roles):
                        continue
                        
                    try:
                        await member.add_roles(target_role, reason="Welcome auto-role background sync")
                        added += 1
                        import asyncio
                        await asyncio.sleep(1)
                    except discord.Forbidden:
                        print(f"[Welcome] ❌ Missing permissions to add role to {member.display_name}. Ensure my bot role is HIGHER in the server list than '{target_role.name}'.")
                    except Exception as e:
                        print(f"[Welcome] ⚠️ Failed to add role to {member.display_name}: {e}")
            except Exception as e:
                print(f"[Welcome] ❌ Critical error in role sync task: {e}")
                
            print(f"[Welcome] ✅ Finished background role sync. Added '{target_role.name}' to {added} members in {guild.name}.")

        self.bot.loop.create_task(sync_role_task(interaction.guild, role))

    @app_commands.describe(role="The role to assign to bots")
    @app_commands.default_permissions(manage_guild=True)
    async def set_bot_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.bot_role_id = role.id
        self.db.save_config(config)
        
        await interaction.response.send_message(
            f"✅ Bot auto-role set to {role.mention}! I will automatically give this ONLY to bots when they join.\n"
            f"🔄 Background sync started: I am now assigning this role to all existing bots...",
            ephemeral=True
        )

        async def sync_bot_role_task(guild: discord.Guild, target_role: discord.Role):
            added = 0
            try:
                members = [m async for m in guild.fetch_members(limit=None)]
                import asyncio
                for member in members:
                    if not member.bot: continue
                    if any(r.id == target_role.id for r in member.roles): continue
                    try:
                        await member.add_roles(target_role, reason="Bot auto-role background sync")
                        added += 1
                        await asyncio.sleep(1)
                    except discord.Forbidden:
                        print(f"[Welcome] ❌ Missing permissions to add bot role to {member.display_name}.")
                    except Exception as e:
                        pass
            except Exception:
                pass
            print(f"[Welcome] ✅ Added '{target_role.name}' to {added} bots in {guild.name}.")

        self.bot.loop.create_task(sync_bot_role_task(interaction.guild, role))

    @app_commands.default_permissions(manage_guild=True)
    async def set_bg(self, interaction: discord.Interaction, image: discord.Attachment) -> None:
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message("❌ Uploaded file must be an image.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            bg_data = await image.read()
            is_gif = image.filename.lower().endswith(".gif") or image.content_type == "image/gif"
            
            if is_gif:
                filename = f"bg_{interaction.guild.id}.gif"
            else:
                img = Image.open(io.BytesIO(bg_data))
                img.verify()
                filename = f"bg_{interaction.guild.id}.png"

            dest_path = os.path.join(ASSETS_DIR, filename)
            with open(dest_path, "wb") as f:
                f.write(bg_data)

            config = self.db.get_config(interaction.guild.id)
            config.background_path = dest_path
            self.db.save_config(config)

            await interaction.followup.send("✅ Custom background image successfully updated!", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to process uploaded image: {exc}", ephemeral=True)

    @app_commands.describe(url="Direct URL to a GIF or image (must end in .gif, .png, .jpg)")
    @app_commands.default_permissions(manage_guild=True)
    async def set_bg_url(self, interaction: discord.Interaction, url: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ Failed to download image from URL.", ephemeral=True)
                        return
                    bg_data = await resp.read()
                    
            is_gif = url.lower().split("?")[0].endswith(".gif")
            if is_gif:
                filename = f"bg_{interaction.guild.id}.gif"
            else:
                try:
                    img = Image.open(io.BytesIO(bg_data))
                    img.verify()
                except:
                    await interaction.followup.send("❌ The URL provided does not seem to contain a valid image.", ephemeral=True)
                    return
                filename = f"bg_{interaction.guild.id}.png"

            dest_path = os.path.join(ASSETS_DIR, filename)
            with open(dest_path, "wb") as f:
                f.write(bg_data)

            config = self.db.get_config(interaction.guild.id)
            config.background_path = dest_path
            self.db.save_config(config)

            await interaction.followup.send("✅ Custom background image URL successfully downloaded and set!", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to process URL: {exc}", ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def test_welcome(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
        if not config.channel_id:
            await interaction.response.send_message("❌ Please set a welcome channel first using `/welcome channel`.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await send_welcome(interaction.user, config)
            await interaction.followup.send("✅ Test welcome message dispatched successfully!", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to run welcome test: {exc}", ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def leave_toggle(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.leave_enabled = not config.leave_enabled
        self.db.save_config(config)
        status = "enabled" if config.leave_enabled else "disabled"
        await interaction.response.send_message(f"✅ Leave message system is now **{status}**.", ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def leave_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.leave_channel_id = channel.id
        self.db.save_config(config)
        await interaction.response.send_message(f"✅ Leave messages will now be sent in {channel.mention}.", ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def leave_set_message(self, interaction: discord.Interaction) -> None:
        modal = LeaveMessageModal(self.db, interaction.guild.id)
        config = self.db.get_config(interaction.guild.id)
        modal.message_text.default = config.leave_message
        await interaction.response.send_modal(modal)

    @app_commands.describe(url="Direct URL to a GIF or image (must end in .gif, .png, .jpg) or 'none' to clear")
    @app_commands.default_permissions(manage_guild=True)
    async def leave_set_image(self, interaction: discord.Interaction, url: str) -> None:
        config = self.db.get_config(interaction.guild.id)
        if url.lower() == "none":
            config.leave_image_url = None
            self.db.save_config(config)
            await interaction.response.send_message("✅ Leave image cleared.", ephemeral=True)
            return

        config.leave_image_url = url
        self.db.save_config(config)
        await interaction.response.send_message("✅ Custom leave image URL successfully set!", ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def test_leave(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
        if not config.leave_channel_id:
            await interaction.response.send_message("❌ Please set a leave channel first using `/leave channel`.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            # We override the setting temporarily to True just to ensure it sends during the test
            old_enabled = config.leave_enabled
            config.leave_enabled = True
            await send_leave(interaction.user, config)
            config.leave_enabled = old_enabled
            await interaction.followup.send("✅ Test leave message dispatched successfully!", ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(f"❌ Failed to run leave test: {exc}", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
