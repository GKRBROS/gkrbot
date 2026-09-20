"""
cache_cleaner.py — owner-only cache / temp cleanup for a bot hosted on Pterodactyl.

Pterodactyl keeps the container disk between restarts, so caches (__pycache__,
.cache, /tmp files, half-finished card renders ...) pile up until someone clears
them. This cog does that from Discord.

Commands
    /clearcache                 -> removes __pycache__ and leftover welcome-card temp folders
    /clearcache deep:True       -> also clears .cache folders and temp files older than 1 hour
    /clearcache dry_run:True    -> only shows what WOULD be removed (nothing is deleted)

Optional automatic cleanup:
    set the env var  AUTO_CLEAR_CACHE_HOURS=24  (any number of hours) in the Startup tab.

SAFETY — this cog NEVER touches:
    * databases (*.sqlite3, *.db), .env, *.json, welcome_assets/, backups, or any other data
    * .git, venv / .venv / node_modules / site-packages
    * AI / model caches (huggingface, torch, transformers, whisper, models) — deleting
      those would force a huge re-download
    * symlinks

Install:  put this file next to main.py and add  "cache_cleaner"  to the
`extensions` list in main.py.
"""
import asyncio
import gc
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import List, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

ROOT = Path(__file__).resolve().parent

# Cache folder names that are always safe to delete (they are rebuilt automatically)
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

# Folders we never walk into
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "env", "site-packages", "welcome_assets"}

# Entries inside a .cache folder we never delete (big, slow to re-download)
PROTECTED_CACHE_ENTRIES = {"huggingface", "torch", "transformers", "whisper", "models", "pypoetry"}

# Temp folders created by this bot's own code
OWN_TEMP_PREFIXES = ("welcome_gif_",)

TEMP_MAX_AGE_SECONDS = 3600  # deep mode only removes temp files older than this


def _size(path: Path) -> int:
    """Total size in bytes of a file or directory (symlinks are not followed)."""
    try:
        if path.is_symlink():
            return 0
        if path.is_file():
            return path.stat().st_size
        total = 0
        for dirpath, _dirs, files in os.walk(path):
            for name in files:
                fp = os.path.join(dirpath, name)
                try:
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
                except OSError:
                    pass
        return total
    except OSError:
        return 0


def _fmt(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def collect_targets(root: Path, deep: bool, temp_dir: Path, home: Path) -> List[Tuple[str, Path]]:
    """Return [(category, path), ...] of everything that would be cleaned."""
    targets: List[Tuple[str, Path]] = []

    # 1) __pycache__ & friends inside the bot folder
    for dirpath, dirnames, _files in os.walk(root, topdown=True):
        keep = []
        for d in dirnames:
            full = Path(dirpath) / d
            if full.is_symlink():
                continue
            if d in CACHE_DIR_NAMES:
                targets.append(("Python cache", full))
            elif d in SKIP_DIRS:
                continue
            elif d == ".cache" and not deep:
                continue  # only touched in deep mode (handled below)
            else:
                keep.append(d)
        dirnames[:] = keep

    # 2) temp files
    now = time.time()
    if temp_dir.exists():
        for entry in temp_dir.iterdir():
            try:
                if entry.is_symlink():
                    continue
                own = entry.name.startswith(OWN_TEMP_PREFIXES)
                old = (now - entry.stat().st_mtime) > TEMP_MAX_AGE_SECONDS
                if own and old:
                    targets.append(("Temp files", entry))
                elif deep and old:
                    targets.append(("Temp files", entry))
            except OSError:
                continue

    # 3) .cache folders (deep only) — skipping big model caches
    if deep:
        for cache_root in {root / ".cache", home / ".cache"}:
            if not cache_root.is_dir() or cache_root.is_symlink():
                continue
            for child in cache_root.iterdir():
                if child.is_symlink() or child.name.lower() in PROTECTED_CACHE_ENTRIES:
                    continue
                targets.append((".cache", child))

    return targets


def run_cleanup(deep: bool = False, dry_run: bool = False,
                root: Path = ROOT, temp_dir: Path = None, home: Path = None) -> dict:
    """Blocking cleanup. Returns {category: [count, bytes]} plus 'errors'."""
    temp_dir = temp_dir or Path(tempfile.gettempdir())
    home = home or Path.home()
    summary: dict = {}
    errors = 0

    for category, path in collect_targets(root, deep, temp_dir, home):
        size = _size(path)
        if not dry_run:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except OSError:
                errors += 1
                continue
        entry = summary.setdefault(category, [0, 0])
        entry[0] += 1
        entry[1] += size

    summary["errors"] = errors
    return summary


class CacheCleaner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        hours = 0.0
        try:
            hours = float(os.getenv("AUTO_CLEAR_CACHE_HOURS", "0") or 0)
        except ValueError:
            pass
        self._auto_hours = hours

    async def cog_load(self):
        if self._auto_hours > 0:
            self.auto_clean.change_interval(hours=self._auto_hours)
            self.auto_clean.start()

    async def cog_unload(self):
        if self.auto_clean.is_running():
            self.auto_clean.cancel()

    @tasks.loop(hours=24)
    async def auto_clean(self):
        summary = await asyncio.to_thread(run_cleanup, False, False)
        freed = sum(v[1] for k, v in summary.items() if k != "errors")
        gc.collect()
        print(f"[CacheCleaner] Auto clean freed {_fmt(freed)}")

    @auto_clean.before_loop
    async def _before_auto(self):
        await self.bot.wait_until_ready()
        # skip the immediate first run; wait one full interval
        await asyncio.sleep(self._auto_hours * 3600)

    @app_commands.command(name="clearcache", description="Owner only: clear bot cache and temp files")
    @app_commands.describe(
        deep="Also clear .cache folders and temp files older than 1 hour",
        dry_run="Only show what would be removed, delete nothing",
    )
    async def clearcache(self, interaction: discord.Interaction, deep: bool = False, dry_run: bool = False):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        summary = await asyncio.to_thread(run_cleanup, deep, dry_run)
        errors = summary.pop("errors", 0)
        collected = 0 if dry_run else gc.collect()

        total_bytes = sum(v[1] for v in summary.values())
        total_items = sum(v[0] for v in summary.values())

        title = "🔍 Cache preview (nothing deleted)" if dry_run else "🧹 Cache cleared"
        embed = discord.Embed(title=title, color=0x5865F2 if dry_run else 0x57F287)

        if summary:
            for category, (count, size) in summary.items():
                embed.add_field(name=category, value=f"{count} item(s) • {_fmt(size)}", inline=True)
        else:
            embed.description = "Nothing to clean — already tidy ✨"

        verb = "Would free" if dry_run else "Freed"
        embed.add_field(name=verb, value=f"**{_fmt(total_bytes)}** across {total_items} item(s)", inline=False)
        if not dry_run:
            embed.add_field(name="Memory", value=f"Garbage-collected {collected} object(s)", inline=False)
        if errors:
            embed.set_footer(text=f"{errors} item(s) could not be removed (in use or permission denied)")
        else:
            embed.set_footer(text="Databases, backups and saved backgrounds are never touched")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CacheCleaner(bot))