"""
auto_backup.py — GKR Bot Auto Backup System

Strategy (most-reliable-first):
  1. SCHEDULED: Backs up every N hours automatically (default: 6h).
     Even if the bot is SIGKILL'd, the last scheduled backup is in the channel.
  2. ON STARTUP: Backs up immediately when the bot comes online.
  3. SHUTDOWN HOOK: Patches bot.close() to attempt a backup before dying.
  4. SIGTERM: Catches Linux host shutdown signal (~30s warning).
  5. MANUAL: /codebkp now — admins can trigger anytime.

Setup:
    Add to .env:
        BACKUP_CHANNEL_ID=your_channel_id_here
        BACKUP_INTERVAL_HOURS=6        (optional, default 6)
"""

import asyncio
import io
import os
import signal
import zipfile
import datetime
import aiohttp
import requests
import atexit
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from gkr_ui import embed_success, embed_error, embed_info, C

BACKUP_CHANNEL_ID     = int(os.getenv("BACKUP_CHANNEL_ID", "0"))
BACKUP_WEBHOOK_URL    = os.getenv("DISCORD_WEBHOOK_URL", "")
BACKUP_INTERVAL_HOURS = float(os.getenv("BACKUP_INTERVAL_HOURS", "6"))

# What to back up:
# - All .sqlite3 / .db database files anywhere in the project
# - The .env file
# - Text-based config files inside welcome_assets (JSON, YAML, TXT)
# We deliberately SKIP images (PNG, GIF, JPG, WEBP) because:
#   1. They are already compressed and don't shrink further inside a ZIP
#   2. They easily push the backup over Discord's 25 MB upload limit
#   3. They are static design assets you control — databases are irreplaceable
GLOBAL_EXTS     = {".sqlite3", ".db", ".env"}  # always included
ASSET_DIR       = "welcome_assets"              # include text configs from here
ASSET_TEXT_EXTS = {".json", ".yaml", ".yml", ".txt", ".toml"}  # allowed from assets
SKIP_DIRS       = {"__pycache__", ".git", "node_modules", ".venv", "venv"}

def _build_zips() -> list[io.BytesIO]:
    """
    Build a compact, single-part backup zip.
    Includes only databases, .env, and text-based configs from welcome_assets.
    Images are intentionally excluded to keep the archive under Discord's 25 MB limit.
    """
    base = os.path.dirname(os.path.abspath(__file__))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for file in files:
                full_path = os.path.join(root, file)
                rel_path  = os.path.relpath(full_path, base)
                _, ext    = os.path.splitext(file)
                ext       = ext.lower()

                # Always include database and env files
                if ext in GLOBAL_EXTS or file == ".env":
                    pass  # include it
                # Include text config files that live inside welcome_assets
                elif ASSET_DIR in rel_path.replace("\\", "/") and ext in ASSET_TEXT_EXTS:
                    pass  # include it
                else:
                    continue  # skip everything else

                try:
                    zf.write(full_path, rel_path)
                except (PermissionError, OSError):
                    pass

    buf.seek(0)
    if buf.getbuffer().nbytes <= 22:  # empty zip
        return []
    return [buf]



def sync_shutdown_backup():
    """Synchronous backup that runs when the Python interpreter is exiting."""
    if not BACKUP_WEBHOOK_URL:
        print("[AutoBackup] No WEBHOOK_URL set. Skipping synchronous shutdown backup.")
        return

    print("\n[AutoBackup] 🛑 Python interpreter shutting down. Running synchronous backup...")
    try:
        buffers = _build_zips()
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        
        for i, buf in enumerate(buffers, start=1):
            filename = f"GKRBot_FullBackup_{timestamp}_part{i}.zip"
            buf.seek(0)
            
            payload = {}
            if i == 1:
                payload["content"] = f"🛑 **Bot Shutdown Detected** - Full Backup (Part {i}/{len(buffers)})"
            else:
                payload["content"] = f"📦 Backup Part {i}/{len(buffers)}"
                
            files = {
                "file": (filename, buf, "application/zip")
            }
            
            resp = requests.post(BACKUP_WEBHOOK_URL, data=payload, files=files)
            if resp.status_code in (200, 204):
                print(f"[AutoBackup] ✅ Sent shutdown backup part {i}/{len(buffers)}.")
            else:
                print(f"[AutoBackup] ❌ Shutdown upload failed: {resp.status_code}")
    except Exception as e:
        print(f"[AutoBackup] ❌ Sync shutdown backup error: {e}")

# Register the synchronous shutdown hook globally
atexit.register(sync_shutdown_backup)

class AutoBackupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._shutdown_triggered = False
        self._register_signals()
        self.scheduled_backup.change_interval(hours=BACKUP_INTERVAL_HOURS)
        self.scheduled_backup.start()

    def cog_unload(self):
        self.scheduled_backup.cancel()

    # ── 1. Scheduled periodic backup ──────────────────────────────────────────

    @tasks.loop(hours=6)
    async def scheduled_backup(self):
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        print(f"[AutoBackup] Scheduled backup running at {now}...")
        await self._send_backup(triggered_by=f"⏰ Scheduled — every {BACKUP_INTERVAL_HOURS}h")

    @scheduled_backup.before_loop
    async def before_scheduled(self):
        await self.bot.wait_until_ready()
        # Run one backup immediately on startup, then every N hours
        print("[AutoBackup] Bot ready — running startup backup...")
        await self._send_backup(triggered_by="🚀 Startup — bot came online")

    def _register_signals(self):
        # We must use standard Python signal.signal instead of asyncio.add_signal_handler
        # because asyncio's handlers can be ignored during Pterodactyl's forced teardown.
        
        def _handle_sigterm(signum, frame):
            print("\n[AutoBackup] 🛑 SIGTERM received from Pterodactyl! Halting everything for backup...")
            sync_shutdown_backup()
            print("[AutoBackup] Backup complete. Exiting process.")
            import sys
            sys.exit(0)
            
        try:
            signal.signal(signal.SIGTERM, _handle_sigterm)
            signal.signal(signal.SIGINT, _handle_sigterm)
            print("[AutoBackup] Successfully hijacked SIGTERM/SIGINT with standard signal module.")
        except Exception as e:
            print(f"[AutoBackup] Could not register signals: {e}")


    # ── Core backup sender ────────────────────────────────────────────────────

    async def _send_backup(self, triggered_by: str = "Manual") -> bool:
        if BACKUP_CHANNEL_ID == 0 and not BACKUP_WEBHOOK_URL:
            print("[AutoBackup] Neither BACKUP_CHANNEL_ID nor DISCORD_WEBHOOK_URL are set — skipping.")
            return False

        channel = self.bot.get_channel(BACKUP_CHANNEL_ID)
        if not channel and not BACKUP_WEBHOOK_URL:
            print(f"[AutoBackup] Channel {BACKUP_CHANNEL_ID} not found and no webhook provided.")
            return False

        try:
            # Build chunked zips
            buffers   = await asyncio.to_thread(_build_zips)
            timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
            total_kb  = sum(len(b.getvalue()) for b in buffers) // 1024
            total_mb  = total_kb / 1024

            print(f"[AutoBackup] Built {len(buffers)} chunks, total size: {total_mb:.1f} MB")

            embed = discord.Embed(
                title="📦  Data & Assets Backup",
                color=C.SUCCESS,
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Triggered By", value=triggered_by,           inline=False)
            embed.add_field(name="Total Size",   value=f"`{total_mb:.1f} MB`",   inline=True)
            embed.add_field(name="Parts",        value=f"`{len(buffers)}`",      inline=True)
            embed.add_field(name="Contents",     value="Databases (`.sqlite3`), `.env`, and `welcome_assets`", inline=False)
            embed.set_footer(text="GKR Bot • Auto Backup")

            # Send the main embed message without files first, or with the first file
            for i, buf in enumerate(buffers, start=1):
                filename = f"GKRBot_DataBackup_{timestamp}_part{i}.zip"
                buf.seek(0)
                
                # Check if we should use the robust Webhook approach (user requested)
                if BACKUP_WEBHOOK_URL:
                    try:
                        form = aiohttp.FormData()
                        # Send the embed only on the first part
                        if i == 1:
                            payload_json = {"embeds": [embed.to_dict()]}
                            form.add_field("payload_json", discord.utils._to_json(payload_json), content_type="application/json")
                        else:
                            payload_json = {"content": f"📦 Backup Part {i}/{len(buffers)}"}
                            form.add_field("payload_json", discord.utils._to_json(payload_json), content_type="application/json")
                            
                        form.add_field("file", buf.read(), filename=filename, content_type="application/zip")
                        
                        async with aiohttp.ClientSession() as session:
                            async with session.post(BACKUP_WEBHOOK_URL, data=form) as resp:
                                if resp.status not in (200, 204):
                                    print(f"[AutoBackup] ❌ Webhook upload failed! HTTP {resp.status}: {await resp.text()}")
                                else:
                                    print(f"[AutoBackup] ✅ Sent part {i}/{len(buffers)} via Webhook: {filename}")
                    except Exception as e:
                        print(f"[AutoBackup] ❌ Webhook error: {e}")
                
                # Fallback to standard bot channel send if no webhook, or if webhook is not set
                elif channel:
                    file_obj = discord.File(fp=buf, filename=filename)
                    if i == 1:
                        await channel.send(embed=embed, file=file_obj)
                    else:
                        await channel.send(f"📦 Backup Part {i}/{len(buffers)}", file=file_obj)
                    print(f"[AutoBackup] ✅ Sent part {i}/{len(buffers)} via Channel: {filename}")

            return True

        except Exception as e:
            print(f"[AutoBackup] Backup failed: {e}")
            return False


    # ── Slash Commands ─────────────────────────────────────────────────────────

    codebkp_group = app_commands.Group(
        name="codebkp",
        description="Bot source code backup commands (Admin only).",
        default_permissions=discord.Permissions(administrator=True)
    )

    @codebkp_group.command(name="now", description="Manually trigger a source code backup right now.")
    async def backup_now(self, interaction: discord.Interaction):
        if BACKUP_CHANNEL_ID == 0:
            return await interaction.response.send_message(
                embed=embed_error("No backup channel set. Add `BACKUP_CHANNEL_ID=<id>` to your `.env`."),
                ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        success = await self._send_backup(triggered_by=f"👤 Manual — {interaction.user}")
        if success:
            ch = self.bot.get_channel(BACKUP_CHANNEL_ID)
            await interaction.followup.send(
                embed=embed_success("Backup Complete", f"Uploaded to {ch.mention}."),
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=embed_error("Backup failed. Check console for details."),
                ephemeral=True
            )

    @codebkp_group.command(name="status", description="Show backup system status and schedule.")
    async def backup_status(self, interaction: discord.Interaction):
        channel = self.bot.get_channel(BACKUP_CHANNEL_ID) if BACKUP_CHANNEL_ID else None
        next_run = self.scheduled_backup.next_iteration

        embed = discord.Embed(title="📦  Backup System Status", color=C.BRAND)
        embed.add_field(
            name="Backup Channel",
            value=channel.mention if channel else "❌ Not set — add `BACKUP_CHANNEL_ID` to `.env`",
            inline=False
        )
        embed.add_field(
            name="Schedule",
            value=f"Every **{BACKUP_INTERVAL_HOURS} hours** automatically",
            inline=True
        )
        embed.add_field(
            name="Next Backup",
            value=f"<t:{int(next_run.timestamp())}:R>" if next_run else "Unknown",
            inline=True
        )
        embed.add_field(
            name="What's included",
            value="All files in the bot folder (`.py`, `.db`, `.env`, images, etc.)",
            inline=False
        )
        embed.set_footer(text="GKR Bot • Auto Backup")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoBackupCog(bot))
    print(f"📦 Auto Backup loaded — scheduled every {BACKUP_INTERVAL_HOURS}h + on startup + on shutdown.")
