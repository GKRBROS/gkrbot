"""
bot_status.py — Live Bot Status Dashboard for GKR Bot.

Features
--------
  • Posts a stylish, modern live-updating status embed to a chosen channel.
  • Auto-edits that single message every 60 seconds (heartbeat loop).
  • Marks the bot OFFLINE when it disconnects or shuts down.
  • Flips back to ONLINE when the bot reconnects.

Commands  (/botstatus)
----------
  setchannel #channel  — Set the dashboard channel and post the first embed.
  post                 — Force re-post / reset the status embed.
  clear                — Delete the pinned embed and disable the dashboard.
"""

import os
import time
import sqlite3
import datetime
import platform
import aiohttp

import discord
from discord import app_commands
from discord.ext import commands, tasks

# Optional: psutil for memory usage
try:
    import psutil as _psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_DB_PATH    = os.path.join(os.path.dirname(__file__), "font_sync.sqlite3")
_START_TIME = time.time()   # captured at module load == bot start time


# ══════════════════════════════════════════════════════════════
#  Database helpers
# ══════════════════════════════════════════════════════════════

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_status_guilds (
                guild_id    INTEGER PRIMARY KEY,
                channel_id  TEXT,
                message_id  TEXT
            )
        """)
        conn.commit()


def _load_cfg() -> dict[int, dict]:
    with _db() as conn:
        rows = conn.execute("SELECT guild_id, channel_id, message_id FROM bot_status_guilds").fetchall()
    
    configs = {}
    for row in rows:
        configs[int(row["guild_id"])] = {
            "channel_id": int(row["channel_id"]) if row["channel_id"] else None,
            "message_id": int(row["message_id"]) if row["message_id"] else None,
        }
    return configs


def _save_cfg(guild_id: int, channel_id: int | None, message_id: int | None) -> None:
    with _db() as conn:
        if channel_id is None and message_id is None:
            conn.execute("DELETE FROM bot_status_guilds WHERE guild_id = ?", (guild_id,))
        else:
            conn.execute(
                """
                INSERT INTO bot_status_guilds (guild_id, channel_id, message_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, message_id = excluded.message_id
                """,
                (
                    guild_id,
                    str(channel_id) if channel_id else None,
                    str(message_id) if message_id else None,
                ),
            )
        conn.commit()


# ══════════════════════════════════════════════════════════════
#  Stat helpers
# ══════════════════════════════════════════════════════════════

def _fmt_uptime() -> str:
    s = int(time.time() - _START_TIME)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def _fmt_memory() -> str:
    if not _PSUTIL:
        return "—"
    try:
        mb = _psutil.Process(os.getpid()).memory_info().rss / 1_048_576
        return f"{mb:.1f} MB"
    except Exception:
        return "—"


import collections
import urllib.parse
import json

# Track the last 60 minutes of stats for the graph
_HISTORY_LABELS = collections.deque(maxlen=60)
_HISTORY_MEM    = collections.deque(maxlen=60)
_HISTORY_CPU    = collections.deque(maxlen=60)

def _update_history() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    _HISTORY_LABELS.append(now.strftime("%H:%M"))
    
    if _PSUTIL:
        try:
            mem = _psutil.Process(os.getpid()).memory_info().rss / 1_048_576
            cpu = _psutil.cpu_percent(interval=None)
        except Exception:
            mem, cpu = 0, 0
    else:
        mem, cpu = 0, 0
        
    _HISTORY_MEM.append(round(mem, 1))
    _HISTORY_CPU.append(round(cpu, 1))

async def _generate_chart_url() -> str | None:
    if len(_HISTORY_LABELS) < 2:
        return None
        
    chart = {
        "type": "line",
        "data": {
            "labels": list(_HISTORY_LABELS),
            "datasets": [
                {
                    "label": "Memory (MB)",
                    "data": list(_HISTORY_MEM),
                    "borderColor": "rgb(54, 162, 235)",
                    "backgroundColor": "rgba(54, 162, 235, 0.5)",
                    "yAxisID": "y-mem",
                    "fill": False,
                    "tension": 0.3
                },
                {
                    "label": "CPU (%)",
                    "data": list(_HISTORY_CPU),
                    "borderColor": "rgb(255, 99, 132)",
                    "backgroundColor": "rgba(255, 99, 132, 0.5)",
                    "yAxisID": "y-cpu",
                    "fill": False,
                    "tension": 0.3
                }
            ]
        },
        "options": {
            "title": {"display": False},
            "legend": {"labels": {"fontColor": "#ffffff"}},
            "scales": {
                "xAxes": [{"ticks": {"fontColor": "#aaaaaa"}, "gridLines": {"color": "#333333"}}],
                "yAxes": [
                    {
                        "id": "y-mem",
                        "position": "left",
                        "ticks": {"fontColor": "rgb(54, 162, 235)", "beginAtZero": True},
                        "gridLines": {"color": "#333333"}
                    },
                    {
                        "id": "y-cpu",
                        "position": "right",
                        "ticks": {"fontColor": "rgb(255, 99, 132)", "beginAtZero": True, "max": 100},
                        "gridLines": {"drawOnChartArea": False}
                    }
                ]
            }
        }
    }
    
    # Use QuickChart's short-URL POST API to avoid Discord's 2048 char URL limit
    payload = {
        "backgroundColor": "rgb(43,45,49)",
        "width": 600,
        "height": 300,
        "format": "png",
        "chart": json.dumps(chart)
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://quickchart.io/chart/create", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        short_url = data.get("url")
                        print(f"[BotStatus] ✅ Chart short URL: {short_url}")
                        return short_url
                    else:
                        print(f"[BotStatus] ⚠️ QuickChart returned success=false: {data}")
                else:
                    body = await resp.text()
                    print(f"[BotStatus] ⚠️ QuickChart returned status {resp.status}: {body[:200]}")
    except Exception as e:
        print(f"[BotStatus] ❌ Failed to generate short chart URL: {type(e).__name__}: {e}")
        
    # If short URL failed, skip the graph entirely (long URL would exceed Discord's limit)
    print("[BotStatus] ⚠️ Skipping chart — short URL generation failed.")
    return None

# ══════════════════════════════════════════════════════════════
#  Embed builder
# ══════════════════════════════════════════════════════════════

def _stat_line(emoji: str, label: str, value: str) -> str:
    """Returns one formatted stat row."""
    return f"{emoji}  **{label}**  `{value}`\n"


async def _build_embed(bot: commands.Bot, *, online: bool = True, chart_url: str | None = None) -> discord.Embed:
    now   = datetime.datetime.now(datetime.timezone.utc)
    color = 0x00E676 if online else 0xFF3B3B   # green / red

    # ── Status indicator ─────────────────────────────────────────────────────
    if online:
        status_line = "🟢  **ONLINE** — All systems operational"
    else:
        status_line = "🔴  **OFFLINE** — Bot is shutting down / disconnected"

    # ── Raw stats ─────────────────────────────────────────────────────────────
    try:
        ping = f"{round(bot.latency * 1000)} ms"
    except Exception:
        ping = "— ms"

    uptime       = _fmt_uptime()
    memory       = _fmt_memory()
    py_ver       = platform.python_version()
    dpy_ver      = discord.__version__
    guild_count  = len(bot.guilds)
    member_count = sum(g.member_count or 0 for g in bot.guilds)
    cmd_count    = len(bot.tree.get_commands())

    # ── Field: System ─────────────────────────────────────────────────────────
    sys_val = (
        _stat_line("⏱", "Uptime",      uptime)
        + _stat_line("📶", "Ping",       ping)
        + _stat_line("💾", "Memory",     memory)
        + _stat_line("🐍", "Python",     py_ver)
        + _stat_line("📦", "discord.py", dpy_ver)
    )

    # ── Field: Community ──────────────────────────────────────────────────────
    community_val = (
        _stat_line("🏰", "Servers",  str(guild_count))
        + _stat_line("👥", "Members",  f"{member_count:,}")
        + _stat_line("⚡", "Commands", str(cmd_count))
    )

    # ── Field: Footer row ─────────────────────────────────────────────────────
    footer_row = (
        "╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌\n"
        f"🔄  Refreshes every **60 s**  ·  "
        f"Last updated <t:{int(now.timestamp())}:T>"
    )

    # ── Assemble embed ────────────────────────────────────────────────────────
    embed = discord.Embed(
        title="🤖  GKR Bot  ·  Live Dashboard",
        description=f"> {status_line}",
        color=color,
        timestamp=now,
    )
    if bot.user:
        embed.set_author(
            name="GKR Bot  ·  Status Monitor",
            icon_url=bot.user.display_avatar.url,
        )

    embed.add_field(name="🖥️  System",     value=sys_val,        inline=True)
    embed.add_field(name="🌐  Community",  value=community_val,  inline=True)
    embed.add_field(name="",               value=footer_row,      inline=False)
    
    if online and chart_url is None:
        chart_url = await _generate_chart_url()
        
    if chart_url:
        # Cache buster to force Discord to reload the image each minute
        embed.set_image(url=f"{chart_url}?_t={int(now.timestamp())}")

    embed.set_footer(text=f"GKR Bot  ·  {now.strftime('%d %b %Y')}")
    return embed


# ══════════════════════════════════════════════════════════════
#  Cog
# ══════════════════════════════════════════════════════════════

class BotStatusCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot         = bot
        self._configs: dict[int, dict] = {}

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_channel(self, guild_id: int) -> discord.TextChannel | None:
        cfg = self._configs.get(guild_id, {})
        channel_id = cfg.get("channel_id")
        if not channel_id:
            return None
        ch = self.bot.get_channel(channel_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _fetch_message(self, guild_id: int) -> discord.Message | None:
        ch = self._get_channel(guild_id)
        cfg = self._configs.get(guild_id, {})
        msg_id = cfg.get("message_id")
        if not ch or not msg_id:
            return None
        try:
            return await ch.fetch_message(msg_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    async def _post_fresh(self, guild_id: int, embed_msg: discord.Embed = None) -> discord.Message | None:
        """Post a brand-new status embed and save the message ID."""
        ch = self._get_channel(guild_id)
        if not ch:
            return None
        try:
            if not embed_msg:
                embed_msg = await _build_embed(self.bot, online=True)
            msg = await ch.send(embed=embed_msg)
            
            if guild_id not in self._configs:
                self._configs[guild_id] = {"channel_id": ch.id}
            self._configs[guild_id]["message_id"] = msg.id
            _save_cfg(guild_id, self._configs[guild_id]["channel_id"], msg.id)
            return msg
        except Exception as exc:
            print(f"[BotStatus] ❌ Failed to post status embed in {guild_id}: {exc}")
            return None

    async def _update(self, *, online: bool = True) -> None:
        """Edit the pinned status message across all configured guilds, posting a new one if missing."""
        if not self._configs:
            return
            
        chart_url = await _generate_chart_url() if online else None
        embed_msg = await _build_embed(self.bot, online=online, chart_url=chart_url)

        for guild_id in list(self._configs.keys()):
            msg = await self._fetch_message(guild_id)
            if msg is None:
                if online:
                    await self._post_fresh(guild_id, embed_msg)
                continue
            try:
                await msg.edit(embed=embed_msg)
            except Exception as exc:
                print(f"[BotStatus] ❌ Failed to edit status embed in {guild_id}: {exc}")

    # ── Task loop — heartbeat every 60 seconds ────────────────────────────────

    @tasks.loop(minutes=3)
    async def _heartbeat(self) -> None:
        _update_history()
        await self._update(online=True)

    @_heartbeat.before_loop
    async def _before_heartbeat(self) -> None:
        await self.bot.wait_until_ready()

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self._configs = _load_cfg()
        if not self._heartbeat.is_running():
            self._heartbeat.start()
        await self._update(online=True)
        print("[BotStatus] ✅ Live status dashboard active.")

    @commands.Cog.listener()
    async def on_disconnect(self) -> None:
        """Flip the embed to Offline when the bot loses its connection."""
        await self._update(online=False)

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        """Flip back to Online when the connection is restored."""
        await self._update(online=True)

    # ── Slash-command group ───────────────────────────────────────────────────

    status_group = app_commands.Group(
        name="botstatus",
        description="Manage the live bot status dashboard",
    )

    @status_group.command(
        name="setchannel",
        description="Set the channel where the live bot status dashboard is posted",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(channel="The text channel to post the live dashboard in")
    async def set_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guild_id = interaction.guild_id
        self._configs[guild_id] = {"channel_id": channel.id, "message_id": None}
        _save_cfg(guild_id, channel.id, None)

        msg = await self._post_fresh(guild_id)
        if msg:
            await interaction.response.send_message(
                f"✅ Live bot status dashboard set to {channel.mention}. "
                f"The embed has been posted and will auto-update every minute.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⚠️ Channel saved as {channel.mention} but the bot couldn't post the embed. "
                f"Check that the bot has **Send Messages** and **Embed Links** permissions there, "
                f"then try `/botstatus post`.",
                ephemeral=True,
            )

    @status_group.command(
        name="post",
        description="Force re-post / reset the live bot status embed in the configured channel",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def post(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        if guild_id not in self._configs or not self._configs[guild_id].get("channel_id"):
            await interaction.response.send_message(
                "❌ No status channel configured yet. Use `/botstatus setchannel` first.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        # Remove old message
        old = await self._fetch_message(guild_id)
        if old:
            try:
                await old.delete()
            except Exception:
                pass
        self._configs[guild_id]["message_id"] = None
        msg = await self._post_fresh(guild_id)
        if msg:
            await interaction.followup.send(
                "✅ Status dashboard re-posted successfully!", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ Failed to post status message — check channel permissions.", ephemeral=True
            )

    @status_group.command(
        name="clear",
        description="Delete the live status embed and disable the auto-update dashboard",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def clear(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id
        old = await self._fetch_message(guild_id)
        if old:
            try:
                await old.delete()
            except Exception:
                pass
        if guild_id in self._configs:
            del self._configs[guild_id]
        _save_cfg(guild_id, None, None)
        await interaction.response.send_message(
            "✅ Status dashboard cleared and disabled.", ephemeral=True
        )


# ══════════════════════════════════════════════════════════════
#  Setup entry point
# ══════════════════════════════════════════════════════════════

async def setup(bot: commands.Bot) -> None:
    """Register the BotStatusCog with the bot."""
    _init_db()
    await bot.add_cog(BotStatusCog(bot))
    print("[BotStatus] Cog loaded — dashboard will activate on_ready.")

