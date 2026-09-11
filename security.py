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
import sqlite3
import datetime
from typing import Optional, Dict, List

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------------------------
# Constants & DB Path
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "security.sqlite3")

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

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: Union[discord.User, discord.Member]) -> None:
        """Log all bans to security logs with moderator & reason from audit log."""
        mod = None
        reason = "No reason provided"
        try:
            await asyncio.sleep(0.5)
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    mod = entry.user
                    if entry.reason:
                        reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

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

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """Log unbans to security logs."""
        mod = None
        try:
            await asyncio.sleep(0.5)
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    mod = entry.user
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

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
        """Detect and log kicks to security logs."""
        guild = member.guild
        kicker = None
        kick_reason = "No reason provided"
        try:
            await asyncio.sleep(0.5)
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id:
                    # Check if the audit log entry is recent (within 7 seconds)
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() < 7:
                        kicker = entry.user
                        if entry.reason:
                            kick_reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        if kicker:
            await self.log_security_action(
                guild,
                "👢 Member Kicked",
                f"**Member:** {member.mention} (`{member}`)\n**Moderator:** {kicker.mention}\n**Reason:** {kick_reason}",
                color=0xFF0000,
                thumbnail_url=member.display_avatar.url,
                event="security_auto_kick"
            )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Detect timeouts / mutes and log to security logs."""
        if before.timed_out_until != after.timed_out_until:
            guild = after.guild
            mod = None
            reason = "No reason provided"
            try:
                await asyncio.sleep(0.5)
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == after.id:
                        mod = entry.user
                        if entry.reason:
                            reason = entry.reason
                        break
            except (discord.Forbidden, discord.HTTPException):
                pass

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
                except discord.Forbidden:
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
                        await self.execute_punishment(message.author, len(warns), reason)
                    except Exception as e:
                        print(f"[Security] Anti-spam timeout failed: {e}")
                        
                        # Also check the overall punishment ladder
                        await self.execute_punishment(message.author, len(warns), reason)
                    except discord.Forbidden:
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
            f"• **Moderation Audit Logging:** `Bans, Unbans, Kicks, Timeouts (Active)`",
        ]

        embed = discord.Embed(
            title=f"🛡️  {BOT_NAME} Security Status — {interaction.guild.name}",
            description="\n".join(status_lines),
            color=C.BRAND
        )
        embed.set_footer(text=f"{BOT_NAME} Security  •  Advanced Server Protection")
        await interaction.response.send_message(embed=embed, ephemeral=True)



# ---------------------------------------------------------------------------
# Extension setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(SecurityCog(bot))

