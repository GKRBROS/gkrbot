"""
profiles.py — Member Profiles & Achievements System for GKR Bot.

Features:
  • /profile [@user]  — Rich embed showing ALL user stats (join date, level,
                        XP, coins, voice time, chat messages, games, warnings,
                        roles, achievements)
  • /achievements     — View all achievements and which ones you've unlocked
  • Achievements auto-unlock from multiple cogs (voice, text, economy, security)
"""

from __future__ import annotations

import os
import sqlite3
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from gkr_ui import C, embed_error, embed_success, embed_info, embed_warning, Paginator, paginate_leaderboard, BOT_NAME  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "profiles.sqlite3")

# ---------------------------------------------------------------------------
# Achievement Definitions (cross-cog)
# ---------------------------------------------------------------------------

ALL_ACHIEVEMENTS: dict[str, dict] = {
    # Voice achievements
    "first_voice":    {"emoji": "🎤", "name": "First Words",      "desc": "Spent your first minute in voice."},
    "voice_1h":       {"emoji": "🎙️", "name": "Voice Regular",    "desc": "Spent 1 hour in voice channels."},
    "voice_10h":      {"emoji": "🔊", "name": "Voice Enthusiast", "desc": "Spent 10 hours in voice channels."},
    "voice_100h":     {"emoji": "🏆", "name": "Voice Legend",     "desc": "Spent 100 hours in voice channels."},
    # Chat achievements
    "first_message":  {"emoji": "💬", "name": "First Message",    "desc": "Sent your first message."},
    "chat_100":       {"emoji": "📝", "name": "Regular Chatter",  "desc": "Sent 100 messages."},
    "chat_1000":      {"emoji": "💎", "name": "Chatterbox",       "desc": "Sent 1,000 messages."},
    "chat_10000":     {"emoji": "👑", "name": "Message King",     "desc": "Sent 10,000 messages."},
    # Economy achievements
    "first_coins":    {"emoji": "🪙", "name": "First Coins",      "desc": "Earned your first coins."},
    "rich_1000":      {"emoji": "💰", "name": "Getting Rich",     "desc": "Accumulated 1,000 coins total."},
    "rich_10000":     {"emoji": "🤑", "name": "Millionaire",      "desc": "Accumulated 10,000 coins total."},
    # Gaming achievements
    "first_game":     {"emoji": "🎮", "name": "Gamer",            "desc": "Played your first game."},
    "game_10h":       {"emoji": "🕹️", "name": "Dedicated Gamer",  "desc": "Played games for 10 hours."},
    # Community
    "verified":       {"emoji": "✅", "name": "Verified Member",  "desc": "Verified yourself in the server."},
    "og_member":      {"emoji": "⭐", "name": "OG Member",        "desc": "One of the first 100 members to join."},
}

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class ProfileDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    unlocked_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id, key)
                )
            """)
            conn.commit()

    def unlock(self, guild_id: int, user_id: int, key: str) -> bool:
        """Returns True if newly unlocked, False if already had it."""
        if key not in ALL_ACHIEVEMENTS:
            return False
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO achievements (guild_id, user_id, key, unlocked_at) VALUES (?, ?, ?, ?)",
                    (str(guild_id), str(user_id), key, datetime.datetime.utcnow().isoformat())
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_unlocked(self, guild_id: int, user_id: int) -> dict[str, str]:
        """Returns {key: unlocked_at} for all unlocked achievements."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key, unlocked_at FROM achievements WHERE guild_id=? AND user_id=?",
                (str(guild_id), str(user_id))
            ).fetchall()
        return {r["key"]: r["unlocked_at"] for r in rows}

    def has(self, guild_id: int, user_id: int, key: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM achievements WHERE guild_id=? AND user_id=? AND key=?",
                (str(guild_id), str(user_id), key)
            ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class ProfilesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ProfileDatabase()
        self.db.initialize()

    def _safe_get(self, cog_name: str):
        return self.bot.get_cog(cog_name)

    async def _unlock_and_announce(self, guild: discord.Guild, member: discord.Member, key: str):
        """Unlock achievement and try to announce in an activity channel."""
        newly = self.db.unlock(guild.id, member.id, key)
        if not newly:
            return

        ach = ALL_ACHIEVEMENTS[key]
        # Try to find an announce channel from voice config
        try:
            voice_cog = self._safe_get("VoiceAnalyticsCog")
            if voice_cog:
                cfg = voice_cog.db.get_config(guild.id)
                ch_id = cfg.get("announce_channel")
                if ch_id:
                    ch = guild.get_channel(int(ch_id))
                    if ch:
                        embed = discord.Embed(
                            title=f"{ach['emoji']}  Achievement Unlocked!",
                            description=f"{member.mention} earned **{ach['name']}**\n*{ach['desc']}*",
                            color=C.GOLD
                        )
                        embed.set_footer(text=f"{BOT_NAME} Achievements")
                        await ch.send(embed=embed)
        except Exception:
            pass

    # ── Listeners for auto-achievement tracking ─────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        uid = message.author.id
        gid = message.guild.id

        # Check chat achievements by reading text stats
        activity_cog = self._safe_get("ServerActivityCog")
        if activity_cog:
            stats = activity_cog.db.get_text_stats(uid, gid)
            if stats:
                msgs = stats.get("total_messages", 0)
                if msgs >= 1 and not self.db.has(gid, uid, "first_message"):
                    await self._unlock_and_announce(message.guild, message.author, "first_message")
                if msgs >= 100:
                    await self._unlock_and_announce(message.guild, message.author, "chat_100")
                if msgs >= 1000:
                    await self._unlock_and_announce(message.guild, message.author, "chat_1000")
                if msgs >= 10000:
                    await self._unlock_and_announce(message.guild, message.author, "chat_10000")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """OG Member check."""
        if member.bot:
            return
        # If guild has 100 or fewer real members at time of join
        real_count = sum(1 for m in member.guild.members if not m.bot)
        if real_count <= 100:
            await self._unlock_and_announce(member.guild, member, "og_member")

    # ── Commands ────────────────────────────────────────────────────────────

    @app_commands.command(name="profile", description="View your or another user's full profile")
    @app_commands.describe(user="The user to view (default: yourself)")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        target = user or interaction.user
        if target.bot:
            await interaction.response.send_message(embed=embed_error("Bots don't have profiles!"), ephemeral=True)
            return

        await interaction.response.defer()
        guild = interaction.guild

        embed = discord.Embed(
            title=f"👤  {target.display_name}'s Profile",
            color=target.color if target.color.value else C.BRAND
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # --- Basic Info ---
        joined_at = target.joined_at
        created_at = target.created_at
        embed.add_field(
            name="📅 Dates",
            value=(
                f"**Joined Server:** <t:{int(joined_at.timestamp())}:R>\n"
                f"**Account Created:** <t:{int(created_at.timestamp())}:R>"
            ),
            inline=False
        )

        # --- Voice Stats ---
        voice_cog = self._safe_get("VoiceAnalyticsCog")
        if voice_cog:
            vstats = voice_cog.db.get_stats(target.id, guild.id)
            if vstats:
                hours, mins = divmod(vstats["total_minutes"], 60)
                embed.add_field(
                    name="🎙️ Voice",
                    value=(
                        f"**Time:** {hours}h {mins}m\n"
                        f"**Level:** {vstats['level']}\n"
                        f"**XP:** {vstats['xp']:,}"
                    ),
                    inline=True
                )
            else:
                embed.add_field(name="🎙️ Voice", value="No data yet", inline=True)

        # --- Text Stats ---
        activity_cog = self._safe_get("ServerActivityCog")
        if activity_cog:
            tstats = activity_cog.db.get_text_stats(target.id, guild.id)
            if tstats:
                embed.add_field(
                    name="💬 Chat",
                    value=(
                        f"**Messages:** {tstats['total_messages']:,}\n"
                        f"**Level:** {tstats['level']}\n"
                        f"**XP:** {tstats['xp']:,}"
                    ),
                    inline=True
                )
            else:
                embed.add_field(name="💬 Chat", value="No data yet", inline=True)

        # --- Economy ---
        eco_cog = self._safe_get("EconomyCog")
        if eco_cog:
            bal = eco_cog.db.get_balance(guild.id, target.id)
            total = bal["wallet"] + bal["bank"]
            embed.add_field(
                name="💰 Economy",
                value=(
                    f"**Wallet:** 🪙 {bal['wallet']:,}\n"
                    f"**Bank:** 🏦 {bal['bank']:,}\n"
                    f"**Total:** 💎 {total:,}"
                ),
                inline=True
            )

        # --- Game Stats ---
        if activity_cog:
            games = activity_cog.db.get_user_games(target.id, guild.id)
            if games:
                top = games[0]
                hours, mins = divmod(top["total_minutes"], 60)
                embed.add_field(
                    name="🎮 Gaming",
                    value=f"**Top Game:** {top['game_name']}\n**Time:** {hours}h {mins}m\n**Games Played:** {len(games)}",
                    inline=True
                )

        # --- Warnings ---
        security_cog = self._safe_get("SecurityCog")
        if security_cog:
            warns = security_cog.db.get_warnings(guild.id, target.id)
            embed.add_field(name="⚠️ Warnings", value=str(len(warns)), inline=True)

        # --- Top Roles ---
        roles = [r for r in target.roles if r.name != "@everyone"]
        roles.sort(key=lambda r: r.position, reverse=True)
        top_roles = roles[:5]
        if top_roles:
            embed.add_field(
                name=f"🏷️ Roles ({len(roles)} total)",
                value=" ".join(r.mention for r in top_roles),
                inline=False
            )

        # --- Achievements ---
        unlocked = self.db.get_unlocked(guild.id, target.id)
        if unlocked:
            ach_display = []
            for key, unlocked_at in list(unlocked.items())[:8]:
                ach = ALL_ACHIEVEMENTS.get(key)
                if ach:
                    ach_display.append(f"{ach['emoji']} {ach['name']}")
            remaining = len(unlocked) - len(ach_display)
            ach_text = " · ".join(ach_display)
            if remaining > 0:
                ach_text += f" *(+{remaining} more)*"
            embed.add_field(name=f"🏅 Achievements ({len(unlocked)})", value=ach_text, inline=False)
        else:
            embed.add_field(name="🏅 Achievements", value="None yet — keep being active!", inline=False)

        embed.set_footer(text=f"User ID: {target.id}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="achievements", description="View all achievements and which ones you've unlocked")
    @app_commands.describe(user="User to check (default: yourself)")
    async def achievements(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        target = user or interaction.user
        unlocked = self.db.get_unlocked(interaction.guild.id, target.id)

        embed = discord.Embed(
            title=f"🏅  Achievements — {target.display_name}",
            description=f"Unlocked **{len(unlocked)}/{len(ALL_ACHIEVEMENTS)}** achievements",
            color=C.GOLD
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        for key, ach in ALL_ACHIEVEMENTS.items():
            if key in unlocked:
                dt = datetime.datetime.fromisoformat(unlocked[key])
                val = f"✅ Unlocked <t:{int(dt.timestamp())}:R>"
            else:
                val = "🔒 Locked"
            embed.add_field(
                name=f"{ach['emoji']}  {ach['name']}",
                value=f"*{ach['desc']}*\n{val}",
                inline=True
            )
        embed.set_footer(text=f"{BOT_NAME} Achievements")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="View the server leaderboard")
    @app_commands.describe(category="What to rank by")
    @app_commands.choices(category=[
        app_commands.Choice(name="💰 Coins (Economy)",   value="coins"),
        app_commands.Choice(name="🎙️ Voice XP",          value="voice"),
        app_commands.Choice(name="💬 Chat Messages",      value="chat"),
        app_commands.Choice(name="🏅 Achievements",       value="achievements"),
    ])
    async def leaderboard(self, interaction: discord.Interaction, category: str = "coins") -> None:
        await interaction.response.defer()
        guild = interaction.guild

        if category == "coins":
            eco_cog = self._safe_get("EconomyCog")
            if not eco_cog:
                await interaction.followup.send(embed=embed_error("Economy system is offline."), ephemeral=True)
                return
            lb = eco_cog.db.get_leaderboard(guild.id, limit=100)
            def fmt(i: int, row: dict) -> str:
                total = row["wallet"] + row["bank"]
                return f"**{i}.** <@{row['user_id']}> — 🪙 **{total:,}**"
            title = "🏆  Economy Leaderboard"

        elif category == "voice":
            voice_cog = self._safe_get("VoiceAnalyticsCog")
            if not voice_cog:
                await interaction.followup.send(embed=embed_error("Voice system is offline."), ephemeral=True)
                return
            lb = voice_cog.db.get_leaderboard(guild.id, sort_by="xp", limit=100)
            def fmt(i: int, row: dict) -> str:
                hours, mins = divmod(row["total_minutes"], 60)
                return f"**{i}.** <@{row['user_id']}> — ⭐ **{row['xp']:,}** XP | {hours}h {mins}m"
            title = "🏆  Voice XP Leaderboard"

        elif category == "chat":
            activity_cog = self._safe_get("ServerActivityCog")
            if not activity_cog:
                await interaction.followup.send(embed=embed_error("Activity system is offline."), ephemeral=True)
                return
            lb = activity_cog.db.get_text_leaderboard(guild.id, sort_by="messages", limit=100)
            def fmt(i: int, row: dict) -> str:
                return f"**{i}.** <@{row['user_id']}> — 💬 **{row['total_messages']:,}** messages"
            title = "🏆  Chat Leaderboard"

        elif category == "achievements":
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                lb = conn.execute("""
                    SELECT user_id, COUNT(*) as total FROM achievements
                    WHERE guild_id=? GROUP BY user_id ORDER BY total DESC LIMIT 100
                """, (str(guild.id),)).fetchall()
            def fmt(i: int, row: dict) -> str:
                return f"**{i}.** <@{row['user_id']}> — 🏅 **{row['total']}** achievements"
            title = "🏆  Achievements Leaderboard"

        if not lb:
            await interaction.followup.send(embed=embed_info("Leaderboard Empty", "No data yet for this category."), ephemeral=True)
            return

        pages = paginate_leaderboard(title, lb, fmt, color=C.GOLD, footer=f"{BOT_NAME} Leaderboard • {guild.name}")
        await interaction.followup.send(embed=pages[0], view=Paginator(pages, interaction.user.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfilesCog(bot))
