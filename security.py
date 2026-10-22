"""
security.py — Advanced Security & Anti-Nuke System for GKR Bot.

Features:
  • Warning System: /warn, /warnings, /delwarn, /clearwarns
  • Configurable Punishments (e.g., 3 warnings = 1 hour mute)
  • Anti-Spam / Anti-Flood Protection
  • Anti-Mass Mention Protection
  • 🖼️ Auto Image Scanner (Sightengine API + keyword heuristics)
    - Detects: NSFW, scam/crypto fraud, gore, offensive memes
    - Auto-deletes flagged images, warns the user, logs the action
"""

from __future__ import annotations

import asyncio
import os
import io
import time
import sqlite3
import datetime
from collections import defaultdict
from typing import Optional, Dict, List, Union

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------------------------
# Constants & DB Path
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "security.sqlite3")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class SecurityDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            # Warnings Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    moderator_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            # Configuration Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS security_config (
                    guild_id TEXT PRIMARY KEY,
                    anti_spam_enabled INTEGER DEFAULT 1,
                    spam_msg_limit INTEGER DEFAULT 5,
                    spam_time_sec INTEGER DEFAULT 5,
                    mass_mention_limit INTEGER DEFAULT 5,
                    log_channel_id TEXT,
                    image_scan_enabled INTEGER DEFAULT 1
                )
            """)
            # Migrate: add image_scan_enabled column if missing
            try:
                conn.execute("ALTER TABLE security_config ADD COLUMN image_scan_enabled INTEGER DEFAULT 1")
            except Exception:
                pass  # Already exists
            # Punishment Ladder
            conn.execute("""
                CREATE TABLE IF NOT EXISTS punishment_ladder (
                    guild_id TEXT NOT NULL,
                    warn_count INTEGER NOT NULL,
                    action TEXT NOT NULL, -- 'mute', 'kick', 'ban'
                    duration_mins INTEGER, -- only applies to mute
                    PRIMARY KEY (guild_id, warn_count)
                )
            """)
            # Anti-Nuke Config Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS antinuke_config (
                    guild_id TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    strict_mode INTEGER DEFAULT 1,
                    ban_limit INTEGER DEFAULT 2,
                    kick_limit INTEGER DEFAULT 2,
                    channel_delete_limit INTEGER DEFAULT 1,
                    channel_create_limit INTEGER DEFAULT 3,
                    role_delete_limit INTEGER DEFAULT 1,
                    role_create_limit INTEGER DEFAULT 3,
                    anti_bot INTEGER DEFAULT 1,
                    action TEXT DEFAULT 'strip_roles',
                    time_window_sec INTEGER DEFAULT 20
                )
            """)
            try:
                conn.execute("ALTER TABLE antinuke_config ADD COLUMN strict_mode INTEGER DEFAULT 1")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            # Anti-Nuke Whitelist Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS antinuke_whitelist (
                    guild_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    added_by TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, target_id)
                )
            """)
            conn.commit()

    # --- Warnings ---

    def add_warning(self, guild_id: int, user_id: int, mod_id: int, reason: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                (str(guild_id), str(user_id), str(mod_id), reason, datetime.datetime.utcnow().isoformat())
            )
            warn_id = cur.lastrowid
            conn.commit()
            return warn_id

    def get_warnings(self, guild_id: int, user_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
                (str(guild_id), str(user_id))
            ).fetchall()
        return [dict(r) for r in rows]

    def remove_warning(self, guild_id: int, warn_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM warnings WHERE id = ? AND guild_id = ?",
                (warn_id, str(guild_id))
            )
            conn.commit()
            return cur.rowcount > 0

    def clear_warnings(self, guild_id: int, user_id: int) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id))
            )
            conn.commit()
            return cur.rowcount

    # --- Config ---

    def get_config(self, guild_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM security_config WHERE guild_id = ?", (str(guild_id),)).fetchone()
            if row:
                d = dict(row)
                # Ensure new field exists in result
                d.setdefault("image_scan_enabled", 1)
                return d
            # Default config
            return {
                "guild_id": str(guild_id),
                "anti_spam_enabled": 1,
                "spam_msg_limit": 5,
                "spam_time_sec": 5,
                "mass_mention_limit": 5,
                "log_channel_id": None,
                "image_scan_enabled": 1,
            }

    def update_config(self, guild_id: int, **kwargs) -> None:
        cfg = self.get_config(guild_id)
        for k, v in kwargs.items():
            cfg[k] = v
        
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO security_config 
                (guild_id, anti_spam_enabled, spam_msg_limit, spam_time_sec, mass_mention_limit, log_channel_id, image_scan_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(guild_id), cfg["anti_spam_enabled"], cfg["spam_msg_limit"], 
                cfg["spam_time_sec"], cfg["mass_mention_limit"], cfg["log_channel_id"],
                cfg.get("image_scan_enabled", 1)
            ))
            conn.commit()

    # --- Punishment Ladder ---

    def get_punishment(self, guild_id: int, warn_count: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM punishment_ladder WHERE guild_id = ? AND warn_count = ?",
                (str(guild_id), warn_count)
            ).fetchone()
            return dict(row) if row else None

    # --- Anti-Nuke Configuration & Whitelist ---

    def get_antinuke_config(self, guild_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM antinuke_config WHERE guild_id = ?", (str(guild_id),)).fetchone()
            if row:
                d = dict(row)
                d.setdefault("strict_mode", 1)
                return d
            return {
                "guild_id": str(guild_id),
                "enabled": 1,
                "strict_mode": 1,
                "ban_limit": 2,
                "kick_limit": 2,
                "channel_delete_limit": 1,
                "channel_create_limit": 3,
                "role_delete_limit": 1,
                "role_create_limit": 3,
                "anti_bot": 1,
                "action": "strip_roles",
                "time_window_sec": 20,
            }

    def update_antinuke_config(self, guild_id: int, **kwargs) -> None:
        cfg = self.get_antinuke_config(guild_id)
        for k, v in kwargs.items():
            cfg[k] = v
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO antinuke_config
                (guild_id, enabled, strict_mode, ban_limit, kick_limit, channel_delete_limit, channel_create_limit, role_delete_limit, role_create_limit, anti_bot, action, time_window_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(guild_id), cfg["enabled"], cfg.get("strict_mode", 1), cfg["ban_limit"], cfg["kick_limit"],
                cfg["channel_delete_limit"], cfg["channel_create_limit"],
                cfg["role_delete_limit"], cfg["role_create_limit"],
                cfg["anti_bot"], cfg["action"], cfg["time_window_sec"]
            ))
            conn.commit()

    def add_antinuke_whitelist(self, guild_id: int, target_id: int, added_by: int) -> bool:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO antinuke_whitelist (guild_id, target_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                    (str(guild_id), str(target_id), str(added_by), datetime.datetime.utcnow().isoformat())
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_antinuke_whitelist(self, guild_id: int, target_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND target_id = ?",
                (str(guild_id), str(target_id))
            )
            conn.commit()
            return cur.rowcount > 0

    def is_antinuke_whitelisted(self, guild_id: int, target_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM antinuke_whitelist WHERE guild_id = ? AND target_id = ?",
                (str(guild_id), str(target_id))
            ).fetchone()
            return row is not None

    def get_antinuke_whitelist(self, guild_id: int) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM antinuke_whitelist WHERE guild_id = ? ORDER BY added_at DESC",
                (str(guild_id),)
            ).fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

from gkr_ui import C, embed_error, embed_success, embed_info, embed_warning, embed_action, BOT_NAME  # noqa: E402

class SecurityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = SecurityDatabase()
        self.db.initialize()
        
        # Anti-spam tracker: (guild_id, user_id) -> list of timestamps
        self._spam_tracker: Dict[tuple[int, int], list[float]] = {}
        self._spam_lock = asyncio.Lock()

        # Anti-nuke tracker: (guild_id, user_id, action_type) -> list of timestamps
        self._antinuke_tracker: Dict[tuple[int, int, str], list[float]] = defaultdict(list)
        self._antinuke_lock = asyncio.Lock()

        # Anti-nuke audit log cache to eliminate Discord 429 rate-limiting during rapid bursts
        self._audit_cache: Dict[tuple[int, discord.AuditLogAction], tuple[float, list[discord.AuditLogEntry]]] = {}
        self._audit_lock = asyncio.Lock()

    # ── Image Scanning (PIL/EXIF-based, no external API) ────────────────────

    from PIL import Image as _PILImage, ExifTags as _ExifTags

    # Filename keywords strongly suggesting scam/malicious content
    _SCAM_FILENAMES = [
        "free", "giveaway", "win", "claim", "crypto", "bitcoin", "btc",
        "earn", "promo", "bonus", "hack", "crack", "keygen", "nft", "eth"
    ]

    # EXIF Software values that mean it's a screenshot tool (= likely a scam image grab)
    _SCREENSHOT_TOOLS = [
        "snagit", "lightshot", "gyazo", "sharex", "greenshot", "obs",
        "screenshot", "capture", "snipping", "snip"
    ]

    # Screen widths that almost always mean a screenshot
    _SCREENSHOT_WIDTHS = {720, 1024, 1280, 1366, 1440, 1600, 1920, 2560, 3840}

    async def _download_image_bytes(self, url: str) -> Optional[bytes]:
        """Download image bytes from any URL (Discord CDN or external)."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            print(f"[ImageScan] Download failed for {url}: {e}")
        return None

    def _analyze_image_bytes(
        self,
        image_bytes: bytes,
        filename: str = "image",
        file_size: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None
    ) -> dict:
        """
        Full PIL/EXIF image analysis — mirrors the /imageinfo command logic
        but focused on detecting suspicious/scam images.

        Returns: {flagged, reasons, confidence, exif_summary}
        """
        from PIL import Image, ExifTags

        reasons = []
        exif_summary = {}
        confidence = 0.0
        fname = filename.lower()
        signal_types = set()

        # ── 1. Filename keyword check ──────────────────────────────────────────────
        hits = [kw for kw in self._SCAM_FILENAMES if kw in fname]
        if hits:
            reasons.append(f"Suspicious filename: `{', '.join(hits)}`")
            confidence = max(confidence, 0.60)
            signal_types.add("filename")

        try:
            img = Image.open(io.BytesIO(image_bytes))
            w, h = img.size
            fmt = img.format or "Unknown"
            mode = img.mode
            size_kb = file_size / 1024 if file_size else len(image_bytes) / 1024

            # Use known dimensions if PIL couldn't get them (e.g. GIF)
            if width:  w = width
            if height: h = height

            # ── 2. EXIF Metadata Analysis ───────────────────────────────────────
            raw_exif = img.getexif() or {}
            TAGS = ExifTags.TAGS
            GPSTAGS = ExifTags.GPSTAGS

            # Build human-readable EXIF summary (same as /imageinfo)
            for tag_id, value in raw_exif.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                if tag_name == "GPSInfo":
                    gps = {}
                    for gid in value:
                        gps[GPSTAGS.get(gid, str(gid))] = value[gid]
                    exif_summary["GPSInfo"] = gps
                else:
                    if isinstance(value, bytes):
                        try: value = value.decode("utf-8", errors="ignore").strip()
                        except: value = "<Binary>"
                    exif_summary[tag_name] = str(value)

            software = exif_summary.get("Software", "").lower()
            make    = exif_summary.get("Make", "")
            model   = exif_summary.get("Model", "")

            # Screenshot tool in EXIF.Software
            sw_hits = [s for s in self._SCREENSHOT_TOOLS if s in software]
            if sw_hits:
                reasons.append(f"Screenshot tool in EXIF Software: `{', '.join(sw_hits)}`")
                confidence = max(confidence, 0.75)
                signal_types.add("screenshot")

            # ── 3. No EXIF + PNG + screenshot resolution = scam screenshot ───────
            if not raw_exif and fmt == "PNG":
                if w in self._SCREENSHOT_WIDTHS:
                    reasons.append(
                        f"Screenshot-resolution PNG ({w}x{h}) with no camera EXIF — likely a screen grab"
                    )
                    confidence = max(confidence, 0.70)
                    signal_types.add("screenshot")

            # ── 4. JPEG with no camera Make/Model but screenshot resolution ───────
            if fmt == "JPEG" and not make and not model and raw_exif:
                if w in self._SCREENSHOT_WIDTHS:
                    reasons.append(
                        f"JPEG at screenshot resolution ({w}x{h}) with no camera Make/Model in EXIF"
                    )
                    confidence = max(confidence, 0.55)
                    signal_types.add("screenshot")

            # ── 5. GPS in EXIF (privacy risk — flag as info, not delete) ────────
            if "GPSInfo" in exif_summary:
                reasons.append("📍 Image contains embedded GPS coordinates (privacy risk)")
                confidence = max(confidence, 0.50)
                signal_types.add("privacy")

            # ── 6. Abnormal file size vs pixel ratio (Steganography / Polyglot detection) ──
            n_frames = getattr(img, "n_frames", 1)
            total_mpx = (w * h * n_frames) / 1_000_000 if w and h else 0
            if n_frames == 1:
                # For single-frame static images: >3MB for <0.3MP is abnormal (possible embedded archive/payload)
                if size_kb > 3000 and total_mpx < 0.3:
                    reasons.append(
                        f"Suspicious: large file ({size_kb:.0f} KB) but very low resolution ({w}x{h}px) — possible embedded payload"
                    )
                    confidence = max(confidence, 0.65)
                    signal_types.add("payload")
            else:
                # For multi-frame animated GIFs: check average density per frame
                avg_frame_kb = size_kb / max(1, n_frames)
                if avg_frame_kb > 150 and (w * h) < 50000:
                    reasons.append(
                        f"Suspicious: animated image with abnormal frame density ({size_kb:.0f} KB across {n_frames} frames) — possible embedded data"
                    )
                    confidence = max(confidence, 0.65)
                    signal_types.add("payload")

            # ── 7. Solid-colour or near-blank image (often used to embed malicious data) ──
            if w > 0 and h > 0 and img.mode in ("RGB", "RGBA"):
                try:
                    small = img.resize((16, 16)).convert("RGB")
                    pixels = list(small.getdata())
                    avg_r = sum(p[0] for p in pixels) / len(pixels)
                    avg_g = sum(p[1] for p in pixels) / len(pixels)
                    avg_b = sum(p[2] for p in pixels) / len(pixels)
                    variance = sum(
                        (p[0]-avg_r)**2 + (p[1]-avg_g)**2 + (p[2]-avg_b)**2
                        for p in pixels
                    ) / len(pixels)
                    # Very low variance = nearly solid colour
                    if variance < 50 and size_kb > 500:
                        reasons.append(
                            f"Near-solid colour image ({size_kb:.0f} KB) — possible steganography or exploit payload"
                        )
                        confidence = max(confidence, 0.70)
                        signal_types.add("stego")
                except Exception:
                    pass

        except Exception as e:
            print(f"[ImageScan] PIL analysis error: {e}")

        soft_only = bool(signal_types) and signal_types.issubset({"screenshot", "privacy"})
        has_hard_combo = (
            "filename" in signal_types and ("payload" in signal_types or "stego" in signal_types)
        )
        should_delete = (confidence >= 0.85) or has_hard_combo
        if soft_only:
            should_delete = False

        return {
            "flagged": len(reasons) > 0,
            "reasons": reasons,
            "confidence": confidence,
            "exif_summary": exif_summary,
            "signal_types": sorted(signal_types),
            "should_delete": should_delete,
        }

    async def scan_and_moderate_image(
        self,
        message: discord.Message,
        attachment: discord.Attachment
    ) -> bool:
        """
        Full pipeline: download image → PIL/EXIF analysis → delete if flagged → warn user → log.
        Returns True if the image was flagged and deleted.
        """
        img_bytes = await self._download_image_bytes(attachment.url)
        if not img_bytes:
            return False

        result = self._analyze_image_bytes(
            img_bytes,
            filename=attachment.filename,
            file_size=attachment.size,
            width=attachment.width,
            height=attachment.height
        )

        if not result["flagged"]:
            return False

        if not result.get("should_delete", False):
            reasons_str = "\n".join(f"• {r}" for r in result["reasons"])
            await self.log_security_action(
                message.guild,
                "🖼️ Image Scan — Soft Flag (Not Deleted)",
                (
                    f"**User:** {message.author.mention} (`{message.author}`)"
                    f"\n**Channel:** {message.channel.mention}"
                    f"\n**File:** `{attachment.filename}` ({attachment.size // 1024} KB  {attachment.width or '?'}x{attachment.height or '?'}px)"
                    f"\n**Confidence:** {result['confidence']:.0%}"
                    f"\n**Signals:** `{', '.join(result.get('signal_types', [])) or 'none'}`"
                    f"\n**Action:** Logged only (no deletion)"
                    f"\n**Reasons:**\n{reasons_str}"
                ),
                color=0xF1C40F
            )
            return False

        reasons_str = "\n".join(f"• {r}" for r in result["reasons"])

        # Delete the message
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"[ImageScan] Could not delete message: {e}")

        # Issue auto-warning
        reason = f"Automod: Flagged image — {', '.join(result['reasons'][:2])}"
        warn_id = self.db.add_warning(message.guild.id, message.author.id, self.bot.user.id, reason)
        warns = self.db.get_warnings(message.guild.id, message.author.id)

        # Send a brief notice in channel
        embed = discord.Embed(
            title="🚨  Flagged Image Removed",
            description=(
                f"{message.author.mention}'s image was **automatically deleted** by {BOT_NAME} Security.\n\n"
                f"**Reason(s):**\n{reasons_str}"
            ),
            color=0xFF0000
        )
        embed.set_footer(text=f"{BOT_NAME} Security  •  Warning #{len(warns)} issued  •  PIL/EXIF Scanner")
        try:
            await message.channel.send(embed=embed, delete_after=15)
        except Exception:
            pass

        # Log to security channel
        await self.log_security_action(
            message.guild,
            "🖼️ Image Scan — Flagged & Deleted",
            (
                f"**User:** {message.author.mention} (`{message.author}`)"
                f"\n**Channel:** {message.channel.mention}"
                f"\n**File:** `{attachment.filename}` ({attachment.size // 1024} KB  {attachment.width or '?'}x{attachment.height or '?'}px)"
                f"\n**Scanner:** PIL/EXIF Analysis"
                f"\n**Confidence:** {result['confidence']:.0%}"
                f"\n**Reasons:**\n{reasons_str}"
                f"\n**Warning:** `#{warn_id}` (Total: {len(warns)})"
            ),
            color=0xFF0000,
            event="security_image_flagged"
        )

        # Apply punishment ladder
        await self.execute_punishment(message.author, len(warns), reason)
        return True

    # ── Helpers ─────────────────────────────────────────────────────────────
    
    async def log_security_action(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        color: int = 0xFF0000,
        thumbnail_url: Optional[str] = None,
        event: str = "security_warn",
    ) -> None:
        """
        Dual-dispatch security log:
        1. Legacy path — sends to security_config.log_channel_id (or fallback name-search).
        2. New path    — dispatches through server_logs security category channel.
        """
        # ── Path 1: Legacy direct security log channel ──────────────────────────
        cfg = self.db.get_config(guild.id)
        channel = None
        if cfg and cfg.get("log_channel_id"):
            try:
                channel = guild.get_channel(int(cfg["log_channel_id"]))
            except Exception:
                pass

        if not channel:
            for ch in guild.text_channels:
                name = ch.name.lower()
                if "security" in name or "mod-log" in name or "member-log" in name or "audit-log" in name:
                    channel = ch
                    break

        if channel:
            embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            embed.set_footer(text=f"{BOT_NAME} Security  •  Audit & Defense Log")
            try:
                await channel.send(embed=embed)
            except Exception as e:
                print(f"[SecurityLog] Failed to send log to #{channel.name}: {e}")

        # ── Path 2: Route through server_logs security category channel ─────────
        try:
            server_logs_cog = self.bot.get_cog("ServerLogsCog")
            if server_logs_cog and hasattr(server_logs_cog, "logger"):
                await server_logs_cog.logger.dispatch_security(
                    guild, event, title, description, color=color, thumbnail_url=thumbnail_url
                )
        except Exception as e:
            print(f"[SecurityLog] server_logs dispatch failed: {e}")


    async def execute_punishment(self, member: discord.Member, warn_count: int, reason: str):
        punishment = self.db.get_punishment(member.guild.id, warn_count)
        if not punishment:
            return

        action = punishment["action"].lower()
        guild = member.guild
        
        try:
            if action == "mute":
                duration = punishment.get("duration_mins", 60)
                until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
                await member.timeout(until, reason=f"Auto-Punishment: Reached {warn_count} warnings. {reason}")
                await self.log_security_action(guild, "🛡️ Auto-Punishment: Mute", f"**{member.mention}** (`{member}`) was muted for {duration}m.\n**Reason:** Reached {warn_count} warnings.", color=0xFF0000, thumbnail_url=member.display_avatar.url, event="security_auto_timeout")
                
            elif action == "kick":
                await member.kick(reason=f"Auto-Punishment: Reached {warn_count} warnings. {reason}")
                await self.log_security_action(guild, "🛡️ Auto-Punishment: Kick", f"**{member.mention}** (`{member}`) was kicked.\n**Reason:** Reached {warn_count} warnings.", color=0xFF0000, thumbnail_url=member.display_avatar.url, event="security_auto_kick")
                
            elif action == "ban":
                await member.ban(reason=f"Auto-Punishment: Reached {warn_count} warnings. {reason}")
                await self.log_security_action(guild, "🛡️ Auto-Punishment: Ban", f"**{member.mention}** (`{member}`) was banned.\n**Reason:** Reached {warn_count} warnings.", color=0xFF0000, thumbnail_url=member.display_avatar.url, event="security_auto_ban")
        except discord.Forbidden:
            await self.log_security_action(guild, "⚠️ Punishment Failed", f"Could not {action} {member.mention}. Missing permissions or role hierarchy issue.", event="security_warn")

    # ── Moderation Audit Listeners (Bans, Unbans, Kicks, Timeouts) ───────────

    async def _fetch_audit_entries(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        limit: int = 25,
        cache_ttl: float = 1.5
    ) -> list[discord.AuditLogEntry]:
        """
        Fetch audit log entries with caching. Lock is NOT held during HTTP
        to avoid serializing hundreds of concurrent events.
        """
        if not guild or not guild.me:
            return []
        perms = getattr(guild.me, "guild_permissions", None)
        if not perms or not perms.view_audit_log:
            return []

        now = time.time()
        key = (guild.id, action)

        # Fast path: return cached under lock
        async with self._audit_lock:
            cached = self._audit_cache.get(key)
            if cached and (now - cached[0] < cache_ttl):
                return cached[1]

        # Slow path: fetch OUTSIDE lock to avoid blocking concurrent events
        entries: list[discord.AuditLogEntry] = []
        try:
            async for entry in guild.audit_logs(limit=limit, action=action):
                entries.append(entry)
        except discord.HTTPException:
            async with self._audit_lock:
                cached = self._audit_cache.get(key)
            return cached[1] if cached else []
        except Exception:
            async with self._audit_lock:
                cached = self._audit_cache.get(key)
            return cached[1] if cached else []

        # Store under lock
        async with self._audit_lock:
            self._audit_cache[key] = (now, entries)
        return entries

    async def _get_audit_entry(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: Optional[int] = None,
        max_age_seconds: Optional[float] = 15.0
    ) -> Optional[discord.AuditLogEntry]:
        """Safely fetch a matching audit log entry using cached audit log entries."""
        entries = await self._fetch_audit_entries(guild, action, limit=10, cache_ttl=1.5)
        now = discord.utils.utcnow()
        for entry in entries:
            if target_id is not None:
                t_id = getattr(entry.target, "id", None)
                if t_id != target_id:
                    continue
            if max_age_seconds is not None:
                age = (now - entry.created_at).total_seconds()
                if age > max_age_seconds:
                    break
            return entry
        return None

    # ── Anti-Nuke Defense Engine ──────────────────────────────────────────────

    async def _handle_antinuke_action(
        self,
        guild: discord.Guild,
        audit_action: discord.AuditLogAction,
        action_name: str,
        limit_key: str,
        target_id: Optional[int] = None,
    ) -> None:
        if not guild or not guild.me:
            return

        cfg = self.db.get_antinuke_config(guild.id)
        if not cfg.get("enabled"):
            return

        strict = bool(cfg.get("strict_mode", 1))
        if strict and limit_key in ("channel_delete_limit", "role_delete_limit"):
            limit = 1
        else:
            limit = cfg.get(limit_key, 2 if strict else 3)

        window = cfg.get("time_window_sec", 20)
        now_ts = time.time()

        # STEP 1: Increment in-memory counter IMMEDIATELY (no audit log wait)
        # Use guild-level key first so we can detect mass action before knowing executor
        guild_tracker_key = (guild.id, 0, action_name)  # 0 = unknown executor
        async with self._antinuke_lock:
            guild_history = self._antinuke_tracker[guild_tracker_key]
            guild_history = [t for t in guild_history if now_ts - t <= window]
            guild_history.append(now_ts)
            self._antinuke_tracker[guild_tracker_key] = guild_history
            guild_count = len(guild_history)

        # Not at limit yet, skip audit log fetch entirely
        if guild_count < limit:
            return

        # STEP 2: Limit reached — now fetch audit logs to identify executor
        entries = await self._fetch_audit_entries(guild, audit_action, limit=25, cache_ttl=1.5)

        now = discord.utils.utcnow()
        matching_entry = None
        for e in entries:
            if target_id is not None and getattr(e.target, "id", None) != target_id:
                continue
            if (now - e.created_at).total_seconds() <= window:
                matching_entry = e
                break

        if not matching_entry and entries:
            if (now - entries[0].created_at).total_seconds() <= window:
                matching_entry = entries[0]

        if not matching_entry or not matching_entry.user:
            return

        executor = matching_entry.user
        if executor.id == guild.owner_id or executor.id == self.bot.user.id:
            return

        if self.db.is_antinuke_whitelisted(guild.id, executor.id):
            return

        # Deduplicate: track per-executor to avoid punishing same person multiple times
        executor_key = (guild.id, executor.id, action_name)
        should_punish = False
        async with self._antinuke_lock:
            exec_history = self._antinuke_tracker[executor_key]
            exec_history = [t for t in exec_history if now_ts - t <= window]
            exec_history.append(now_ts)
            self._antinuke_tracker[executor_key] = exec_history
            count = len(exec_history)
            if count >= limit:
                # Clear both trackers to avoid re-triggering
                self._antinuke_tracker[executor_key] = []
                self._antinuke_tracker[guild_tracker_key] = []
                should_punish = True

        if not should_punish:
            return

        member = guild.get_member(executor.id)
        if not member:
            try:
                member = await guild.fetch_member(executor.id)
            except Exception:
                member = None

        await self._punish_nuker(
            guild=guild,
            executor=member or executor,
            action_name=action_name,
            count=count,
            limit=limit,
            punishment=cfg.get("action", "strip_roles"),
        )

    async def _punish_nuker(
        self,
        guild: discord.Guild,
        executor: Union[discord.Member, discord.User],
        action_name: str,
        count: int,
        limit: int,
        punishment: str = "strip_roles",
    ) -> None:
        action_taken = "No action (Hierarchy / Permission Issue)"
        success = False

        if isinstance(executor, discord.Member):
            if executor.top_role >= guild.me.top_role and executor.id != guild.owner_id:
                action_taken = "⚠️ Failed: Culprit role equal/above bot role. Move bot role higher!"
            else:
                # 1. Instant Quarantine Timeout (28 days max Discord timeout) to freeze culprit immediately
                try:
                    await executor.timeout(datetime.timedelta(days=28), reason=f"[Anti-Nuke] Instant Quarantine: {action_name} spam")
                    action_taken = "⏱️ Timed out 28 days"
                    success = True
                except Exception:
                    pass

                # 2. Execute selected penalty
                if punishment == "ban":
                    try:
                        await guild.ban(executor, reason=f"[Anti-Nuke Triggered] Exceeded {action_name} limit ({count}/{limit})", delete_message_days=1)
                        action_taken = "🔨 Banned from server"
                        success = True
                    except Exception as e:
                        action_taken = f"⚠️ Failed to ban: {e}"
                elif punishment == "kick":
                    try:
                        await executor.kick(reason=f"[Anti-Nuke Triggered] Exceeded {action_name} limit ({count}/{limit})")
                        action_taken = "👢 Kicked from server"
                        success = True
                    except Exception as e:
                        action_taken = f"⚠️ Failed to kick: {e}"
                else:  # strip_roles
                    roles_to_remove = [
                        r for r in executor.roles
                        if not r.is_default() and not r.managed and r < guild.me.top_role
                    ]
                    if roles_to_remove:
                        try:
                            await executor.remove_roles(*roles_to_remove, reason=f"[Anti-Nuke] Exceeded {action_name} limit ({count}/{limit})")
                            action_taken = f"🛡️ Stripped {len(roles_to_remove)} role(s) + 28d Quarantine Timeout"
                            success = True
                        except Exception as e:
                            action_taken += f" (⚠️ Role strip failed: {e})"
                    else:
                        action_taken += " (No removable roles)"

        else:
            if punishment == "ban":
                try:
                    await guild.ban(executor, reason=f"[Anti-Nuke Triggered] Exceeded {action_name} limit ({count}/{limit})")
                    action_taken = "🔨 Banned from server"
                    success = True
                except Exception as e:
                    action_taken = f"⚠️ Failed to ban: {e}"

        await self.log_security_action(
            guild=guild,
            title="🚨 Anti-Nuke Triggered",
            description=(
                f"**Culprit:** {executor.mention} (`{executor}`)\n"
                f"**Violation:** Mass {action_name} (`{count}/{limit}` actions)\n"
                f"**Action Taken:** `{action_taken}`\n"
                f"**Status:** {'🛡️ Neutralized' if success else '⚠️ Attention Required'}"
            ),
            color=0xFF0000,
            event="security_auto_ban"
        )

    # ── Audit Listeners ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: Union[discord.User, discord.Member]) -> None:
        """Log all bans and monitor for Anti-Nuke mass ban attempts."""
        mod = None
        reason = "No reason provided"
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.ban, target_id=user.id, max_age_seconds=15.0)
        if entry:
            mod = entry.user
            if entry.reason:
                reason = entry.reason

        avatar = user.display_avatar.url if hasattr(user, "display_avatar") else None
        mod_str = mod.mention if mod else "*Unknown Moderator*"
        await self.log_security_action(
            guild,
            "🔨 Member Banned",
            f"**Member:** {user.mention} (`{user}`)\n**Moderator:** {mod_str}\n**Reason:** {reason}",
            color=0xFF0000,
            thumbnail_url=avatar,
            event="security_auto_ban"
        )
        # Anti-Nuke mass ban check
        await self._handle_antinuke_action(guild, discord.AuditLogAction.ban, "Member Ban", "ban_limit")

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """Log unbans to security logs."""
        mod = None
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.unban, target_id=user.id, max_age_seconds=15.0)
        if entry:
            mod = entry.user

        avatar = user.display_avatar.url if hasattr(user, "display_avatar") else None
        mod_str = mod.mention if mod else "*Unknown Moderator*"
        await self.log_security_action(
            guild,
            "✅ Member Unbanned",
            f"**Member:** {user.mention} (`{user}`)\n**Moderator:** {mod_str}",
            color=0x57F287,
            thumbnail_url=avatar,
            event="security_warn"
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Detect and log kicks to security logs, and monitor for Anti-Nuke mass kicks."""
        guild = member.guild
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.kick, target_id=member.id, max_age_seconds=7.0)
        if entry:
            kicker = entry.user
            kick_reason = entry.reason or "No reason provided"
            await self.log_security_action(
                guild,
                "👢 Member Kicked",
                f"**Member:** {member.mention} (`{member}`)\n**Moderator:** {kicker.mention}\n**Reason:** {kick_reason}",
                color=0xFF0000,
                thumbnail_url=member.display_avatar.url,
                event="security_auto_kick"
            )
            # Anti-Nuke mass kick check
            await self._handle_antinuke_action(guild, discord.AuditLogAction.kick, "Member Kick", "kick_limit")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Anti-Nuke channel delete listener."""
        await self._handle_antinuke_action(channel.guild, discord.AuditLogAction.channel_delete, "Channel Delete", "channel_delete_limit")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Anti-Nuke channel create listener."""
        await self._handle_antinuke_action(channel.guild, discord.AuditLogAction.channel_create, "Channel Create", "channel_create_limit")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Anti-Nuke role delete listener."""
        await self._handle_antinuke_action(role.guild, discord.AuditLogAction.role_delete, "Role Delete", "role_delete_limit")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """Anti-Nuke role create listener."""
        await self._handle_antinuke_action(role.guild, discord.AuditLogAction.role_create, "Role Create", "role_create_limit")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Anti-Bot defense: allow bots to be added, but strip all roles and power if unwhitelisted."""
        if not member.bot:
            return
        cfg = self.db.get_antinuke_config(member.guild.id)
        if not cfg.get("enabled"):
            return
        if self.db.is_antinuke_whitelisted(member.guild.id, member.id):
            return

        entry = await self._get_audit_entry(member.guild, discord.AuditLogAction.bot_add, target_id=member.id, max_age_seconds=20.0)
        inviter = entry.user if entry else None
        inviter_str = inviter.mention if inviter else "*Unknown*"

        async def _strip_bot_power(target: discord.Member) -> None:
            """Strip all roles and neuter managed roles for an unwhitelisted bot."""
            # Strip all removable non-managed roles
            roles_to_strip = [r for r in target.roles if not r.is_default() and not r.managed and r < target.guild.me.top_role]
            if roles_to_strip:
                try:
                    await target.remove_roles(*roles_to_strip, reason="[Anti-Nuke] Unwhitelisted bot: All roles stripped, power denied")
                except Exception:
                    pass
            # Neuter managed integration roles with dangerous perms
            for r in target.roles:
                if r.managed and r < target.guild.me.top_role:
                    try:
                        perms = r.permissions
                        if perms.administrator or perms.manage_guild or perms.manage_channels or perms.manage_roles or perms.ban_members or perms.kick_members or perms.mention_everyone:
                            safe_perms = discord.Permissions(send_messages=True, read_messages=True, view_channel=True)
                            await r.edit(permissions=safe_perms, reason="[Anti-Nuke] Stripped dangerous power from unwhitelisted bot")
                    except Exception:
                        pass

        # Immediate strip
        await _strip_bot_power(member)

        # Wait for Discord to assign the managed integration role, then strip again
        await asyncio.sleep(3)
        try:
            refreshed = member.guild.get_member(member.id)
            if refreshed:
                await _strip_bot_power(refreshed)
        except Exception:
            pass

        await self.log_security_action(
            member.guild,
            "🤖 Unwhitelisted Bot Joined — Power Stripped",
            f"**Bot:** {member.mention} (`{member}`)\n**Added By:** {inviter_str}\n**Status:** Bot allowed to join, but ALL roles and administrative powers were stripped.\n**Action:** Use `/whitelist` to grant this bot power.",
            color=0xFAA61A,
            event="security_warn"
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Detect timeouts / mutes and log to security logs."""
        if before.timed_out_until != after.timed_out_until:
            guild = after.guild
            mod = None
            reason = "No reason provided"
            entry = await self._get_audit_entry(guild, discord.AuditLogAction.member_update, after.id, max_age_seconds=10.0)
            if entry:
                mod = entry.user
                if entry.reason:
                    reason = entry.reason

            mod_str = mod.mention if mod else "*Unknown Moderator / AutoMod*"
            if after.timed_out_until and after.timed_out_until > discord.utils.utcnow():
                # Timed out
                expires_str = f"<t:{int(after.timed_out_until.timestamp())}:R>"
                await self.log_security_action(
                    guild,
                    "⏱️ Member Timed Out (Muted)",
                    f"**Member:** {after.mention} (`{after}`)\n**Moderator:** {mod_str}\n**Expires:** {expires_str}\n**Reason:** {reason}",
                    color=0xFAA61A,
                    thumbnail_url=after.display_avatar.url,
                    event="security_auto_timeout"
                )
            elif before.timed_out_until and (not after.timed_out_until or after.timed_out_until <= discord.utils.utcnow()):
                # Timeout removed
                await self.log_security_action(
                    guild,
                    "🔊 Member Timeout Removed (Unmuted)",
                    f"**Member:** {after.mention} (`{after}`)\n**Moderator:** {mod_str}\n**Reason:** {reason}",
                    color=0x57F287,
                    thumbnail_url=after.display_avatar.url,
                    event="security_warn"
                )

        # Check role assignments: if unwhitelisted member or bot gained dangerous permissions, strip them!
        if before.roles != after.roles and after.id != after.guild.owner_id and after.id != self.bot.user.id:
            added_roles = [r for r in after.roles if r not in before.roles]
            if added_roles:
                cfg = self.db.get_antinuke_config(after.guild.id)
                if cfg.get("enabled"):
                    is_wl = self.db.is_antinuke_whitelisted(after.guild.id, after.id)
                    if not is_wl:
                        dangerous_removable = []
                        dangerous_managed = []
                        for r in added_roles:
                            perms = r.permissions
                            if (perms.administrator or perms.manage_guild or perms.manage_channels or 
                                perms.manage_roles or perms.ban_members or perms.kick_members or perms.mention_everyone):
                                if r < after.guild.me.top_role:
                                    if r.managed:
                                        dangerous_managed.append(r)
                                    else:
                                        dangerous_removable.append(r)
                        # Remove non-managed dangerous roles
                        if dangerous_removable:
                            try:
                                await after.remove_roles(*dangerous_removable, reason="[Anti-Nuke] Power roles denied: Member/bot is not whitelisted!")
                            except Exception:
                                pass
                        # Neuter managed roles (bot integration roles) — can't remove, so strip perms
                        for r in dangerous_managed:
                            try:
                                safe_perms = discord.Permissions(send_messages=True, read_messages=True, view_channel=True)
                                await r.edit(permissions=safe_perms, reason="[Anti-Nuke] Stripped dangerous power from unwhitelisted bot role")
                            except Exception:
                                pass
                        all_dangerous = dangerous_removable + dangerous_managed
                        if all_dangerous:
                            try:
                                await self.log_security_action(
                                    after.guild,
                                    "🛡️ Unauthorized Power Role Revoked",
                                    f"**Target:** {after.mention} (`{after}`)\n**Roles Revoked/Neutered:** {', '.join(r.name for r in all_dangerous)}\n**Reason:** Not on Anti-Nuke Whitelist. Use `/whitelist` to grant power.",
                                    color=0xFF0000,
                                    event="security_warn"
                                )
                            except Exception:
                                pass

    # ── Listeners ───────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
            
        guild_id = message.guild.id
        user_id = message.author.id
        cfg = self.db.get_config(guild_id)
        now = asyncio.get_running_loop().time()

        # 0. Image Scanning — runs before other checks
        if cfg.get("image_scan_enabled", 1):
            image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
            for att in message.attachments:
                ext = os.path.splitext(att.filename.lower())[1]
                is_image = ext in image_exts or (att.content_type and att.content_type.startswith("image/"))
                if is_image:
                    try:
                        flagged = await self.scan_and_moderate_image(message, att)
                        if flagged:
                            return  # Message already deleted; stop processing
                    except Exception as e:
                        print(f"[ImageScan] Error scanning {att.filename}: {e}")

        # 1. Anti-Everyone / Anti-Here Raid Protection
        # Blocks unauthorized mass @everyone / @here pings, while allowing normal multiple user mentions
        if message.mention_everyone:
            if isinstance(message.author, discord.Member) and not message.author.guild_permissions.mention_everyone:
                try:
                    await message.delete()
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    pass
                
                reason = "Automod: Unauthorized @everyone/@here mass ping attempt"
                warn_id = self.db.add_warning(guild_id, user_id, self.bot.user.id, reason)
                warns = self.db.get_warnings(guild_id, user_id)
                embed = discord.Embed(
                    title="🚨  Unauthorized Mass Ping Blocked",
                    description=f"{message.author.mention} was warned for attempting an unauthorized `@everyone` or `@here` ping. (Warning #{len(warns)})",
                    color=C.DANGER
                )
                embed.set_footer(text=f"{BOT_NAME} Security  •  Anti-Raid Protection")
                try:
                    await message.channel.send(embed=embed, delete_after=10)
                except Exception:
                    pass
                await self.log_security_action(
                    message.guild,
                    "🚨 Unauthorized @everyone / @here Blocked",
                    f"**User:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Action:** Message deleted & warned.",
                    color=0xFF0000,
                    thumbnail_url=message.author.display_avatar.url,
                    event="security_anti_raid"
                )
                await self.execute_punishment(message.author, len(warns), reason)
                return  # Stop processing this message further

        # 2. Anti-Spam Check
        if cfg["anti_spam_enabled"]:
            limit = cfg["spam_msg_limit"]
            time_window = cfg["spam_time_sec"]
            
            async with self._spam_lock:
                key = (guild_id, user_id)
                times = self._spam_tracker.get(key, [])
                
                # Filter old timestamps
                times = [t for t in times if now - t <= time_window]
                times.append(now)
                self._spam_tracker[key] = times
                
                if len(times) > limit:
                    # User is spamming!
                    # Clear their tracker so we don't trigger this 100 times
                    self._spam_tracker[key] = []
                    
                    reason = "Automod: Message spam/flood"
                    warn_id = self.db.add_warning(guild_id, user_id, self.bot.user.id, reason)
                    warns = self.db.get_warnings(guild_id, user_id)
                    
                    try:
                        # Mute them immediately for 5 minutes as a base spam response
                        until = discord.utils.utcnow() + datetime.timedelta(minutes=5)
                        if isinstance(message.author, discord.Member):
                            await message.author.timeout(until, reason="Automod: Spam prevention")
                        
                        embed = discord.Embed(
                            title="🛡️  Spam Detected",
                            description=f"{message.author.mention} has been muted for 5 minutes for flooding the chat.",
                            color=C.DANGER
                        )
                        embed.set_footer(text=f"{BOT_NAME} Security")
                        await message.channel.send(embed=embed, delete_after=10)
                        await self.log_security_action(
                            message.guild,
                            "🚨 Anti-Spam Triggered",
                            f"**User:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Action:** 5-minute mute & warning issued.",
                            color=0xFF0000,
                            thumbnail_url=message.author.display_avatar.url,
                            event="security_anti_spam"
                        )
                    except discord.Forbidden:
                        try:
                            await self.execute_punishment(message.author, len(warns), reason)
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"[Security] Anti-spam timeout failed: {e}")
                        try:
                            # Also check the overall punishment ladder
                            await self.execute_punishment(message.author, len(warns), reason)
                        except Exception:
                            pass

    # ── Slash Commands ──────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Issue a formal warning to a member")
    @app_commands.describe(user="The member to warn", reason="Reason for the warning")
    @app_commands.default_permissions(moderate_members=True)
    async def warn_user(self, interaction: discord.Interaction, user: discord.Member, reason: str) -> None:
        if user.bot:
            await interaction.response.send_message(embed=embed_error("You cannot issue warnings to bot accounts."), ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=embed_error("You cannot warn yourself."), ephemeral=True)
            return

        warn_id = self.db.add_warning(interaction.guild.id, user.id, interaction.user.id, reason)
        warns = self.db.get_warnings(interaction.guild.id, user.id)
        total_warns = len(warns)

        embed = create_moderation_embed(
            action_title="⚠️  Warning Issued",
            user=user,
            moderator=interaction.user,
            reason=reason,
            extra_info=f"**Total Warnings:** `{total_warns}`",
            color=C.WARNING
        )
        await interaction.response.send_message(embed=embed)

        await self.log_security_action(
            interaction.guild,
            "⚠️ Warning Logged",
            f"**Member:** {user.mention}\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}\n**Total:** `{total_warns}` warnings",
            color=0xFAA61A,
            event="security_warn"
        )
        await self.execute_punishment(user, total_warns, reason)

        # DM User
        try:
            dm_embed = discord.Embed(
                title=f"⚠️  Warning Received — {interaction.guild.name}",
                description=f"You received a formal warning in **{interaction.guild.name}**.\n\n**Reason:**\n> {reason}\n\n**Total Warnings:** `{total_warns}`",
                color=C.WARNING
            )
            dm_embed.set_footer(text="Repeated violations may result in timeouts or bans")
            await user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    @app_commands.command(name="warnings", description="View a member's warning history")
    @app_commands.describe(user="The member to inspect")
    @app_commands.default_permissions(moderate_members=True)
    async def view_warnings(self, interaction: discord.Interaction, user: discord.Member) -> None:
        warns = self.db.get_warnings(interaction.guild.id, user.id)

        if not warns:
            await interaction.response.send_message(
                embed=embed_success("Clean Record", f"{user.mention} has no active warnings on record."),
                ephemeral=True
            )
            return

        lines = []
        for w in warns[:10]:
            try:
                dt = datetime.datetime.fromisoformat(w["timestamp"])
                ts_str = fmt_rel(dt)
            except Exception:
                ts_str = "Recently"
            lines.append(f"• Warning `#{w['id']}` ({ts_str}) by <@{w['moderator_id']}>\n> {w['reason']}")

        embed = discord.Embed(
            title=f"📋  Warning History — {user.display_name}",
            description=f"{user.mention} has **{len(warns):,}** warning(s) on record.\n\n" + "\n\n".join(lines),
            color=C.WARNING
        )
        if hasattr(user, "display_avatar") and user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)
        if len(warns) > 10:
            embed.set_footer(text=f"Showing latest 10 of {len(warns):,} total warnings")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delwarn", description="Delete a specific warning by its ID")
    @app_commands.describe(warning_id="The warning ID (found in /warnings)")
    @app_commands.default_permissions(moderate_members=True)
    async def delwarn(self, interaction: discord.Interaction, warning_id: int) -> None:
        success = self.db.remove_warning(interaction.guild.id, warning_id)
        if success:
            await interaction.response.send_message(
                embed=embed_success("Warning Removed", f"Warning `#{warning_id}` has been deleted from records."),
                ephemeral=True
            )
            await self.log_security_action(
                interaction.guild, "🗑️ Warning Deleted",
                f"**Moderator:** {interaction.user.mention}\n**Warning ID:** `#{warning_id}`",
                color=0x4E5058,
                event="security_warn"
            )
        else:
            await interaction.response.send_message(embed=embed_error(f"Warning `#{warning_id}` could not be found."), ephemeral=True)

    @app_commands.command(name="clearwarns", description="Clear all warnings for a member")
    @app_commands.describe(user="The member to clear warnings for")
    @app_commands.default_permissions(administrator=True)
    async def clearwarns(self, interaction: discord.Interaction, user: discord.Member) -> None:
        count = self.db.clear_warnings(interaction.guild.id, user.id)
        await interaction.response.send_message(
            embed=embed_success("Warnings Cleared", f"Removed **{count:,}** warning(s) from {user.mention}'s record."),
            ephemeral=True
        )
        await self.log_security_action(
            interaction.guild, "🧹 Warnings Cleared",
            f"**Moderator:** {interaction.user.mention}\n**Member:** {user.mention}\n**Cleared Count:** `{count:,}`",
            color=0x4E5058,
            event="security_warn"
        )

    @app_commands.command(name="imagescan", description="Toggle automatic image scanning for this server")
    @app_commands.describe(enabled="Turn image scanning ON or OFF")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable", value=1),
        app_commands.Choice(name="Disable", value=0),
    ])
    @app_commands.default_permissions(administrator=True)
    async def imagescan_toggle(self, interaction: discord.Interaction, enabled: int) -> None:
        self.db.update_config(interaction.guild.id, image_scan_enabled=enabled)
        state_str = "Enabled" if enabled else "Disabled"

        embed = embed_success("Image Scan Setting Updated", f"Auto image scanning is now **{state_str}** for this server.") if enabled else embed_warning(f"Auto image scanning is now **{state_str}**.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        await self.log_security_action(
            interaction.guild,
            f"🖼️ Image Scanner {state_str}",
            f"**Moderator:** {interaction.user.mention}\n**Status:** `{state_str}`",
            color=0x57F287 if enabled else 0xFAA61A,
            event="security_warn"
        )

    @app_commands.command(name="imagescan_test", description="Test the image scanner against a sample file or URL")
    @app_commands.describe(image="Upload an image file to scan", url="Or paste a direct image URL (https://...)")
    @app_commands.default_permissions(administrator=True)
    async def imagescan_test(self, interaction: discord.Interaction, image: Optional[discord.Attachment] = None, url: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)

        img_bytes = None
        display_name = ""
        display_url = ""
        width = height = file_size = 0

        if image:
            if not (image.content_type and image.content_type.startswith("image/")):
                await interaction.followup.send(embed=embed_error("Please upload a valid image file."), ephemeral=True)
                return
            img_bytes = await image.read()
            display_name = image.filename
            display_url = image.url
            width = image.width or 0
            height = image.height or 0
            file_size = image.size
        elif url:
            url = url.strip()
            if not url.startswith(("http://", "https://")):
                await interaction.followup.send(embed=embed_error("Invalid URL. Must start with `https://`."), ephemeral=True)
                return
            img_bytes = await self._download_image_bytes(url)
            if not img_bytes:
                await interaction.followup.send(embed=embed_error("Could not download image from that URL."), ephemeral=True)
                return
            display_name = url.split("/")[-1].split("?")[0] or "image"
            display_url = url
            file_size = len(img_bytes)
        else:
            await interaction.followup.send(embed=embed_error("Please upload an image file or provide a direct image URL."), ephemeral=True)
            return

        result = self._analyze_image_bytes(img_bytes, filename=display_name, file_size=file_size, width=width, height=height)
        is_flagged = result["flagged"]

        lines = [
            f"**Verdict:** {'🚨 **FLAGGED** (Would be deleted)' if is_flagged else '✅ **CLEAN** (Allowed)'}",
            f"**Confidence:** `{result['confidence']:.0%}` · **File:** `{display_name}`",
        ]
        if result["reasons"]:
            lines.append("\n**Detected Issues:**")
            for r in result["reasons"]:
                lines.append(f"• {r}")

        embed = discord.Embed(
            title="🔬  Image Scanner Diagnostic Test",
            description="\n".join(lines),
            color=C.DANGER if is_flagged else C.SUCCESS
        )
        if display_url:
            embed.set_thumbnail(url=display_url)
        embed.set_footer(text="Diagnostic mode — no moderation action taken")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Security Configuration Commands ─────────────────────────────────────

    security_group = app_commands.Group(name="security", description="Security and Anti-Nuke management commands")

    @security_group.command(name="logchannel", description="Set the channel where security alerts, bans, and timeouts are logged")
    @app_commands.describe(channel="The channel for security and moderation audit logs")
    @app_commands.default_permissions(administrator=True)
    async def security_logchannel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        self.db.update_config(interaction.guild.id, log_channel_id=channel.id)
        embed = embed_success(
            "Security Log Channel Configured",
            f"Security alerts, bans, kicks, timeouts, and anti-raid logs will now be sent to {channel.mention}."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.log_security_action(
            interaction.guild,
            "🛡️ Security Log Channel Updated",
            f"**Moderator:** {interaction.user.mention}\n**New Log Channel:** {channel.mention}",
            color=C.SUCCESS
        )

    @security_group.command(name="status", description="View current security defense & logging configuration")
    @app_commands.default_permissions(administrator=True)
    async def security_status(self, interaction: discord.Interaction) -> None:
        cfg = self.db.get_config(interaction.guild.id)
        log_ch_id = cfg.get("log_channel_id")
        log_ch = interaction.guild.get_channel(int(log_ch_id)) if log_ch_id else None
        
        status_lines = [
            f"• **Security Logs Channel:** {log_ch.mention if log_ch else '`Auto-Detect (Fallback Active)`'}",
            f"• **Anti-Spam / Flood:** {'`Enabled`' if cfg.get('anti_spam_enabled') else '`Disabled`'} ({cfg.get('spam_msg_limit', 5)} msgs / {cfg.get('spam_time_sec', 5)}s)",
            f"• **Anti-Everyone / Here:** `Enabled (Unauthorized Block & Auto-Warn)`",
            f"• **User Mentions:** `Allowed (Friends & Group Tagging Permitted)`",
            f"• **Auto Image Scanner:** {'`Enabled`' if cfg.get('image_scan_enabled') else '`Disabled`'}",
            f"• **Anti-Nuke Defense:** `Active (/antinuke status)`",
            f"• **Moderation Audit Logging:** `Bans, Unbans, Kicks, Timeouts (Active)`",
        ]

        embed = discord.Embed(
            title=f"🛡️  {BOT_NAME} Security Status — {interaction.guild.name}",
            description="\n".join(status_lines),
            color=C.BRAND
        )
        embed.set_footer(text=f"{BOT_NAME} Security  •  Advanced Server Protection")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @security_group.command(name="antinuke", description="Quick shortcut to check Anti-Nuke protection status")
    @app_commands.default_permissions(administrator=True)
    async def security_antinuke_shortcut(self, interaction: discord.Interaction) -> None:
        await self.antinuke_status(interaction)

    # ── Anti-Nuke Command Group ───────────────────────────────────────────────

    async def _safe_defer(self, interaction: discord.Interaction, ephemeral: bool = True) -> None:
        """Immediately acknowledge interaction to prevent Discord 3-second 10062 timeout."""
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=ephemeral)
        except Exception:
            pass

    async def _safe_respond(self, interaction: discord.Interaction, embed: discord.Embed, ephemeral: bool = True) -> None:
        """Send embed response safely via followup or send_message, catching 10062 gracefully."""
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        except (discord.NotFound, discord.HTTPException):
            try:
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            except Exception:
                pass

    antinuke_group = app_commands.Group(name="antinuke", description="🛡️ Anti-Nuke Server Protection & Raid Prevention")

    @antinuke_group.command(name="status", description="Show current Anti-Nuke defense status, thresholds, and whitelisted staff")
    @app_commands.default_permissions(administrator=True)
    async def antinuke_status(self, interaction: discord.Interaction) -> None:
        await self._safe_defer(interaction, ephemeral=True)
        cfg = self.db.get_antinuke_config(interaction.guild.id)
        wl = self.db.get_antinuke_whitelist(interaction.guild.id)

        state = "🟢 Enabled" if cfg.get("enabled") else "🔴 Disabled"
        punishment_map = {
            "strip_roles": "🛡️ Strip All Roles + 1h Timeout",
            "ban": "🔨 Permanent Ban",
            "kick": "👢 Kick Member",
        }
        punishment_str = punishment_map.get(cfg.get("action", "strip_roles"), cfg.get("action"))

        window = cfg.get("time_window_sec", 20)
        strict_mode = bool(cfg.get("strict_mode", 1))
        strict_str = "⚡ Active (Instant Quarantine on 1 Delete)" if strict_mode else "Standard"
        lines = [
            f"**System State:** `{state}`",
            f"**Strict Mode:** `{strict_str}`",
            f"**Punishment:** `{punishment_str}`",
            f"**Evaluation Window:** `{window} seconds`\n",
            "**Trigger Thresholds:**",
            f"• **Mass Ban:** `{cfg.get('ban_limit', 2)} bans` / {window}s",
            f"• **Mass Kick:** `{cfg.get('kick_limit', 2)} kicks` / {window}s",
            f"• **Channel Delete:** `{1 if strict_mode else cfg.get('channel_delete_limit', 1)} channel(s)` (Strict={strict_mode})",
            f"• **Channel Create:** `{cfg.get('channel_create_limit', 3)} channels` / {window}s",
            f"• **Role Delete:** `{1 if strict_mode else cfg.get('role_delete_limit', 1)} role(s)` (Strict={strict_mode})",
            f"• **Role Create:** `{cfg.get('role_create_limit', 3)} roles` / {window}s",
            f"• **Anti-Bot Addition:** {'`Active (Auto-Kick)`' if cfg.get('anti_bot') else '`Disabled`'}\n",
            f"**Whitelisted Entities:** `{len(wl)}` configured (Server owner immune)",
        ]

        if wl:
            wl_str = ", ".join(f"<@{r['target_id']}>" for r in wl[:10])
            if len(wl) > 10:
                wl_str += f" *(+{len(wl)-10} more)*"
            lines.append(f"• {wl_str}")

        embed = discord.Embed(
            title=f"🛡️  Anti-Nuke Protection Status — {interaction.guild.name}",
            description="\n".join(lines),
            color=C.SUCCESS if cfg.get("enabled") else C.DANGER,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"{BOT_NAME} Anti-Nuke Engine")
        await self._safe_respond(interaction, embed, ephemeral=True)

    @antinuke_group.command(name="toggle", description="Enable or disable the Anti-Nuke defense engine")
    @app_commands.describe(enabled="Turn Anti-Nuke protection ON or OFF")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable (ON)", value=1),
        app_commands.Choice(name="Disable (OFF)", value=0),
    ])
    @app_commands.default_permissions(administrator=True)
    async def antinuke_toggle(self, interaction: discord.Interaction, enabled: int) -> None:
        await self._safe_defer(interaction, ephemeral=True)
        self.db.update_antinuke_config(interaction.guild.id, enabled=enabled)
        state_str = "Enabled" if enabled else "Disabled"
        embed = embed_success("Anti-Nuke Updated", f"Anti-Nuke protection is now **{state_str}** for this server.") if enabled else embed_warning(f"Anti-Nuke protection is now **{state_str}**.")
        await self._safe_respond(interaction, embed, ephemeral=True)

    @antinuke_group.command(name="strict", description="Toggle Strict Mode (Instant Quarantine on 1 channel/role deletion)")
    @app_commands.describe(enabled="Strict Mode ON (Max security) or OFF (Standard thresholds)")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Strict (Instant Lockdown on 1 Delete)", value=1),
        app_commands.Choice(name="Standard (Use configured thresholds)", value=0),
    ])
    @app_commands.default_permissions(administrator=True)
    async def antinuke_strict(self, interaction: discord.Interaction, enabled: int) -> None:
        await self._safe_defer(interaction, ephemeral=True)
        self.db.update_antinuke_config(interaction.guild.id, strict_mode=enabled)
        mode_str = "Strict (Instant 1-delete quarantine)" if enabled else "Standard"
        embed = embed_success("Strict Mode Updated", f"Anti-Nuke strict mode is now **{mode_str}**.")
        await self._safe_respond(interaction, embed, ephemeral=True)

    @antinuke_group.command(name="action", description="Set the punishment executed against nukers")
    @app_commands.describe(action="Penalty type")
    @app_commands.choices(action=[
        app_commands.Choice(name="Strip Roles + Quarantine Timeout (Recommended)", value="strip_roles"),
        app_commands.Choice(name="Permanent Ban", value="ban"),
        app_commands.Choice(name="Kick from Server", value="kick"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def antinuke_action(self, interaction: discord.Interaction, action: str) -> None:
        await self._safe_defer(interaction, ephemeral=True)
        self.db.update_antinuke_config(interaction.guild.id, action=action)
        embed = embed_success("Punishment Updated", f"Anti-Nuke punishment action set to: **{action}**.")
        await self._safe_respond(interaction, embed, ephemeral=True)

    @antinuke_group.command(name="limits", description="Configure trigger thresholds for Anti-Nuke actions")
    @app_commands.describe(
        ban_limit="Max bans allowed in 15s (default: 3)",
        kick_limit="Max kicks allowed in 15s (default: 3)",
        channel_delete_limit="Max channel deletions in 15s (default: 3)",
        role_delete_limit="Max role deletions in 15s (default: 3)",
        time_window="Evaluation time window in seconds (default: 15)"
    )
    @app_commands.default_permissions(administrator=True)
    async def antinuke_limits(
        self,
        interaction: discord.Interaction,
        ban_limit: Optional[int] = None,
        kick_limit: Optional[int] = None,
        channel_delete_limit: Optional[int] = None,
        role_delete_limit: Optional[int] = None,
        time_window: Optional[int] = None
    ) -> None:
        await self._safe_defer(interaction, ephemeral=True)
        updates = {}
        if ban_limit is not None and ban_limit >= 1:
            updates["ban_limit"] = ban_limit
        if kick_limit is not None and kick_limit >= 1:
            updates["kick_limit"] = kick_limit
        if channel_delete_limit is not None and channel_delete_limit >= 1:
            updates["channel_delete_limit"] = channel_delete_limit
        if role_delete_limit is not None and role_delete_limit >= 1:
            updates["role_delete_limit"] = role_delete_limit
        if time_window is not None and time_window >= 5:
            updates["time_window_sec"] = min(60, time_window)

        if not updates:
            await self._safe_respond(interaction, embed_error("Please specify at least one valid threshold to update."), ephemeral=True)
            return

        self.db.update_antinuke_config(interaction.guild.id, **updates)
        summary = "\n".join(f"• **{k}:** `{v}`" for k, v in updates.items())
        await self._safe_respond(
            interaction,
            embed_success("Anti-Nuke Thresholds Updated", f"Updated settings:\n{summary}"),
            ephemeral=True
        )

    @antinuke_group.command(name="antibot", description="Toggle auto-kick for unauthorized bot additions")
    @app_commands.describe(enabled="Turn Anti-Bot defense ON or OFF")
    @app_commands.choices(enabled=[
        app_commands.Choice(name="Enable (Auto-kick unauthorized bots)", value=1),
        app_commands.Choice(name="Disable", value=0),
    ])
    @app_commands.default_permissions(administrator=True)
    async def antinuke_antibot(self, interaction: discord.Interaction, enabled: int) -> None:
        await self._safe_defer(interaction, ephemeral=True)
        self.db.update_antinuke_config(interaction.guild.id, anti_bot=enabled)
        state_str = "Enabled" if enabled else "Disabled"
        await self._safe_respond(
            interaction,
            embed_success("Anti-Bot Setting Updated", f"Anti-Bot protection is now **{state_str}**."),
            ephemeral=True
        )

    @antinuke_group.command(name="whitelist", description="Manage trusted admins/bots immune to Anti-Nuke")
    @app_commands.describe(action="Action to perform", target="Target user or bot to whitelist/unwhitelist")
    @app_commands.choices(action=[
        app_commands.Choice(name="Add to Whitelist", value="add"),
        app_commands.Choice(name="Remove from Whitelist", value="remove"),
        app_commands.Choice(name="List Whitelist", value="list"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def antinuke_whitelist_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        target: Optional[Union[discord.Member, discord.User]] = None
    ) -> None:
        await self._safe_defer(interaction, ephemeral=True)
        if action == "list":
            wl = self.db.get_antinuke_whitelist(interaction.guild.id)
            if not wl:
                await self._safe_respond(interaction, embed_info("Anti-Nuke Whitelist", "No members or bots are currently whitelisted (Server Owner is always immune)."), ephemeral=True)
                return
            lines = [f"• <@{r['target_id']}> (`{r['target_id']}`) — *Added by <@{r['added_by']}>*" for r in wl]
            embed = discord.Embed(
                title=f"🛡️  Anti-Nuke Whitelist ({len(wl)})",
                description="\n".join(lines),
                color=C.BRAND
            )
            await self._safe_respond(interaction, embed, ephemeral=True)
            return

        if not target:
            await self._safe_respond(interaction, embed_error("Please specify a member or bot to add/remove."), ephemeral=True)
            return

        if action == "add":
            added = self.db.add_antinuke_whitelist(interaction.guild.id, target.id, interaction.user.id)
            if added:
                await self._safe_respond(interaction, embed_success("Whitelist Added", f"{target.mention} is now whitelisted and immune to Anti-Nuke."), ephemeral=True)
            else:
                await self._safe_respond(interaction, embed_info("Already Whitelisted", f"{target.mention} is already on the Anti-Nuke whitelist."), ephemeral=True)
        else:
            removed = self.db.remove_antinuke_whitelist(interaction.guild.id, target.id)
            if removed:
                await self._safe_respond(interaction, embed_success("Whitelist Removed", f"{target.mention} was removed from the Anti-Nuke whitelist."), ephemeral=True)
            else:
                await self._safe_respond(interaction, embed_info("Not Found", f"{target.mention} is not in the Anti-Nuke whitelist."), ephemeral=True)

    # ── Top-Level /whitelist and /unwhitelist Commands ─────────────────────────

    @app_commands.command(name="whitelist", description="Whitelist a user or bot for Anti-Nuke immunity and assign power role")
    @app_commands.describe(target="The member, user, or bot to whitelist", role="Optional power role to grant them")
    @app_commands.default_permissions(administrator=True)
    async def whitelist(
        self,
        interaction: discord.Interaction,
        target: discord.User,
        role: Optional[discord.Role] = None
    ) -> None:
        if not interaction.guild:
            return

        await self._safe_defer(interaction, ephemeral=False)
        self.db.add_antinuke_whitelist(interaction.guild.id, target.id, interaction.user.id)
        actions = ["🛡️ Added to Anti-Nuke Whitelist (Full Immunity)"]

        # If member is in the guild, manage timeout and roles
        member = interaction.guild.get_member(target.id)
        if member:
            if member.timed_out_until and member.timed_out_until > discord.utils.utcnow():
                try:
                    await member.timeout(None, reason=f"Whitelisted & empowered by {interaction.user}")
                    actions.append("🔊 Removed quarantine timeout")
                except Exception:
                    pass

            if role:
                if role >= interaction.guild.me.top_role:
                    actions.append(f"⚠️ Cannot grant {role.mention}: Role hierarchy equal/above bot role")
                elif role.managed:
                    actions.append(f"⚠️ Cannot grant {role.mention}: Integration/managed role")
                else:
                    try:
                        await member.add_roles(role, reason=f"Whitelisted & empowered by {interaction.user}")
                        actions.append(f"⚡ Granted power role: {role.mention}")
                    except Exception as e:
                        actions.append(f"⚠️ Failed to add role: {e}")

        await self.log_security_action(
            interaction.guild,
            "✅ Member / Bot Whitelisted",
            f"**Target:** {target.mention} (`{target}`)\n**Executor:** {interaction.user.mention}\n" + "\n".join(f"• {a}" for a in actions),
            color=0x57F287,
            event="security_warn"
        )

        embed = embed_success(
            "Target Whitelisted & Empowered",
            f"**Target:** {target.mention} (`{target}`)\n" + "\n".join(f"• {a}" for a in actions)
        )
        await self._safe_respond(interaction, embed, ephemeral=False)

    @app_commands.command(name="unwhitelist", description="Remove a user or bot from whitelist and immediately strip all power roles")
    @app_commands.describe(target="The member, user, or bot to unwhitelist")
    @app_commands.default_permissions(administrator=True)
    async def unwhitelist(
        self,
        interaction: discord.Interaction,
        target: discord.User
    ) -> None:
        if not interaction.guild:
            return

        if target.id == interaction.guild.owner_id:
            await self._safe_respond(
                interaction,
                embed_error("Cannot unwhitelist the server owner."),
                ephemeral=True
            )
            return

        await self._safe_defer(interaction, ephemeral=False)
        removed = self.db.remove_antinuke_whitelist(interaction.guild.id, target.id)
        actions = ["❌ Removed from Anti-Nuke Whitelist (Vulnerable to Anti-Nuke triggers)"]

        # Strip all removable roles if present in guild
        member = interaction.guild.get_member(target.id)
        if member:
            roles_to_remove = [
                r for r in member.roles
                if not r.is_default() and not r.managed and r < interaction.guild.me.top_role
            ]
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason=f"Unwhitelisted by {interaction.user}: Stripping all power roles")
                    actions.append(f"🛡️ Stripped `{len(roles_to_remove)}` power role(s) ({', '.join(r.name for r in roles_to_remove[:5])})")
                except Exception as e:
                    actions.append(f"⚠️ Role strip error: {e}")
            else:
                actions.append("ℹ️ No removable power roles found")

        await self.log_security_action(
            interaction.guild,
            "❌ Member / Bot Unwhitelisted",
            f"**Target:** {target.mention} (`{target}`)\n**Executor:** {interaction.user.mention}\n" + "\n".join(f"• {a}" for a in actions),
            color=0xED4245,
            event="security_auto_kick"
        )

        embed = embed_warning(
            "Target Unwhitelisted & Stripped",
            f"**Target:** {target.mention} (`{target}`)\n" + "\n".join(f"• {a}" for a in actions)
        )
        await self._safe_respond(interaction, embed, ephemeral=False)



# ---------------------------------------------------------------------------
# Extension setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(SecurityCog(bot))

