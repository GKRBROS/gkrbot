"""
voice_analytics.py — Voice XP, Coins, Levels, Achievements & Leaderboards

Features:
  • XP & Coins earned per minute spent in voice channels
  • Levelling system with configurable thresholds
  • Achievements (First Hour, Night Owl, 10h, 50h, 100h, 500h, etc.)
  • Per-guild configuration (rates, level-up announcement channel)
  • /voice stats, /voice leaderboard, /voice config slash commands
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "voice_analytics.sqlite3")

XP_PER_MINUTE_DEFAULT    = 10
COINS_PER_MINUTE_DEFAULT = 5


def xp_for_level(level: int) -> int:
    """Total XP required to reach `level`. Scales quadratically."""
    return int(100 * (level ** 1.6))


ACHIEVEMENTS = {
    "first_minute":  {"name": "First Step",     "emoji": "👣", "desc": "Spend 1 minute in voice",     "minutes": 1},
    "first_hour":    {"name": "Hour One",        "emoji": "⏱️",  "desc": "Spend 1 hour in voice",       "minutes": 60},
    "night_owl":     {"name": "Night Owl",       "emoji": "🦉",  "desc": "Spend 5 hours in voice",      "minutes": 300},
    "voice_veteran": {"name": "Voice Veteran",   "emoji": "🎙️",  "desc": "Spend 10 hours in voice",     "minutes": 600},
    "marathon":      {"name": "Marathon",        "emoji": "🏃",  "desc": "Spend 50 hours in voice",     "minutes": 3000},
    "legend":        {"name": "Legend",          "emoji": "🏆",  "desc": "Spend 100 hours in voice",    "minutes": 6000},
    "immortal":      {"name": "Immortal",        "emoji": "⚡",  "desc": "Spend 500 hours in voice",    "minutes": 30000},
}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class VoiceDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_stats (
                    user_id       TEXT NOT NULL,
                    guild_id      TEXT NOT NULL,
                    total_minutes INTEGER NOT NULL DEFAULT 0,
                    xp            INTEGER NOT NULL DEFAULT 0,
                    coins         INTEGER NOT NULL DEFAULT 0,
                    level         INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_sessions (
                    user_id    TEXT NOT NULL,
                    guild_id   TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    join_time  TEXT NOT NULL,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_achievements (
                    user_id         TEXT NOT NULL,
                    guild_id        TEXT NOT NULL,
                    achievement_key TEXT NOT NULL,
                    unlocked_at     TEXT NOT NULL,
                    PRIMARY KEY (user_id, guild_id, achievement_key)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_config (
                    guild_id         TEXT PRIMARY KEY,
                    xp_per_min       INTEGER NOT NULL DEFAULT 10,
                    coins_per_min    INTEGER NOT NULL DEFAULT 5,
                    announce_channel TEXT
                )
            """)
            conn.commit()

    # ── Sessions ─────────────────────────────────────────────────────────────

    def start_session(self, user_id: int, guild_id: int, channel_id: int) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO voice_sessions (user_id, guild_id, channel_id, join_time)
                VALUES (?, ?, ?, ?)
            """, (str(user_id), str(guild_id), str(channel_id),
                  datetime.datetime.utcnow().isoformat()))
            conn.commit()

    def end_session(self, user_id: int, guild_id: int) -> Optional[int]:
        """End session and return minutes elapsed, or None if no session."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT join_time FROM voice_sessions WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            ).fetchone()
            if not row:
                return None
            join_time = datetime.datetime.fromisoformat(row["join_time"])
            elapsed = int((datetime.datetime.utcnow() - join_time).total_seconds() / 60)
            conn.execute(
                "DELETE FROM voice_sessions WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            )
            conn.commit()
        return max(0, elapsed)

    def get_active_sessions(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM voice_sessions").fetchall()
        return [dict(r) for r in rows]

    # ── Stats ─────────────────────────────────────────────────────────────────

    def add_time(self, user_id: int, guild_id: int, minutes: int,
                 xp_per_min: int, coins_per_min: int) -> dict:
        """Accumulate minutes, XP, coins. Returns updated stats row."""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO voice_stats (user_id, guild_id, total_minutes, xp, coins, level)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    total_minutes = total_minutes + excluded.total_minutes,
                    xp            = xp            + excluded.xp,
                    coins         = coins         + excluded.coins
            """, (str(user_id), str(guild_id),
                  minutes, minutes * xp_per_min, minutes * coins_per_min))
            conn.commit()
            row = conn.execute(
                "SELECT * FROM voice_stats WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            ).fetchone()
        return dict(row)

    def get_stats(self, user_id: int, guild_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM voice_stats WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            ).fetchone()
        return dict(row) if row else None

    def set_level(self, user_id: int, guild_id: int, level: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE voice_stats SET level=? WHERE user_id=? AND guild_id=?",
                (level, str(user_id), str(guild_id))
            )
            conn.commit()

    def get_leaderboard(self, guild_id: int, sort_by: str = "xp",
                        limit: int = 10) -> list[dict]:
        col = "xp" if sort_by == "xp" else "coins"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM voice_stats WHERE guild_id=? ORDER BY {col} DESC LIMIT ?",
                (str(guild_id), limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Achievements ──────────────────────────────────────────────────────────

    def get_achievements(self, user_id: int, guild_id: int) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT achievement_key FROM voice_achievements WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            ).fetchall()
        return [r["achievement_key"] for r in rows]

    def unlock_achievement(self, user_id: int, guild_id: int, key: str) -> bool:
        """Returns True if newly unlocked, False if already existed."""
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO voice_achievements
                        (user_id, guild_id, achievement_key, unlocked_at)
                    VALUES (?, ?, ?, ?)
                """, (str(user_id), str(guild_id), key,
                      datetime.datetime.utcnow().isoformat()))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    # ── Config ────────────────────────────────────────────────────────────────

    def get_config(self, guild_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM voice_config WHERE guild_id=?", (str(guild_id),)
            ).fetchone()
        if row:
            return dict(row)
        return {
            "guild_id": str(guild_id),
            "xp_per_min": XP_PER_MINUTE_DEFAULT,
            "coins_per_min": COINS_PER_MINUTE_DEFAULT,
            "announce_channel": None,
        }

    def set_config(self, guild_id: int, xp_per_min: int, coins_per_min: int,
                   announce_channel: Optional[str]) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO voice_config
                    (guild_id, xp_per_min, coins_per_min, announce_channel)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    xp_per_min       = excluded.xp_per_min,
                    coins_per_min    = excluded.coins_per_min,
                    announce_channel = excluded.announce_channel
            """, (str(guild_id), xp_per_min, coins_per_min, announce_channel))
            conn.commit()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class VoiceAnalyticsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = VoiceDatabase()
        self.db.initialize()

    async def cog_load(self) -> None:
        self._award_loop.start()

    async def cog_unload(self) -> None:
        self._award_loop.cancel()

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _announce_levelup(self, guild: discord.Guild,
                                user: discord.Member, new_level: int) -> None:
        cfg = self.db.get_config(guild.id)
        ch_id = cfg.get("announce_channel")
        if not ch_id:
            return
        ch = guild.get_channel(int(ch_id))
        if not ch:
            return
        embed = discord.Embed(
            title="🎉 Level Up!",
            description=f"{user.mention} reached **Voice Level {new_level}**!",
            color=0x5865F2,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await ch.send(embed=embed)

    async def _announce_achievement(self, guild: discord.Guild,
                                    user: discord.Member, key: str) -> None:
        ach = ACHIEVEMENTS[key]
        cfg = self.db.get_config(guild.id)
        ch_id = cfg.get("announce_channel")
        if not ch_id:
            return
        ch = guild.get_channel(int(ch_id))
        if not ch:
            return
        embed = discord.Embed(
            title=f"{ach['emoji']} Achievement Unlocked!",
            description=f"{user.mention} earned **{ach['name']}**\n*{ach['desc']}*",
            color=0xFFD700,
        )
        await ch.send(embed=embed)

    async def _process_awards(self, user_id: int, guild_id: int,
                               minutes: int) -> None:
        """Credit XP/coins and check level-ups and achievements."""
        if minutes <= 0:
            return
        cfg = self.db.get_config(guild_id)
        stats = self.db.add_time(
            user_id, guild_id, minutes,
            cfg["xp_per_min"], cfg["coins_per_min"]
        )

        # Deposit into global economy wallet
        eco = self.bot.get_cog("EconomyCog")
        if eco:
            coins_earned = minutes * cfg["coins_per_min"]
            if coins_earned > 0:
                eco.db.add_wallet(guild_id, user_id, coins_earned)


        # Level-up check
        current_level = stats["level"]
        new_level = current_level
        while stats["xp"] >= xp_for_level(new_level + 1):
            new_level += 1
        if new_level > current_level:
            self.db.set_level(user_id, guild_id, new_level)
            guild = self.bot.get_guild(guild_id)
            if guild:
                member = guild.get_member(user_id)
                if member:
                    await self._announce_levelup(guild, member, new_level)

        # Achievement checks
        total_mins = stats["total_minutes"]
        guild = self.bot.get_guild(guild_id)
        member = guild.get_member(user_id) if guild else None
        for key, ach in ACHIEVEMENTS.items():
            if total_mins >= ach["minutes"]:
                newly = self.db.unlock_achievement(user_id, guild_id, key)
                if newly and guild and member:
                    await self._announce_achievement(guild, member, key)

    # ── Voice state listener ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        joined = after.channel is not None and before.channel is None
        left   = after.channel is None and before.channel is not None
        moved  = (after.channel is not None and before.channel is not None
                  and after.channel != before.channel)

        if joined:
            self.db.start_session(member.id, member.guild.id, after.channel.id)

        elif left:
            mins = self.db.end_session(member.id, member.guild.id)
            if mins:
                await self._process_awards(member.id, member.guild.id, mins)

        elif moved:
            mins = self.db.end_session(member.id, member.guild.id)
            if mins:
                await self._process_awards(member.id, member.guild.id, mins)
            self.db.start_session(member.id, member.guild.id, after.channel.id)

    # ── Background award tick (every 5 min for users already in VC) ──────────

    @tasks.loop(minutes=5)
    async def _award_loop(self) -> None:
        """Award XP every 5 minutes to users currently in voice."""
        sessions = self.db.get_active_sessions()
        for s in sessions:
            try:
                guild = self.bot.get_guild(int(s["guild_id"]))
                if not guild:
                    continue
                member = guild.get_member(int(s["user_id"]))
                if not member or not member.voice or not member.voice.channel:
                    self.db.end_session(int(s["user_id"]), int(s["guild_id"]))
                    continue
                await self._process_awards(int(s["user_id"]), int(s["guild_id"]), 5)
                # Reset session clock to avoid double-counting on leave
                self.db.start_session(
                    int(s["user_id"]), int(s["guild_id"]),
                    member.voice.channel.id
                )
            except Exception as exc:
                print(f"[VoiceAnalytics] Award loop error: {exc}")

    @_award_loop.before_loop
    async def _before_award_loop(self):
        await self.bot.wait_until_ready()

    # ── /voice group ──────────────────────────────────────────────────────────

    voice_group = app_commands.Group(
        name="voice", description="Voice analytics — XP, coins, levels, achievements"
    )

    @voice_group.command(name="stats", description="View voice stats for you or another user")
    @app_commands.describe(user="The user to check (leave blank for yourself)")
    async def voice_stats(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ) -> None:
        target = user or interaction.user
        stats = self.db.get_stats(target.id, interaction.guild.id)
        achievements = self.db.get_achievements(target.id, interaction.guild.id)

        embed = discord.Embed(
            title=f"🎙️ Voice Stats — {target.display_name}",
            color=0x5865F2,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if not stats:
            embed.description = "No voice activity recorded yet."
        else:
            total_mins = stats["total_minutes"]
            hours, mins = divmod(total_mins, 60)
            lvl = stats["level"]
            current_xp = stats["xp"]
            next_xp = xp_for_level(lvl + 1)
            progress = min(100, int((current_xp / max(next_xp, 1)) * 100))
            bar = "█" * (progress // 10) + "░" * (10 - progress // 10)

            embed.add_field(name="⏱️ Time in Voice", value=f"`{hours}h {mins}m`",   inline=True)
            embed.add_field(name="⭐ XP",             value=f"`{current_xp:,}`",     inline=True)
            embed.add_field(name="🪙 Coins",           value=f"`{stats['coins']:,}`", inline=True)
            embed.add_field(name="🏅 Level",           value=f"`{lvl}`",             inline=True)
            embed.add_field(
                name=f"📈 Progress to Lv.{lvl + 1}",
                value=f"`{bar}` {progress}%\n`{current_xp:,} / {next_xp:,} XP`",
                inline=False,
            )

            if achievements:
                badges = "  ".join(
                    f"{ACHIEVEMENTS[k]['emoji']} {ACHIEVEMENTS[k]['name']}"
                    for k in achievements if k in ACHIEVEMENTS
                )
                embed.add_field(
                    name=f"🏆 Achievements ({len(achievements)})",
                    value=badges, inline=False
                )
            else:
                embed.add_field(
                    name="🏆 Achievements",
                    value="None yet — spend time in voice to earn some!", inline=False
                )

        await interaction.response.send_message(embed=embed)

    @voice_group.command(name="leaderboard", description="View the voice leaderboard")
    @app_commands.describe(sort="Sort by XP or Coins")
    @app_commands.choices(sort=[
        app_commands.Choice(name="XP ⭐",    value="xp"),
        app_commands.Choice(name="Coins 🪙", value="coins"),
    ])
    async def voice_leaderboard(
        self,
        interaction: discord.Interaction,
        sort: str = "xp",
    ) -> None:
        rows = self.db.get_leaderboard(interaction.guild.id, sort_by=sort)
        label = "XP ⭐" if sort == "xp" else "Coins 🪙"
        embed = discord.Embed(
            title=f"{label} Leaderboard — {interaction.guild.name}",
            color=0xFFD700,
        )
        if not rows:
            embed.description = "No voice activity recorded yet."
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, r in enumerate(rows):
                member = interaction.guild.get_member(int(r["user_id"]))
                name = member.display_name if member else f"User {r['user_id']}"
                medal = medals[i] if i < 3 else f"`#{i + 1}`"
                val = r["xp"] if sort == "xp" else r["coins"]
                h, m = divmod(r["total_minutes"], 60)
                unit = "XP" if sort == "xp" else "🪙"
                lines.append(f"{medal} **{name}** — {val:,} {unit} • {h}h {m}m")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)

    @voice_group.command(
        name="config",
        description="Configure voice analytics — XP/coin rates, announcement channel (Admin only)"
    )
    @app_commands.describe(
        xp_per_minute="XP per minute in voice (default 10)",
        coins_per_minute="Coins per minute in voice (default 5)",
        announce_channel="Channel for level-up & achievement announcements",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def voice_config(
        self,
        interaction: discord.Interaction,
        xp_per_minute: Optional[int] = None,
        coins_per_minute: Optional[int] = None,
        announce_channel: Optional[discord.TextChannel] = None,
    ) -> None:
        cfg = self.db.get_config(interaction.guild.id)
        new_xp    = xp_per_minute   if xp_per_minute   is not None else cfg["xp_per_min"]
        new_coins = coins_per_minute if coins_per_minute is not None else cfg["coins_per_min"]
        new_ch    = str(announce_channel.id) if announce_channel else cfg.get("announce_channel")

        self.db.set_config(interaction.guild.id, new_xp, new_coins, new_ch)

        ch_mention = f"<#{new_ch}>" if new_ch else "Not set"
        embed = discord.Embed(
            title="✅ Voice Analytics Config Updated",
            color=0x57F287,
            description=(
                f"**XP per minute:** `{new_xp}`\n"
                f"**Coins per minute:** `{new_coins}`\n"
                f"**Announce channel:** {ch_mention}"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Extension setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceAnalyticsCog(bot))
