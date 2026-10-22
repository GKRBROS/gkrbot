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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS owner_status_embed (
                channel_id  TEXT PRIMARY KEY,
                message_id  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS owner_status_config (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()


GIF_ONLINE = "https://cdn.discordapp.com/attachments/1247646566794133585/1559078469021990933/standard_5.gif?ex=6acdc479&is=6acc72f9&hm=1c2bbf588502fc484a624c50116481ad688ebdc1923733341d4d0dc111a0025a&"
GIF_OFFLINE = "https://media.discordapp.net/attachments/1247646566794133585/1559078524973744308/standard_6.gif?ex=6acdc486&is=6acc7306&hm=ceb8471d616e252e28ecaf399bc877d648a551453f6427107dc910c38f8324e6&=&width=640&height=360"
GIF_RESTARTING = "https://media.discordapp.net/attachments/1247646566794133585/1559078613511311450/standard_7.gif?ex=6acdc49b&is=6acc731b&hm=c5c1915b7b9949ef24dc32458d8ca3c9f879e24bcff5268b6413ec01acb7e527&=&width=640&height=360"

TOPGG_VOTE_URL = "https://top.gg/bot/1397848684061790301/vote"


class BotStatusView(discord.ui.View):
    """Persistent view attached to the bot status embed."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Vote on Top.gg",
            emoji="❤️",
            style=discord.ButtonStyle.link,
            url=TOPGG_VOTE_URL,
        ))


def _clean_channel_id(val) -> int | None:
    if not val:
        return None
    cleaned = str(val).strip().strip('"').strip("'").replace("<#", "").replace(">", "").strip()
    return int(cleaned) if cleaned.isdigit() else None


def _get_owner_channel_id() -> int | None:
    cid = _clean_channel_id(os.getenv("STATUS_CHANNEL"))
    if cid:
        return cid
    try:
        with _db() as conn:
            row = conn.execute("SELECT value FROM owner_status_config WHERE key = 'channel_id'").fetchone()
            if row and row["value"]:
                return _clean_channel_id(row["value"])
    except Exception:
        pass
    return None


def _set_owner_channel_id(channel_id: int) -> None:
    with _db() as conn:
        conn.execute("""
            INSERT INTO owner_status_config (key, value)
            VALUES ('channel_id', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (str(channel_id),))
        conn.commit()


def _load_owner_msg_id(channel_id: int) -> int | None:
    with _db() as conn:
        row = conn.execute("SELECT message_id FROM owner_status_embed WHERE channel_id = ?", (str(channel_id),)).fetchone()
        if row and row["message_id"]:
            try:
                return int(row["message_id"])
            except Exception:
                pass
    return None


def _save_owner_msg_id(channel_id: int, message_id: int) -> None:
    with _db() as conn:
        conn.execute("""
            INSERT INTO owner_status_embed (channel_id, message_id)
            VALUES (?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET message_id = excluded.message_id
        """, (str(channel_id), str(message_id)))
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
#  Stat helpers & Metric Tracking
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


def _bar(percent: float, length: int = 8) -> str:
    """Compact graphical unicode progress bar."""
    pct = max(0.0, min(100.0, float(percent)))
    filled = int(round((pct / 100.0) * length))
    filled = min(length, max(0, filled))
    return "▰" * filled + "▱" * (length - filled)


def _get_metrics() -> tuple[float, float]:
    """Return current (memory_mb, cpu_percent)."""
    if not _PSUTIL:
        return 0.0, 0.0
    try:
        proc = _psutil.Process(os.getpid())
        mem = proc.memory_info().rss / 1_048_576
        cpu = _psutil.cpu_percent(interval=None)
        return round(mem, 1), round(cpu, 1)
    except Exception:
        return 0.0, 0.0


import collections
import json

# Track the last 60 minutes of stats for the graph
_HISTORY_LABELS = collections.deque(maxlen=60)
_HISTORY_MEM    = collections.deque(maxlen=60)
_HISTORY_CPU    = collections.deque(maxlen=60)


def _seed_history() -> None:
    """Pre-seed telemetry buffer on cold start so the graph renders immediately."""
    if len(_HISTORY_LABELS) >= 2:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    mem, cpu = _get_metrics()
    if mem == 0.0:
        mem = 40.0
    for i in range(5, -1, -1):
        t = now - datetime.timedelta(minutes=i)
        _HISTORY_LABELS.append(t.strftime("%H:%M"))
        _HISTORY_MEM.append(mem)
        _HISTORY_CPU.append(cpu)


def _update_history() -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    _HISTORY_LABELS.append(now.strftime("%H:%M"))
    mem, cpu = _get_metrics()
    _HISTORY_MEM.append(mem)
    _HISTORY_CPU.append(cpu)


async def _generate_chart_url() -> str | None:
    """Generate high-density futuristic dark telemetry chart via QuickChart."""
    if len(_HISTORY_LABELS) < 2:
        _seed_history()

    chart = {
        "type": "line",
        "data": {
            "labels": list(_HISTORY_LABELS),
            "datasets": [
                {
                    "label": "RAM (MB)",
                    "data": list(_HISTORY_MEM),
                    "borderColor": "#00f2fe",
                    "backgroundColor": "rgba(0, 242, 254, 0.12)",
                    "yAxisID": "y-mem",
                    "fill": True,
                    "tension": 0.35,
                    "borderWidth": 2,
                    "pointRadius": 2,
                    "pointBackgroundColor": "#00f2fe"
                },
                {
                    "label": "CPU (%)",
                    "data": list(_HISTORY_CPU),
                    "borderColor": "#f43f5e",
                    "backgroundColor": "rgba(244, 63, 94, 0.12)",
                    "yAxisID": "y-cpu",
                    "fill": True,
                    "tension": 0.35,
                    "borderWidth": 2,
                    "pointRadius": 2,
                    "pointBackgroundColor": "#f43f5e"
                }
            ]
        },
        "options": {
            "title": {"display": False},
            "legend": {
                "display": True,
                "labels": {
                    "fontColor": "#f1f5f9",
                    "fontSize": 11,
                    "boxWidth": 12,
                    "padding": 12
                }
            },
            "scales": {
                "xAxes": [{
                    "ticks": {"fontColor": "#94a3b8", "fontSize": 10, "maxTicksLimit": 10},
                    "gridLines": {"color": "#1e293b", "zeroLineColor": "#334155"}
                }],
                "yAxes": [
                    {
                        "id": "y-mem",
                        "position": "left",
                        "ticks": {"fontColor": "#00f2fe", "fontSize": 10, "beginAtZero": False},
                        "gridLines": {"color": "#1e293b", "zeroLineColor": "#334155"}
                    },
                    {
                        "id": "y-cpu",
                        "position": "right",
                        "ticks": {"fontColor": "#f43f5e", "fontSize": 10, "beginAtZero": True, "max": 100},
                        "gridLines": {"drawOnChartArea": False}
                    }
                ]
            }
        }
    }

    payload = {
        "backgroundColor": "#0b0e14",
        "width": 680,
        "height": 280,
        "format": "png",
        "chart": json.dumps(chart)
    }

    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://quickchart.io/chart/create", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        return data.get("url")
    except Exception as e:
        print(f"[BotStatus] Telemetry chart request notice: {e}")

    return None


# ══════════════════════════════════════════════════════════════
#  Futuristic Embed Builder
# ══════════════════════════════════════════════════════════════

async def _build_embed(bot: commands.Bot, *, online: bool = True, chart_url: str | None = None) -> discord.Embed:
    now = datetime.datetime.now(datetime.timezone.utc)

    # ── Latency & Status Assessment ───────────────────────────
    try:
        raw_ping = bot.latency * 1000
        ping_val = round(raw_ping)
        ping_str = f"{ping_val} ms"
    except Exception:
        ping_val = 0
        ping_str = "Unavailable"

    if not online:
        color = 0xEF4444  # Crimson Red
        status_line = "🔴 **OFFLINE** — Bot disconnected / shutting down"
        ping_badge = "Offline"
    elif ping_val < 100:
        color = 0x00D2FF  # Cyber Electric Cyan
        status_line = "🟢 **ONLINE** — All systems operational"
        ping_badge = "Excellent"
    elif ping_val < 250:
        color = 0x38BDF8  # Deep Sky Blue
        status_line = "🟢 **ONLINE** — All systems operational"
        ping_badge = "Normal"
    else:
        color = 0xFBBF24  # Amber Warning
        status_line = "🟡 **ONLINE** — High gateway latency detected"
        ping_badge = "Elevated"

    uptime_str = _fmt_uptime()
    mem_mb, cpu_pct = _get_metrics()
    py_ver = platform.python_version()
    dpy_ver = discord.__version__

    guild_count = len(bot.guilds)
    member_count = sum(g.member_count or 0 for g in bot.guilds)
    cmd_count = len(bot.tree.get_commands())
    voice_count = len(bot.voice_clients)

    # Lavalink connectivity status
    lavalink_str = "Standby"
    try:
        import wavelink
        if hasattr(wavelink, "Pool") and wavelink.Pool.nodes:
            connected = [n for n in wavelink.Pool.nodes.values() if getattr(n, "status", None) == wavelink.NodeStatus.CONNECTED]
            lavalink_str = f"Online ({len(connected)} node)" if connected else "Connecting"
    except Exception:
        pass

    # Visual gauge bars
    cpu_bar_str = _bar(cpu_pct, 6)
    mem_percent = min(100.0, (mem_mb / 512.0) * 100.0) if mem_mb > 0 else 0.0
    mem_bar_str = _bar(mem_percent, 6)

    # ── Description Block ─────────────────────────────────────
    desc_lines = [
        f"> {status_line}",
        f"> ⚡ **Gateway RTT:** `{ping_str}` (`{ping_badge}`)  ·  ⏱️ **Uptime:** `{uptime_str}`",
    ]

    # Active Developer Directive / Notice
    try:
        from bot_status_msg import get_status_message
        notice = get_status_message()
        if notice and notice.get("active") and notice.get("message"):
            desc_lines.append(f"\n📢 **BROADCAST DIRECTIVE**\n> {notice['message']}\n*Issued by {notice.get('author', 'Dev')} · {notice.get('updated_at', 'recently')}*")
    except Exception:
        pass

    # ── Field 1: System Telemetry ─────────────────────────────
    sys_val = (
        f"⏱️ **Uptime:** `{uptime_str}`\n"
        f"📶 **Ping:** `{ping_str}` ({ping_badge})\n"
        f"💾 **Memory:** `{mem_mb:.1f} MB` `[{mem_bar_str}]`\n"
        f"⚡ **CPU Load:** `{cpu_pct:.1f}%` `[{cpu_bar_str}]`\n"
        f"🐍 **Python:** `v{py_ver}`\n"
        f"📦 **discord.py:** `v{dpy_ver}`"
    )

    # ── Field 2: Community & Topology ─────────────────────────
    community_val = (
        f"🏰 **Servers:** `{guild_count:,}`\n"
        f"👥 **Members:** `{member_count:,}`\n"
        f"⚡ **Commands:** `{cmd_count}` registered\n"
        f"🔊 **Voice Streams:** `{voice_count}` active\n"
        f"🎵 **Audio Core:** `{lavalink_str}`\n"
        f"📻 **24/7 Radio:** `Operational`"
    )

    # ── Assemble Modern Embed ─────────────────────────────────
    embed = discord.Embed(
        title="GKR Bot • Live Dashboard",
        description="\n".join(desc_lines),
        color=color,
        timestamp=now,
    )

    if bot.user:
        embed.set_author(
            name="GKR Bot • Status Monitor",
            icon_url=bot.user.display_avatar.url,
        )

    embed.add_field(name="🖥️  System Telemetry", value=sys_val, inline=True)
    embed.add_field(name="🌐  Community & Network", value=community_val, inline=True)

    if online and chart_url is None:
        chart_url = await _generate_chart_url()

    if chart_url:
        embed.set_image(url=f"{chart_url}?_t={int(now.timestamp())}")

    embed.set_footer(
        text="GKR Bot • Live Monitoring • Refreshes every 60 seconds",
        icon_url=bot.user.display_avatar.url if bot.user else None
    )
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
            msg = await ch.send(embed=embed_msg, view=BotStatusView())
            
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
                await msg.edit(embed=embed_msg, view=BotStatusView())
            except Exception as exc:
                print(f"[BotStatus] ❌ Failed to edit status embed in {guild_id}: {exc}")

    # ── Task loop — heartbeat every 60 seconds ────────────────────────────────

    @tasks.loop(seconds=60)
    async def _heartbeat(self) -> None:
        try:
            _update_history()
            await self._update(online=True)
        except Exception as e:
            print(f"[BotStatus] ⚠️ Error in heartbeat loop: {e}")

    @_heartbeat.before_loop
    async def _before_heartbeat(self) -> None:
        await self.bot.wait_until_ready()

    # ── Task loop — Owner status channel ping every 10 minutes ────────────────

    @tasks.loop(minutes=10)
    async def _owner_status_loop(self) -> None:
        try:
            await self.update_owner_status(state="online")
        except Exception as e:
            print(f"[BotStatus] ⚠️ Error in owner status loop: {e}")

    @_owner_status_loop.before_loop
    async def _before_owner_status_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ── Owner STATUS_CHANNEL Manager ──────────────────────────────────────────

    async def update_owner_status(self, state: str = "online", channel_id_override: int | None = None) -> tuple[bool, str]:
        ch_id = channel_id_override or _get_owner_channel_id()
        if not ch_id:
            msg = "STATUS_CHANNEL not configured in .env or database (use `/system setchannel`)"
            print(f"[OwnerStatus] ⚠️ {msg}")
            return False, msg

        ch = self.bot.get_channel(ch_id)
        if not ch:
            try:
                ch = await self.bot.fetch_channel(ch_id)
            except Exception as e:
                msg = f"Could not find or fetch channel {ch_id}: {e}"
                print(f"[OwnerStatus] ❌ {msg}")
                return False, msg

        if not isinstance(ch, discord.TextChannel):
            msg = f"Channel {ch_id} is not a TextChannel"
            print(f"[OwnerStatus] ❌ {msg}")
            return False, msg

        perms = ch.permissions_for(ch.guild.me)
        if not perms.send_messages:
            msg = f"Missing 'Send Messages' permission in #{ch.name} ({ch.id})"
            print(f"[OwnerStatus] ❌ {msg}")
            return False, msg

        now_ts = int(time.time())
        if state == "online":
            color = 0x57F287
            title = "🟢 Bot Status: Online"
            gif_url = GIF_ONLINE
            from bot_status_msg import get_status_message
            notice = get_status_message()
            lines = []
            if notice and notice.get("message"):
                lines.append(f"📢 **Announcement:**\n{notice['message']}\n")
            lines.append(f"📶 **Latency:** `{round(self.bot.latency * 1000)}ms`")
            lines.append(f"⏱️ **Uptime:** `{_fmt_uptime()}`")
            lines.append(f"🕒 **Last Checked:** <t:{now_ts}:R>")
            desc = "\n".join(lines)
            footer = "GKR Bot • Checked every 10 minutes"
        elif state == "restarting":
            color = 0xFEE75C
            title = "🟡 Bot Status: Restarting"
            gif_url = GIF_RESTARTING
            desc = f"⚠️ **The bot is currently restarting.** Services will resume shortly.\n🕒 **Timestamp:** <t:{now_ts}:R>"
            footer = "GKR Bot • Restarting..."
        else:
            color = 0xED4245
            title = "🔴 Bot Status: Offline"
            gif_url = GIF_OFFLINE
            desc = f"❌ **The bot is currently offline.**\n🕒 **Timestamp:** <t:{now_ts}:R>"
            footer = "GKR Bot • Offline"

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_image(url=gif_url)
        embed.set_footer(text=footer)

        msg_id = _load_owner_msg_id(ch_id)
        msg = None
        if msg_id:
            try:
                msg = await ch.fetch_message(msg_id)
            except Exception:
                msg = None

        if msg:
            try:
                await msg.edit(embed=embed, view=BotStatusView())
                print(f"[OwnerStatus] ✅ Edited status message ({msg.id}) in #{ch.name}")
                return True, f"Updated existing status embed in {ch.mention}"
            except Exception as e:
                print(f"[OwnerStatus] Edit failed, posting fresh message: {e}")

        if state != "offline":
            try:
                new_msg = await ch.send(embed=embed, view=BotStatusView())
                _save_owner_msg_id(ch_id, new_msg.id)
                print(f"[OwnerStatus] ✅ Posted new status message ({new_msg.id}) in #{ch.name}")
                return True, f"Posted new status embed in {ch.mention}"
            except Exception as e:
                err_msg = f"Failed to send status embed in {ch.mention}: {e}"
                print(f"[OwnerStatus] ❌ {err_msg}")
                return False, err_msg
        return True, "Offline state recorded"

    async def set_owner_status(self, state: str = "online") -> None:
        await self.update_owner_status(state=state)

    async def update_owner_status_now(self) -> None:
        await self.update_owner_status(state="online")

    def _check_owner_access(self, interaction: discord.Interaction) -> tuple[bool, str]:
        # 1. Guild check (only allowed in owner/dev server)
        owner_guild = (os.getenv("DISCORD_GUILD_ID") or os.getenv("DEV_GUILD_ID") or "").strip()
        if owner_guild.isdigit() and interaction.guild_id != int(owner_guild):
            return False, "❌ This command is only available in the owner's system server."

        # 2. User check
        owner_user = (os.getenv("OWNER_DISCORD_ID") or "").strip()
        if owner_user.isdigit() and interaction.user.id == int(owner_user):
            return True, ""
        if self.bot.owner_id and interaction.user.id == self.bot.owner_id:
            return True, ""
        if self.bot.owner_ids and interaction.user.id in self.bot.owner_ids:
            return True, ""
        if interaction.guild and interaction.guild.owner_id == interaction.user.id:
            return True, ""
        return False, "❌ Access restricted to the bot owner."

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        _seed_history()
        self._configs = _load_cfg()
        if not self._heartbeat.is_running():
            self._heartbeat.start()
        if not self._owner_status_loop.is_running():
            self._owner_status_loop.start()
        await self._update(online=True)
        await self.update_owner_status(state="online")

        # Sync /system immediately to owner guild so it appears right away
        owner_guild = (os.getenv("DISCORD_GUILD_ID") or os.getenv("DEV_GUILD_ID") or "").strip()
        if owner_guild.isdigit():
            try:
                g_obj = discord.Object(id=int(owner_guild))
                self.bot.tree.add_command(self.system_group, guild=g_obj, override=True)
                await self.bot.tree.sync(guild=g_obj)
                print(f"[BotStatus] ✅ Synced /system command to guild {owner_guild}")
            except Exception as e:
                print(f"[BotStatus] Warning syncing /system: {e}")

        print("[BotStatus] ✅ Live status dashboard active.")

    @commands.Cog.listener()
    async def on_disconnect(self) -> None:
        """Flip the embed to Offline when the bot loses its connection."""
        await self._update(online=False)
        await self.update_owner_status(state="offline")

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        """Flip back to Online when the connection is restored."""
        await self._update(online=True)
        await self.update_owner_status(state="online")

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
    # ── Owner-only hidden /system command group ───────────────────────────────

    system_group = app_commands.Group(
        name="system",
        description="Owner-only hidden system status commands",
    )

    @system_group.command(
        name="post",
        description="Force post or update the live status embed in the owner status channel",
    )
    async def sys_post(self, interaction: discord.Interaction) -> None:
        allowed, reason = self._check_owner_access(interaction)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        ok, msg = await self.update_owner_status(state="online")
        if ok:
            await interaction.followup.send(f"✅ **System Status Embed:** {msg}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ **System Status Error:** {msg}", ephemeral=True)

    @system_group.command(
        name="setchannel",
        description="Set the target channel for the owner status embed and post it immediately",
    )
    @app_commands.describe(channel="Text channel to receive the live status embed")
    async def sys_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        allowed, reason = self._check_owner_access(interaction)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        _set_owner_channel_id(channel.id)
        ok, msg = await self.update_owner_status(state="online", channel_id_override=channel.id)
        if ok:
            await interaction.followup.send(
                f"✅ Status channel set to {channel.mention}!\nResult: {msg}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"⚠️ Status channel set to {channel.mention}, but sending embed failed: {msg}\n"
                f"Make sure the bot has **View Channel**, **Send Messages**, and **Embed Links** permissions there.",
                ephemeral=True
            )

    @system_group.command(
        name="notice",
        description="Set a custom announcement notice text shown on the status embed",
    )
    @app_commands.describe(message="Notice text to display on the embed")
    async def sys_notice(self, interaction: discord.Interaction, message: str) -> None:
        allowed, reason = self._check_owner_access(interaction)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        from bot_status_msg import set_status_message
        set_status_message(message.strip(), author=f"{interaction.user.name}", active=True)
        await self.update_owner_status(state="online")
        await interaction.response.send_message(
            f"✅ **Status notice updated & pushed to embed:**\n> {message.strip()}",
            ephemeral=True
        )

    @system_group.command(
        name="clearnotice",
        description="Clear any custom announcement notice on the status embed",
    )
    async def sys_clearnotice(self, interaction: discord.Interaction) -> None:
        allowed, reason = self._check_owner_access(interaction)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        from bot_status_msg import clear_status_message
        clear_status_message()
        await self.update_owner_status(state="online")
        await interaction.response.send_message("✅ Status notice cleared and embed refreshed.", ephemeral=True)

    @system_group.command(
        name="info",
        description="View current owner status channel configuration and diagnostics",
    )
    async def sys_info(self, interaction: discord.Interaction) -> None:
        allowed, reason = self._check_owner_access(interaction)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        ch_id = _get_owner_channel_id()
        msg_id = _load_owner_msg_id(ch_id) if ch_id else None
        ch = self.bot.get_channel(ch_id) if ch_id else None

        info_lines = [
            "**🛠️ System Status Configuration Diagnostics**",
            f"• **Channel ID:** `{ch_id or 'Not Configured'}`",
            f"• **Channel Mention:** {ch.mention if ch else 'Not found in bot cache'}",
            f"• **Active Message ID:** `{msg_id or 'None'}`",
            f"• **Bot Latency:** `{round(self.bot.latency * 1000)}ms`",
            f"• **Uptime:** `{_fmt_uptime()}`",
            f"• **Loop Running:** `{'Yes' if self._owner_status_loop.is_running() else 'No'}`",
        ]
        if ch and hasattr(ch, "permissions_for"):
            perms = ch.permissions_for(ch.guild.me)
            info_lines.append(f"• **Bot Send Perms:** `{'Yes' if perms.send_messages else 'NO (Missing Perms!)'}`")
            info_lines.append(f"• **Bot Embed Perms:** `{'Yes' if perms.embed_links else 'NO (Missing Perms!)'}`")

        await interaction.response.send_message("\n".join(info_lines), ephemeral=True)



# ══════════════════════════════════════════════════════════════
#  Setup entry point
# ══════════════════════════════════════════════════════════════

async def setup(bot: commands.Bot) -> None:
    """Register the BotStatusCog with the bot."""
    _init_db()
    await bot.add_cog(BotStatusCog(bot))
    print("[BotStatus] Cog loaded — dashboard will activate on_ready.")

