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
from gkr_ui import embed_success, embed_error, embed_info, C

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
    welcome_message: str = (
        "🎊 **Welcome to FAMILY** 🎊\n\n"
        "Hey {member}! 👋 We're so glad you're here!\n\n"
        "**{server}** is a place built on good vibes, genuine friendships and great memories. "
        "Whether you're here to chill, game, share memes or just talk — there's always a place for you.\n\n"
        "Make yourself comfortable, say hi in the chat and jump right in!\n\n"
        "🏠 *Welcome home, Amigo!*"
    )
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
    """Futuristic dark cyberpunk split-panel background."""
    W, H = 1024, 500
    base = Image.new("RGBA", (W, H), (8, 6, 14, 255))
    draw = ImageDraw.Draw(base)
    # Left panel: deep navy/indigo
    for x in range(W // 2):
        t = x / (W // 2)
        r = int(12 + 8 * t)
        g = int(8 + 4 * t)
        b = int(22 + 10 * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b, 255))
    # Right panel: near-black with subtle blue tint
    for x in range(W // 2, W):
        t = (x - W // 2) / (W // 2)
        r = int(10 + 4 * t)
        g = int(10 + 4 * t)
        b = int(18 + 6 * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b, 255))
    return base


def _draw_glow_circle(canvas: Image.Image, cx: int, cy: int, radius: int, color: Tuple[int, int, int], alpha_max: int = 80, layers: int = 8) -> None:
    """Draw a multi-layer soft glow ring centered at (cx, cy)."""
    for i in range(layers, 0, -1):
        r_i = radius + (layers - i) * 6
        alpha = int(alpha_max * (i / layers) * 0.6)
        glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gd.ellipse(
            (cx - r_i, cy - r_i, cx + r_i, cy + r_i),
            fill=(*color, alpha),
        )
        canvas.alpha_composite(glow_layer)


def make_circle_avatar(
    avatar_image: Image.Image,
    size: int = 200,
    border_color: Tuple[int, int, int] = (120, 80, 255),
    border_width: int = 5,
) -> Image.Image:
    """Crop avatar into a circle with a colored ring."""
    avatar_image = avatar_image.convert("RGBA")
    avatar_image = ImageOps.fit(avatar_image, (size, size), Image.Resampling.LANCZOS)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)

    circle_avatar = Image.new("RGBA", (size, size))
    circle_avatar.paste(avatar_image, (0, 0), mask=mask)

    total_size = size + border_width * 2
    bordered = Image.new("RGBA", (total_size, total_size), (0, 0, 0, 0))
    ImageDraw.Draw(bordered).ellipse(
        (0, 0, total_size, total_size), fill=(*border_color, 255)
    )
    bordered.paste(circle_avatar, (border_width, border_width), mask=circle_avatar)
    return bordered


def render_welcome_card(
    avatar_bytes: bytes,
    guild_icon_bytes: bytes,
    username: str,
    member_count: int,
    guild_name: str = "the server",
    background_path: Optional[str] = None,
    draw_avatar: bool = True,
    show_guild_icon: bool = False,
    draw_text: bool = True,
) -> io.BytesIO:
    """Render a futuristic split-panel welcome card.

    LEFT PANEL  (0 → 420 px)  : radial purple/cyan glow + glowing avatar rings
    RIGHT PANEL (420 → 1024)  : dark glass card with gradient title & info badges
    """
    import math, random

    W, H = 1024, 500
    SPLIT = 410          # x where left panel ends
    ACCENT  = (130, 80, 255)   # purple accent
    ACCENT2 = (0, 200, 255)    # cyan accent
    GOLD    = (255, 195, 0)    # gold for member count
    WHITE   = (255, 255, 255)

    # ── Background ────────────────────────────────────────────────────────────
    if background_path and os.path.exists(background_path):
        try:
            bg = Image.open(background_path).convert("RGBA")
            bg = ImageOps.fit(bg, (W, H), Image.Resampling.LANCZOS)
            # darken custom bg heavily
            bg = Image.alpha_composite(bg, Image.new("RGBA", bg.size, (0, 0, 0, 175)))
        except Exception:
            bg = generate_default_bg()
    else:
        bg = generate_default_bg()

    # ── Left panel radial glow ────────────────────────────────────────────────
    cx_glow, cy_glow = SPLIT // 2, H // 2
    for radius, color, alpha in [
        (220, ACCENT,  30),
        (160, ACCENT,  50),
        (100, ACCENT2, 40),
        (60,  ACCENT2, 25),
    ]:
        _draw_glow_circle(bg, cx_glow, cy_glow, radius, color, alpha_max=alpha, layers=6)

    # ── Subtle particle dots (left panel) ────────────────────────────────────
    rng = random.Random(42)
    pdraw = ImageDraw.Draw(bg)
    for _ in range(38):
        px = rng.randint(8, SPLIT - 8)
        py = rng.randint(8, H - 8)
        pr = rng.randint(1, 3)
        pa = rng.randint(40, 130)
        col = rng.choice([ACCENT, ACCENT2, WHITE])
        pdraw.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(*col, pa))

    # ── Right panel glass overlay ─────────────────────────────────────────────
    glass = Image.new("RGBA", (W - SPLIT, H), (10, 10, 22, 200))
    bg.alpha_composite(glass, (SPLIT, 0))

    # Thin vertical separator line with glow
    sep_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sep_draw  = ImageDraw.Draw(sep_layer)
    for offset, alpha in [(-2, 30), (-1, 80), (0, 200), (1, 80), (2, 30)]:
        sep_draw.line([(SPLIT + offset, 0), (SPLIT + offset, H)], fill=(*ACCENT, alpha))
    bg.alpha_composite(sep_layer)

    # Corner accent line (top-right)
    corner_draw = ImageDraw.Draw(bg)
    corner_draw.line([(SPLIT + 20, 0), (W - 20, 0)], fill=(*ACCENT, 120), width=2)
    corner_draw.line([(SPLIT + 20, H - 1), (W - 20, H - 1)], fill=(*ACCENT, 80), width=1)
    # Small corner bracket top-left of right panel
    corner_draw.line([(SPLIT, 0), (SPLIT, 30)], fill=(*ACCENT2, 180), width=2)
    corner_draw.line([(SPLIT, 0), (SPLIT + 30, 0)], fill=(*ACCENT2, 180), width=2)

    # ── Avatar with multi-ring glow (left panel) ──────────────────────────────
    avatar_img = None
    if draw_avatar and avatar_bytes:
        try:
            avatar_img = Image.open(io.BytesIO(avatar_bytes))
        except Exception:
            avatar_img = Image.new("RGBA", (200, 200), (80, 80, 100, 255))

    AVATAR_R = 95          # avatar circle radius
    av_cx    = cx_glow
    av_cy    = cy_glow

    if avatar_img:
        # Outer glow rings
        for ring_r, ring_col, ring_alpha, ring_w in [
            (AVATAR_R + 30, ACCENT,  60, 2),
            (AVATAR_R + 20, ACCENT2, 80, 3),
            (AVATAR_R + 10, ACCENT,  120, 4),
        ]:
            ring_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ring_d = ImageDraw.Draw(ring_layer)
            ring_d.ellipse(
                (av_cx - ring_r, av_cy - ring_r, av_cx + ring_r, av_cy + ring_r),
                outline=(*ring_col, ring_alpha),
                width=ring_w,
            )
            bg.alpha_composite(ring_layer)

        # Avatar circle with purple border
        circ = make_circle_avatar(
            avatar_img,
            size=AVATAR_R * 2,
            border_color=ACCENT,
            border_width=5,
        )
        paste_x = av_cx - circ.width  // 2
        paste_y = av_cy - circ.height // 2
        bg.paste(circ, (paste_x, paste_y), mask=circ)

    # ── Fonts ─────────────────────────────────────────────────────────────────
    font_header  = load_font(FONT_BOLD_PATH,    44)   # "WELCOME TO"
    font_name    = load_font(FONT_BOLD_PATH,    58)   # username
    font_sub     = load_font(FONT_REGULAR_PATH, 26)   # member count
    font_server  = load_font(FONT_REGULAR_PATH, 22)   # server name
    font_tiny    = load_font(FONT_REGULAR_PATH, 18)   # small badge text

    if draw_text:
        RX     = SPLIT + 28          # right panel text left edge
        R_W    = W - SPLIT - 28      # available width in right panel
        R_CX   = SPLIT + (W - SPLIT) // 2  # right panel center x

        text_draw = ImageDraw.Draw(bg)

        # ── "WELCOME TO" label ────────────────────────────────────────────────
        label_y = 52
        label_text = "WELCOME TO"
        lb_bbox = text_draw.textbbox((0, 0), label_text, font=font_header)
        lb_w = lb_bbox[2] - lb_bbox[0]
        lb_x = R_CX - lb_w // 2
        # soft glow under text
        for ox, oy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            text_draw.text((lb_x + ox, label_y + oy), label_text, font=font_header, fill=(*ACCENT, 60))
        text_draw.text((lb_x, label_y), label_text, font=font_header, fill=(190, 160, 255, 255))

        # Thin underline under label
        ul_y = label_y + (lb_bbox[3] - lb_bbox[1]) + 4
        text_draw.line([(RX, ul_y), (W - 28, ul_y)], fill=(*ACCENT, 100), width=1)

        # ── Server name ───────────────────────────────────────────────────────
        srv_y = ul_y + 8
        guild_display = guild_name.upper()
        # Truncate if too long
        while True:
            srv_bbox = text_draw.textbbox((0, 0), guild_display, font=font_server)
            if (srv_bbox[2] - srv_bbox[0]) <= R_W or len(guild_display) < 4:
                break
            guild_display = guild_display[:-4] + "..."
        srv_w = srv_bbox[2] - srv_bbox[0]
        text_draw.text((R_CX - srv_w // 2, srv_y), guild_display, font=font_server, fill=(*ACCENT2, 220))

        # ── Username ──────────────────────────────────────────────────────────
        name_y = srv_y + (srv_bbox[3] - srv_bbox[1]) + 22
        display_name = username
        # Truncate if needed
        while True:
            nm_bbox = text_draw.textbbox((0, 0), display_name, font=font_name)
            if (nm_bbox[2] - nm_bbox[0]) <= R_W or len(display_name) < 4:
                break
            display_name = display_name[:-4] + "..."
        nm_w = nm_bbox[2] - nm_bbox[0]
        nm_h = nm_bbox[3] - nm_bbox[1]
        nm_x = R_CX - nm_w // 2
        # Glow shadow
        for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4)]:
            text_draw.text((nm_x + ox, name_y + oy), display_name, font=font_name, fill=(*ACCENT, 50))
        text_draw.text((nm_x, name_y), display_name, font=font_name, fill=WHITE)

        # ── Divider ───────────────────────────────────────────────────────────
        div_y = name_y + nm_h + 18
        div_cx = R_CX
        text_draw.line([(div_cx - 80, div_y), (div_cx + 80, div_y)], fill=(*ACCENT2, 80), width=1)
        # Diamond center accent
        dm = 4
        text_draw.polygon(
            [(div_cx, div_y - dm), (div_cx + dm, div_y), (div_cx, div_y + dm), (div_cx - dm, div_y)],
            fill=(*ACCENT2, 200),
        )

        # ── Member count badge ────────────────────────────────────────────────
        suffix_map = {1: "st", 2: "nd", 3: "rd"}
        n_mod = member_count % 100
        n_end = member_count % 10
        suffix = "th" if 11 <= n_mod <= 13 else suffix_map.get(n_end, "th")
        count_text = f"#{member_count:,}{suffix} Member"

        badge_y = div_y + 16
        ct_bbox = text_draw.textbbox((0, 0), count_text, font=font_sub)
        ct_w = ct_bbox[2] - ct_bbox[0]
        ct_h = ct_bbox[3] - ct_bbox[1]
        badge_pad_x, badge_pad_y = 18, 8
        badge_x1 = R_CX - ct_w // 2 - badge_pad_x
        badge_y1 = badge_y - badge_pad_y
        badge_x2 = R_CX + ct_w // 2 + badge_pad_x
        badge_y2 = badge_y + ct_h + badge_pad_y
        badge_r  = (badge_y2 - badge_y1) // 2

        # Badge pill background
        badge_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(badge_layer)
        bd.rounded_rectangle(
            (badge_x1, badge_y1, badge_x2, badge_y2),
            radius=badge_r,
            fill=(*GOLD, 28),
            outline=(*GOLD, 130),
            width=1,
        )
        bg.alpha_composite(badge_layer)
        text_draw.text(
            (R_CX - ct_w // 2, badge_y),
            count_text,
            font=font_sub,
            fill=(*GOLD, 230),
        )

        # ── Bottom tagline ────────────────────────────────────────────────────
        tag_y = badge_y2 + 20
        if tag_y < H - 36:
            tag_text = "We're glad you're here ✦"
            tg_bbox = text_draw.textbbox((0, 0), tag_text, font=font_tiny)
            tg_w = tg_bbox[2] - tg_bbox[0]
            text_draw.text(
                (R_CX - tg_w // 2, tag_y),
                tag_text,
                font=font_tiny,
                fill=(160, 160, 200, 180),
            )

    # ── Export ────────────────────────────────────────────────────────────────
    output = io.BytesIO()
    bg.convert("RGB").save(output, format="JPEG", quality=93)
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
            username=member.display_name,
            member_count=member_count,
            guild_name=member.guild.name,
            background_path=config.background_path,
            draw_avatar=config.draw_avatar,
            show_guild_icon=config.show_guild_icon,
            draw_text=config.draw_text,
        )
        discord_file = discord.File(card_file_bytes, filename=f"welcome_{member.id}.jpg")
        image_url = f"attachment://welcome_{member.id}.jpg"

    # ── Format the custom welcome message ────────────────────────────────────
    import string
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    custom_msg = string.Formatter().vformat(
        config.welcome_message, (), SafeDict(
            member=member.mention,
            server=member.guild.name,
            member_count=member_count,
        )
    )

    # ── Ordinal suffix for member count ──────────────────────────────────────
    n = member_count or 0
    _s = {1: "st", 2: "nd", 3: "rd"}
    suffix = "th" if 11 <= (n % 100) <= 13 else _s.get(n % 10, "th")
    member_ordinal = f"#{n:,}{suffix}"

    # ── Account age ───────────────────────────────────────────────────────────
    created = member.created_at
    now_utc = discord.utils.utcnow()
    days_old = (now_utc - created).days
    if days_old < 30:
        age_str = f"{days_old} days"
    elif days_old < 365:
        age_str = f"{days_old // 30} months"
    else:
        age_str = f"{days_old // 365}y {(days_old % 365) // 30}mo"

    join_ts = f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "just now"

    # ── Build premium full-width embed ────────────────────────────────────────
    # KEY: use set_author() for avatar (top-left small icon) instead of
    #      set_thumbnail() — thumbnail compresses text to 60% width. This
    #      gives the description FULL embed width (≈520 px on desktop).
    #
    # Structure (inspired by ProBot / Carl-bot premium layouts):
    #   [AUTHOR ROW]   avatar ● "username just joined"
    #   [HERO IMAGE]   full-width welcome card (top of embed, most prominent)
    #   [DESCRIPTION]  decorated short greeting + custom message
    #   [FIELDS ×2]    member ordinal  |  account age
    #   [FOOTER]       server icon + name + timestamp

    embed = discord.Embed(
        color=0x8250FF,
        timestamp=discord.utils.utcnow(),
    )

    # Author row — avatar renders as a small circle at top-left (no width cost)
    embed.set_author(
        name=f"✦  {member.display_name}  ✦",
        icon_url=member.display_avatar.url,
    )

    # Hero image — full width, immediately under the author row
    embed.set_image(url=image_url)

    # Description — short, clear, well-spaced, uses markdown
    divider = "─" * 35          # Discord renders long dashes cleanly
    desc = (
        f"## 🎉  Welcome to **{member.guild.name}**!\n"
        f"{divider}\n"
        f"\n"
        f"{custom_msg}\n"
        f"\n"
        f"{divider}"
    )
    embed.description = desc

    # Fields — ONLY 2 inline so they stay wide and don't wrap
    embed.add_field(
        name="🏅  Member",
        value=f"**{member_ordinal}**",
        inline=True,
    )
    embed.add_field(
        name="🕰️  Account Age",
        value=f"**{age_str}**",
        inline=True,
    )

    # Footer with server branding
    guild_icon = member.guild.icon.url if member.guild.icon else None
    embed.set_footer(
        text=f"{member.guild.name}  ·  We're glad you're here",
        icon_url=guild_icon,
    )

    # ── Content (outside embed) — clean single-line ping ─────────────────────
    content = f"👋  {member.mention} — **Welcome to the family!** 🎊"

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

    custom_leave = string.Formatter().vformat(
        config.leave_message, (), SafeDict(
            user=member.display_name,
            member=member.mention,
            server=member.guild.name,
            member_count=member.guild.member_count,
        )
    )

    remaining = member.guild.member_count or 0
    guild_icon = member.guild.icon.url if member.guild.icon else None

    embed = discord.Embed(
        title=f"👋  {member.display_name} has left",
        description=(
            f"### 😢  Farewell, **{member.display_name}**!\n"
            f"\n"
            f"{custom_leave}"
        ),
        color=0x4A4A6A,        # Muted indigo — somber but not harsh
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="👥  Members Remaining",
        value=f"```\n{remaining:,} members\n```",
        inline=True,
    )
    embed.add_field(
        name="📅  Was a member since",
        value=f"<t:{int(member.joined_at.timestamp())}:D>" if member.joined_at else "*Unknown*",
        inline=True,
    )
    if config.leave_image_url:
        embed.set_image(url=config.leave_image_url)
    embed.set_footer(
        text=f"{member.guild.name}  •  They will be missed ✦",
        icon_url=guild_icon,
    )

    try:
        await channel.send(
            content=f"> **{member.display_name}** just left the server.",
            embed=embed,
        )
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
        await interaction.response.send_message(embed=embed_success("Success", f"Welcome message set:\n>>> {preview}"), ephemeral=True)


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
        await interaction.response.send_message(embed=embed_success("Success", f"Leave message set:\n>>> {preview}"), ephemeral=True)


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = WelcomeDatabase()
        self.db.initialize()
        
        self.welcome_group = app_commands.Group(name="welcome", description="Manage Server Welcome messages & cards")
        self.leave_group = app_commands.Group(name="leave", description="Manage Server Leave messages")
        self.autorole_group = app_commands.Group(name="autorole", description="Manage automatic role assignment for members and bots upon joining")
        
        # We assign the commands to the welcome group
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

        # Dedicated Auto-Role group
        self.autorole_group.add_command(app_commands.Command(name="member", description="Set an auto-role to assign to human members upon joining", callback=self.set_role))
        self.autorole_group.add_command(app_commands.Command(name="bot", description="Set an auto-role specifically for newly invited bots", callback=self.set_bot_role))
        self.autorole_group.add_command(app_commands.Command(name="status", description="View active member and bot auto-roles", callback=self.autorole_status))
        self.autorole_group.add_command(app_commands.Command(name="remove", description="Remove member or bot auto-role configuration", callback=self.remove_autorole_cmd))

        self.bot.tree.add_command(self.autorole_group)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.welcome_group.name)
        self.bot.tree.remove_command(self.leave_group.name)
        self.bot.tree.remove_command(self.autorole_group.name)

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
        await interaction.response.send_message(embed=embed_success("Success", f"Welcome system is now **{status_str}**."), ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.channel_id = channel.id
        self.db.save_config(config)
        await interaction.response.send_message(embed=embed_success("Success", f"Welcome channel successfully set to {channel.mention}."), ephemeral=True)

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
        await interaction.response.send_message(embed=embed_success("Success", f"User avatar {status_str} be displayed as the Discord Embed thumbnail."), ephemeral=True)

    @app_commands.describe(show="Select True/False")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle_draw_avatar(self, interaction: discord.Interaction, show: bool) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.draw_avatar = show
        self.db.save_config(config)
        status_str = "will now" if show else "will no longer"
        await interaction.response.send_message(embed=embed_success("Success", f"User avatar drawing {status_str} be enabled on the welcome card image."), ephemeral=True)

    @app_commands.describe(show="Select True/False")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle_server_icon(self, interaction: discord.Interaction, show: bool) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.show_guild_icon = show
        self.db.save_config(config)
        status_str = "will now" if show else "will no longer"
        await interaction.response.send_message(embed=embed_success("Success", f"Server icon {status_str} be displayed on the welcome card."), ephemeral=True)

    @app_commands.describe(show="Select True/False")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle_draw_text(self, interaction: discord.Interaction, show: bool) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.draw_text = show
        self.db.save_config(config)
        status_str = "will now" if show else "will no longer"
        await interaction.response.send_message(embed=embed_success("Success", f"Card text overlay {status_str} be drawn on the welcome card image."), ephemeral=True)

    @app_commands.describe(role="The role to assign")
    @app_commands.default_permissions(manage_guild=True)
    async def set_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.welcome_role_id = role.id
        self.db.save_config(config)
        
        await interaction.response.send_message(
            embed=embed_success(
                "Auto-Role Set",
                f"Auto-role set to {role.mention}! I will automatically give this role to users when they join.\n"
                f"🔄 Background sync started: I am now assigning this role to all existing members... this may take some time."
            ),
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

    @app_commands.default_permissions(manage_guild=True)
    async def remove_role(self, interaction: discord.Interaction) -> None:
        """Removes the member auto-role configuration."""
        config = self.db.get_config(interaction.guild.id)
        config.welcome_role_id = None
        self.db.save_config(config)
        await interaction.response.send_message(embed=embed_success("Success", "Member auto-role has been cleared. New members will no longer receive a role automatically upon joining."), ephemeral=True)

    @app_commands.describe(role="The role to assign to bots")
    @app_commands.default_permissions(manage_guild=True)
    async def set_bot_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.bot_role_id = role.id
        self.db.save_config(config)
        
        await interaction.response.send_message(
            embed=embed_success(
                "Bot Auto-Role Set",
                f"Bot auto-role set to {role.mention}! I will automatically give this ONLY to bots when they join.\n"
                f"🔄 Background sync started: I am now assigning this role to all existing bots..."
            ),
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
    async def remove_bot_role(self, interaction: discord.Interaction) -> None:
        """Removes the bot auto-role configuration."""
        config = self.db.get_config(interaction.guild.id)
        config.bot_role_id = None
        self.db.save_config(config)
        await interaction.response.send_message(embed=embed_success("Success", "Bot auto-role has been cleared. New bots will no longer receive a role automatically upon joining."), ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def autorole_status(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
        member_role = interaction.guild.get_role(config.welcome_role_id) if config.welcome_role_id else None
        bot_role = interaction.guild.get_role(config.bot_role_id) if config.bot_role_id else None

        embed = discord.Embed(
            title="🎭  Auto-Role Configuration",
            description="Roles automatically assigned when new entities join this server:",
            color=C.BRAND,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="👤  Member Auto-Role", value=member_role.mention if member_role else "`Not configured`", inline=True)
        embed.add_field(name="🤖  Bot Auto-Role", value=bot_role.mention if bot_role else "`Not configured`", inline=True)
        embed.set_footer(text="Use /autorole member <role> or /autorole bot <role> to configure")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.describe(target="Which auto-role to clear ('member', 'bot', or 'all')")
    @app_commands.choices(target=[
        app_commands.Choice(name="Member Auto-Role", value="member"),
        app_commands.Choice(name="Bot Auto-Role", value="bot"),
        app_commands.Choice(name="All Auto-Roles", value="all"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def remove_autorole_cmd(self, interaction: discord.Interaction, target: str) -> None:
        config = self.db.get_config(interaction.guild.id)
        if target == "member":
            config.welcome_role_id = None
            msg = "Member auto-role cleared."
        elif target == "bot":
            config.bot_role_id = None
            msg = "Bot auto-role cleared."
        else:
            config.welcome_role_id = None
            config.bot_role_id = None
            msg = "All auto-roles cleared."
        self.db.save_config(config)
        await interaction.response.send_message(embed=embed_success("Auto-Role Cleared", msg), ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def set_bg(self, interaction: discord.Interaction, image: discord.Attachment) -> None:
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message(embed=embed_error("Uploaded file must be an image."), ephemeral=True)
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

            await interaction.followup.send(embed=embed_success("Success", "Custom background image successfully updated!"), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=embed_error(f"Failed to process uploaded image: {exc}"), ephemeral=True)

    @app_commands.describe(url="Direct URL to a GIF or image (must end in .gif, .png, .jpg)")
    @app_commands.default_permissions(manage_guild=True)
    async def set_bg_url(self, interaction: discord.Interaction, url: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(embed=embed_error("Failed to download image from URL."), ephemeral=True)
                        return
                    bg_data = await resp.read()
                    
            is_gif = url.lower().split("?")[0].endswith(".gif")
            if is_gif:
                filename = f"bg_{interaction.guild.id}.gif"
            else:
                try:
                    img = Image.open(io.BytesIO(bg_data))
                    img.verify()
                except Exception:
                    await interaction.followup.send(embed=embed_error("The URL provided does not seem to contain a valid image."), ephemeral=True)
                    return
                filename = f"bg_{interaction.guild.id}.png"

            dest_path = os.path.join(ASSETS_DIR, filename)
            with open(dest_path, "wb") as f:
                f.write(bg_data)

            config = self.db.get_config(interaction.guild.id)
            config.background_path = dest_path
            self.db.save_config(config)

            await interaction.followup.send(embed=embed_success("Success", "Custom background image URL successfully downloaded and set!"), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=embed_error(f"Failed to process URL: {exc}"), ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def test_welcome(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
        if not config.channel_id:
            await interaction.response.send_message(embed=embed_error("Please set a welcome channel first using `/welcome channel`."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await send_welcome(interaction.user, config)
            await interaction.followup.send(embed=embed_success("Success", "Test welcome message dispatched successfully!"), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=embed_error(f"Failed to run welcome test: {exc}"), ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def leave_toggle(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.leave_enabled = not config.leave_enabled
        self.db.save_config(config)
        status = "enabled" if config.leave_enabled else "disabled"
        await interaction.response.send_message(embed=embed_success("Success", f"Leave message system is now **{status}**."), ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def leave_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        config = self.db.get_config(interaction.guild.id)
        config.leave_channel_id = channel.id
        self.db.save_config(config)
        await interaction.response.send_message(embed=embed_success("Success", f"Leave messages will now be sent in {channel.mention}."), ephemeral=True)

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
            await interaction.response.send_message(embed=embed_success("Success", "Leave image cleared."), ephemeral=True)
            return

        config.leave_image_url = url
        self.db.save_config(config)
        await interaction.response.send_message(embed=embed_success("Success", "Custom leave image URL successfully set!"), ephemeral=True)

    @app_commands.default_permissions(manage_guild=True)
    async def test_leave(self, interaction: discord.Interaction) -> None:
        config = self.db.get_config(interaction.guild.id)
        if not config.leave_channel_id:
            await interaction.response.send_message(embed=embed_error("Please set a leave channel first using `/leave channel`."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            # We override the setting temporarily to True just to ensure it sends during the test
            old_enabled = config.leave_enabled
            config.leave_enabled = True
            await send_leave(interaction.user, config)
            config.leave_enabled = old_enabled
            await interaction.followup.send(embed=embed_success("Success", "Test leave message dispatched successfully!"), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=embed_error(f"Failed to run leave test: {exc}"), ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
