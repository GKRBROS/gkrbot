"""
server_activity.py — Text and Game Activity Analytics

Features:
  • Text tracking: Counts messages sent, awards XP and Coins (with an anti-spam cooldown).
  • Game tracking: Tracks time spent playing specific games via Discord Presence.
  • /text stats, /text leaderboard
  • /game stats, /game leaderboard
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import datetime
from typing import Optional, Dict

import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_activity.sqlite3")

TEXT_XP_DEFAULT    = 5
TEXT_COIN_DEFAULT  = 2
TEXT_COOLDOWN_SEC  = 30  # Wait 30s before awarding XP/Coins again to prevent spam


def xp_for_level(level: int) -> int:
    """Total XP required to reach `level`. Scales quadratically."""
    return int(100 * (level ** 1.6))


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class ActivityDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            # Text Stats
            conn.execute("""
                CREATE TABLE IF NOT EXISTS text_stats (
                    user_id        TEXT NOT NULL,
                    guild_id       TEXT NOT NULL,
                    total_messages INTEGER NOT NULL DEFAULT 0,
                    xp             INTEGER NOT NULL DEFAULT 0,
                    coins          INTEGER NOT NULL DEFAULT 0,
                    level          INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            # Game Stats (Per Game)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS game_stats (
                    user_id       TEXT NOT NULL,
                    guild_id      TEXT NOT NULL,
                    game_name     TEXT NOT NULL,
                    total_minutes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id, game_name)
                )
            """)
            # Active Game Sessions (To calculate duration)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS game_sessions (
                    user_id    TEXT NOT NULL,
                    guild_id   TEXT NOT NULL,
                    game_name  TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    PRIMARY KEY (user_id, guild_id, game_name)
                )
            """)
            # Configuration
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activity_config (
                    guild_id         TEXT PRIMARY KEY,
                    text_xp_rate     INTEGER NOT NULL DEFAULT 5,
                    text_coin_rate   INTEGER NOT NULL DEFAULT 2,
                    announce_channel TEXT
                )
            """)
            conn.commit()

    # ── Text Analytics ────────────────────────────────────────────────────────

    def add_message(self, user_id: int, guild_id: int, xp: int, coins: int) -> dict:
        """Increment message count and add XP/coins. Returns updated row."""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO text_stats (user_id, guild_id, total_messages, xp, coins, level)
                VALUES (?, ?, 1, ?, ?, 0)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    total_messages = total_messages + 1,
                    xp             = xp + excluded.xp,
                    coins          = coins + excluded.coins
            """, (str(user_id), str(guild_id), xp, coins))
            conn.commit()
            row = conn.execute(
                "SELECT * FROM text_stats WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            ).fetchone()
        return dict(row)

    def get_text_stats(self, user_id: int, guild_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM text_stats WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            ).fetchone()
        return dict(row) if row else None

    def set_text_level(self, user_id: int, guild_id: int, level: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE text_stats SET level=? WHERE user_id=? AND guild_id=?",
                (level, str(user_id), str(guild_id))
            )
            conn.commit()

    def get_text_leaderboard(self, guild_id: int, sort_by: str = "messages", limit: int = 10) -> list[dict]:
        if sort_by == "xp":
            col = "xp"
        elif sort_by == "coins":
            col = "coins"
        else:
            col = "total_messages"
        
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM text_stats WHERE guild_id=? ORDER BY {col} DESC LIMIT ?",
                (str(guild_id), limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Game Analytics ────────────────────────────────────────────────────────

    def start_game_session(self, user_id: int, guild_id: int, game_name: str) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO game_sessions (user_id, guild_id, game_name, start_time)
                VALUES (?, ?, ?, ?)
            """, (str(user_id), str(guild_id), game_name, datetime.datetime.utcnow().isoformat()))
            conn.commit()

    def end_game_session(self, user_id: int, guild_id: int, game_name: str) -> Optional[int]:
        """Ends the session, updates game_stats, and returns elapsed minutes."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT start_time FROM game_sessions WHERE user_id=? AND guild_id=? AND game_name=?",
                (str(user_id), str(guild_id), game_name)
            ).fetchone()
            
            if not row:
                return None
                
            start_time = datetime.datetime.fromisoformat(row["start_time"])
            elapsed_mins = int((datetime.datetime.utcnow() - start_time).total_seconds() / 60)
            
            if elapsed_mins > 0:
                conn.execute("""
                    INSERT INTO game_stats (user_id, guild_id, game_name, total_minutes)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, guild_id, game_name) DO UPDATE SET
                        total_minutes = total_minutes + excluded.total_minutes
                """, (str(user_id), str(guild_id), game_name, elapsed_mins))
                
            conn.execute(
                "DELETE FROM game_sessions WHERE user_id=? AND guild_id=? AND game_name=?",
                (str(user_id), str(guild_id), game_name)
            )
            conn.commit()
        return max(0, elapsed_mins)

    def get_user_games(self, user_id: int, guild_id: int) -> list[dict]:
        game_map: dict[str, int] = {}
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT game_name, total_minutes FROM game_stats WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            ).fetchall()
            for r in rows:
                game_map[r["game_name"]] = int(r["total_minutes"])

            now = datetime.datetime.utcnow()
            active_rows = conn.execute(
                "SELECT game_name, start_time FROM game_sessions WHERE user_id=? AND guild_id=?",
                (str(user_id), str(guild_id))
            ).fetchall()
            for r in active_rows:
                try:
                    st = datetime.datetime.fromisoformat(r["start_time"])
                    mins = max(0, int((now - st).total_seconds() / 60))
                    gname = r["game_name"]
                    game_map[gname] = game_map.get(gname, 0) + mins
                except Exception:
                    pass

        sorted_games = sorted(game_map.items(), key=lambda x: x[1], reverse=True)
        return [{"game_name": g, "total_minutes": m} for g, m in sorted_games if m > 0]

    def get_game_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict]:
        """Returns top users by TOTAL game time across all games (including live sessions)."""
        totals: dict[str, int] = {}
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT user_id, SUM(total_minutes) as total_mins
                FROM game_stats
                WHERE guild_id=?
                GROUP BY user_id
            """, (str(guild_id),)).fetchall()
            for r in rows:
                totals[str(r["user_id"])] = int(r["total_mins"])

            now = datetime.datetime.utcnow()
            active_rows = conn.execute(
                "SELECT user_id, start_time FROM game_sessions WHERE guild_id=?",
                (str(guild_id),)
            ).fetchall()
            for r in active_rows:
                try:
                    st = datetime.datetime.fromisoformat(r["start_time"])
                    mins = max(0, int((now - st).total_seconds() / 60))
                    uid = str(r["user_id"])
                    totals[uid] = totals.get(uid, 0) + mins
                except Exception:
                    pass

        sorted_users = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"user_id": uid, "total_mins": mins} for uid, mins in sorted_users if mins > 0]

    def seed_demo_data(self, guild_id: int, user_ids: list[int | str]) -> None:
        """Seed realistic game tracking data for demonstration / verification screenshots."""
        demo_games = [
            ("Grand Theft Auto V", 435),
            ("Valorant", 280),
            ("Minecraft", 165),
            ("Counter-Strike 2", 320),
            ("Apex Legends", 195),
            ("Fortnite", 140),
            ("League of Legends", 250),
            ("Rocket League", 110),
        ]
        with self._conn() as conn:
            for idx, uid in enumerate(user_ids[:8]):
                picked = demo_games[idx % len(demo_games): (idx % len(demo_games)) + 2]
                for gname, mins in picked:
                    scaled_mins = max(30, int(mins * (1.0 - (idx * 0.08))))
                    conn.execute("""
                        INSERT INTO game_stats (user_id, guild_id, game_name, total_minutes)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(user_id, guild_id, game_name) DO UPDATE SET
                            total_minutes = excluded.total_minutes
                    """, (str(uid), str(guild_id), gname, scaled_mins))
            conn.commit()

    # ── Config ────────────────────────────────────────────────────────────────

    def get_config(self, guild_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM activity_config WHERE guild_id=?", (str(guild_id),)
            ).fetchone()
        if row:
            return dict(row)
        return {
            "guild_id": str(guild_id),
            "text_xp_rate": TEXT_XP_DEFAULT,
            "text_coin_rate": TEXT_COIN_DEFAULT,
            "announce_channel": None,
        }

    def set_config(self, guild_id: int, xp_rate: int, coin_rate: int, announce_channel: Optional[str]) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO activity_config
                    (guild_id, text_xp_rate, text_coin_rate, announce_channel)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    text_xp_rate     = excluded.text_xp_rate,
                    text_coin_rate   = excluded.text_coin_rate,
                    announce_channel = excluded.announce_channel
            """, (str(guild_id), xp_rate, coin_rate, announce_channel))
            conn.commit()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class ServerActivityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ActivityDatabase()
        self.db.initialize()
        
        # Cooldown map: (user_id, guild_id) -> float (timestamp of last rewarded message)
        self._text_cooldowns: Dict[tuple[int, int], float] = {}

    # ── Helper ────────────────────────────────────────────────────────────────

    async def _announce_levelup(self, guild: discord.Guild, user: discord.Member, new_level: int) -> None:
        cfg = self.db.get_config(guild.id)
        ch_id = cfg.get("announce_channel")
        if not ch_id:
            return
        ch = guild.get_channel(int(ch_id))
        if not ch:
            return
        embed = discord.Embed(
            title="🎉 Chat Level Up!",
            description=f"{user.mention} reached **Text Level {new_level}**!",
            color=0x5865F2,
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await ch.send(embed=embed)

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        now = asyncio.get_running_loop().time()
        
        # Check cooldown
        last_time = self._text_cooldowns.get((user_id, guild_id), 0.0)
        
        # They always get a message count tick, but XP/Coins are subject to cooldown
        give_xp = False
        if now - last_time >= TEXT_COOLDOWN_SEC:
            self._text_cooldowns[(user_id, guild_id)] = now
            give_xp = True

        cfg = self.db.get_config(guild_id)
        xp_gain = cfg["text_xp_rate"] if give_xp else 0
        coin_gain = cfg["text_coin_rate"] if give_xp else 0

        stats = self.db.add_message(user_id, guild_id, xp_gain, coin_gain)

        # Deposit into global economy wallet
        if give_xp and coin_gain > 0:
            eco = self.bot.get_cog("EconomyCog")
            if eco:
                eco.db.add_wallet(guild_id, user_id, coin_gain)

        # Level up check
        if give_xp:
            current_level = stats["level"]
            new_level = current_level
            while stats["xp"] >= xp_for_level(new_level + 1):
                new_level += 1
            if new_level > current_level:
                self.db.set_text_level(user_id, guild_id, new_level)
                if isinstance(message.author, discord.Member):
                    await self._announce_levelup(message.guild, message.author, new_level)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.bot:
            return
            
        guild_id = after.guild.id
        user_id = after.id
        
        def get_games(activities):
            """Extracts game names from a member's activities."""
            games = []
            for act in activities:
                if act and (getattr(act, "type", None) == discord.ActivityType.playing or isinstance(act, discord.Game)) and getattr(act, "name", None):
                    games.append(act.name)
            return set(games)
            
        before_games = get_games(before.activities)
        after_games = get_games(after.activities)
        
        started = after_games - before_games
        stopped = before_games - after_games
        
        for game in started:
            self.db.start_game_session(user_id, guild_id, game)
            
        for game in stopped:
            self.db.end_game_session(user_id, guild_id, game)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Scan active presences across guilds on startup."""
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot:
                    continue
                for act in member.activities:
                    if act and (getattr(act, "type", None) == discord.ActivityType.playing or isinstance(act, discord.Game)) and getattr(act, "name", None):
                        self.db.start_game_session(member.id, guild.id, act.name)

    # ── Text Commands ─────────────────────────────────────────────────────────

    text_group = app_commands.Group(name="text", description="Text activity, XP, and leaderboards")

    @text_group.command(name="stats", description="View your or another user's text activity stats")
    @app_commands.describe(user="The user to check (leave blank for yourself)")
    async def text_stats(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        target = user or interaction.user
        stats = self.db.get_text_stats(target.id, interaction.guild.id)

        embed = discord.Embed(
            title=f"💬 Text Stats — {target.display_name}",
            color=0x3498DB,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if not stats:
            embed.description = "No chat activity recorded yet."
        else:
            total_msgs = stats["total_messages"]
            lvl = stats["level"]
            current_xp = stats["xp"]
            next_xp = xp_for_level(lvl + 1)
            progress = min(100, int((current_xp / max(next_xp, 1)) * 100))
            bar = "█" * (progress // 10) + "░" * (10 - progress // 10)

            embed.add_field(name="📩 Messages Sent", value=f"`{total_msgs:,}`", inline=True)
            embed.add_field(name="⭐ Text XP",       value=f"`{current_xp:,}`", inline=True)
            embed.add_field(name="🪙 Coins",         value=f"`{stats['coins']:,}`", inline=True)
            embed.add_field(name="🏅 Level",         value=f"`{lvl}`", inline=False)
            embed.add_field(
                name=f"📈 Progress to Lv.{lvl + 1}",
                value=f"`{bar}` {progress}%\n`{current_xp:,} / {next_xp:,} XP`",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @text_group.command(name="leaderboard", description="View the text activity leaderboard")
    @app_commands.describe(sort="Sort by Messages, XP, or Coins")
    @app_commands.choices(sort=[
        app_commands.Choice(name="Messages 📩", value="messages"),
        app_commands.Choice(name="XP ⭐",        value="xp"),
        app_commands.Choice(name="Coins 🪙",     value="coins"),
    ])
    async def text_leaderboard(self, interaction: discord.Interaction, sort: str = "messages") -> None:
        rows = self.db.get_text_leaderboard(interaction.guild.id, sort_by=sort)
        label = "Messages 📩" if sort == "messages" else ("XP ⭐" if sort == "xp" else "Coins 🪙")
        
        embed = discord.Embed(
            title=f"{label} Leaderboard — {interaction.guild.name}",
            color=0x3498DB,
        )
        if not rows:
            embed.description = "No chat activity recorded yet."
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, r in enumerate(rows):
                member = interaction.guild.get_member(int(r["user_id"]))
                name = member.display_name if member else f"User {r['user_id']}"
                medal = medals[i] if i < 3 else f"`#{i + 1}`"
                
                if sort == "messages":
                    val = f"{r['total_messages']:,} msgs"
                elif sort == "xp":
                    val = f"{r['xp']:,} XP"
                else:
                    val = f"{r['coins']:,} 🪙"
                    
                lines.append(f"{medal} **{name}** — {val} (Lv. {r['level']})")
            embed.description = "\n".join(lines)
            
        await interaction.response.send_message(embed=embed)

    # ── Game Commands ─────────────────────────────────────────────────────────

    game_group = app_commands.Group(name="game", description="Game activity tracking and leaderboards")

    @game_group.command(name="stats", description="View your or another user's game activity")
    @app_commands.describe(user="The user to check (leave blank for yourself)")
    async def game_stats(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        target = user or interaction.user
        games = self.db.get_user_games(target.id, interaction.guild.id)
        
        embed = discord.Embed(
            title=f"🎮 Game Activity — {target.display_name}",
            color=0xE67E22,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        if not games:
            embed.description = "No gaming activity recorded yet."
        else:
            total_mins_all = sum(g["total_minutes"] for g in games)
            h, m = divmod(total_mins_all, 60)
            embed.description = f"**Total Playtime:** `{h}h {m}m`\n\n**Most Played:**"
            
            lines = []
            for i, g in enumerate(games[:10]):  # top 10 games
                gh, gm = divmod(g["total_minutes"], 60)
                lines.append(f"`#{i+1}` **{g['game_name']}** — {gh}h {gm}m")
            
            embed.add_field(name="Top Games", value="\n".join(lines), inline=False)
            
        await interaction.response.send_message(embed=embed)

    @game_group.command(name="leaderboard", description="View the overall gaming time leaderboard")
    async def game_leaderboard(self, interaction: discord.Interaction) -> None:
        rows = self.db.get_game_leaderboard(interaction.guild.id)
        
        embed = discord.Embed(
            title=f"🎮 Top Gamers — {interaction.guild.name}",
            color=0xE67E22,
        )
        
        if not rows:
            embed.description = "No gaming activity recorded yet."
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, r in enumerate(rows):
                member = interaction.guild.get_member(int(r["user_id"]))
                name = member.display_name if member else f"User {r['user_id']}"
                medal = medals[i] if i < 3 else f"`#{i + 1}`"
                
                h, m = divmod(r["total_mins"], 60)
                lines.append(f"{medal} **{name}** — {h}h {m}m")
                
            embed.description = "\n".join(lines)
            
        await interaction.response.send_message(embed=embed)

    @game_group.command(name="seed", description="Seed demo game stats for leaderboard testing / verification (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def game_seed(self, interaction: discord.Interaction) -> None:
        """Seed realistic game tracking data for demonstration / verification screenshots."""
        member_ids = [m.id for m in interaction.guild.members if not m.bot]
        if not member_ids:
            member_ids = [interaction.user.id]
        self.db.seed_demo_data(interaction.guild.id, member_ids)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Game Demo Data Seeded",
                description="Demo game activity data has been seeded! Run `/game leaderboard` or `/game stats` to view it.",
                color=0x57F287
            ),
            ephemeral=True
        )

    # ── Config Command ────────────────────────────────────────────────────────

    @app_commands.command(name="activity_config", description="Configure Text & Game analytics (Admin only)")
    @app_commands.describe(
        text_xp="Text XP per message (default 5, 30s cooldown)",
        text_coins="Coins per message (default 2, 30s cooldown)",
        announce_channel="Channel for text level-up announcements",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def activity_config(
        self,
        interaction: discord.Interaction,
        text_xp: Optional[int] = None,
        text_coins: Optional[int] = None,
        announce_channel: Optional[discord.TextChannel] = None,
    ) -> None:
        cfg = self.db.get_config(interaction.guild.id)
        new_xp    = text_xp   if text_xp   is not None else cfg["text_xp_rate"]
        new_coins = text_coins if text_coins is not None else cfg["text_coin_rate"]
        new_ch    = str(announce_channel.id) if announce_channel else cfg.get("announce_channel")

        self.db.set_config(interaction.guild.id, new_xp, new_coins, new_ch)

        ch_mention = f"<#{new_ch}>" if new_ch else "Not set"
        embed = discord.Embed(
            title="✅ Activity Config Updated",
            color=0x57F287,
            description=(
                f"**Text XP per message:** `{new_xp}`\n"
                f"**Text Coins per message:** `{new_coins}`\n"
                f"*(Note: There is a 30-second cooldown between XP/Coin rewards to prevent spam)*\n"
                f"**Announce channel:** {ch_mention}"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Extension setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerActivityCog(bot))
