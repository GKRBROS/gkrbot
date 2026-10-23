"""
leveling.py — Leveling and XP System for GKR Bot.
Features:
  • Configurable XP multiplier (1.0x - 5.0x)
  • In-memory runtime cache for zero-overhead message processing
  • Rank cards with customizable background URL
  • Stackable role rewards
  • Channel blacklist grid
  • Safe Discord event handling
"""

from __future__ import annotations

import os
import json
import time
import math
import sqlite3
from typing import Optional, Dict, List, Any

import discord
from discord import app_commands
from discord.ext import commands

from gkr_ui import C, BOT_NAME, embed_success, embed_info, embed_warning

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leveling.sqlite3")

class LevelingDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leveling_config (
                    guild_id TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    xp_multiplier REAL DEFAULT 1.0,
                    card_background_url TEXT DEFAULT '',
                    stack_rewards INTEGER DEFAULT 1,
                    announce_channel_id TEXT DEFAULT NULL,
                    announce_message TEXT DEFAULT 'Congratulations {user}, you leveled up to **Level {level}**!',
                    channel_blacklist TEXT DEFAULT '[]'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS level_rewards (
                    guild_id TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY(guild_id, level)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_xp (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    last_xp_time REAL DEFAULT 0,
                    PRIMARY KEY(guild_id, user_id)
                )
            """)
            conn.commit()

    def get_config(self, guild_id: int) -> Dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM leveling_config WHERE guild_id=?", (str(guild_id),)).fetchone()
            if not row:
                return {
                    "enabled": 1,
                    "xp_multiplier": 1.0,
                    "card_background_url": "",
                    "stack_rewards": 1,
                    "announce_channel_id": None,
                    "announce_message": "Congratulations {user}, you leveled up to **Level {level}**!",
                    "channel_blacklist": []
                }
            data = dict(row)
            try:
                data["channel_blacklist"] = json.loads(data.get("channel_blacklist") or "[]")
            except Exception:
                data["channel_blacklist"] = []
            return data

    def set_config(self, guild_id: int, config: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO leveling_config (
                    guild_id, enabled, xp_multiplier, card_background_url,
                    stack_rewards, announce_channel_id, announce_message, channel_blacklist
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    xp_multiplier=excluded.xp_multiplier,
                    card_background_url=excluded.card_background_url,
                    stack_rewards=excluded.stack_rewards,
                    announce_channel_id=excluded.announce_channel_id,
                    announce_message=excluded.announce_message,
                    channel_blacklist=excluded.channel_blacklist
            """, (
                str(guild_id),
                int(config.get("enabled", 1)),
                float(config.get("xp_multiplier", 1.0)),
                str(config.get("card_background_url", "")),
                int(config.get("stack_rewards", 1)),
                str(config.get("announce_channel_id") or "") or None,
                str(config.get("announce_message", "Congratulations {user}, you leveled up to **Level {level}**!")),
                json.dumps(config.get("channel_blacklist", []))
            ))
            conn.commit()

    def get_rewards(self, guild_id: int) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT level, role_id FROM level_rewards WHERE guild_id=? ORDER BY level ASC",
                (str(guild_id),)
            ).fetchall()
        return [{"level": r["level"], "role_id": r["role_id"]} for r in rows]

    def set_reward(self, guild_id: int, level: int, role_id: int) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO level_rewards (guild_id, level, role_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, level) DO UPDATE SET role_id=excluded.role_id
            """, (str(guild_id), level, str(role_id)))
            conn.commit()

    def delete_reward(self, guild_id: int, level: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM level_rewards WHERE guild_id=? AND level=?",
                (str(guild_id), level)
            )
            conn.commit()
        return cur.rowcount > 0

    def get_user_xp(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT xp, level FROM user_xp WHERE guild_id=? AND user_id=?",
                (str(guild_id), str(user_id))
            ).fetchone()
        if not row:
            return {"xp": 0, "level": 0}
        return {"xp": row["xp"], "level": row["level"]}

    def add_xp(self, guild_id: int, user_id: int, xp_to_add: int) -> Dict[str, Any]:
        """Add XP and return dict with new_xp, old_level, new_level, leveled_up boolean."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT xp, level, last_xp_time FROM user_xp WHERE guild_id=? AND user_id=?",
                (str(guild_id), str(user_id))
            ).fetchone()
            now = time.time()
            if row:
                old_xp = row["xp"]
                old_level = row["level"]
                last_time = row["last_xp_time"]
            else:
                old_xp = 0
                old_level = 0
                last_time = 0

            # 60s cooldown per XP award
            if now - last_time < 50:
                return {"leveled_up": False, "level": old_level, "xp": old_xp}

            new_xp = old_xp + xp_to_add
            # XP formula: level = floor(0.1 * sqrt(xp))
            new_level = int(0.1 * math.sqrt(new_xp))

            conn.execute("""
                INSERT INTO user_xp (guild_id, user_id, xp, level, last_xp_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    xp=excluded.xp,
                    level=excluded.level,
                    last_xp_time=excluded.last_xp_time
            """, (str(guild_id), str(user_id), new_xp, new_level, now))
            conn.commit()

            return {
                "leveled_up": new_level > old_level,
                "old_level": old_level,
                "new_level": new_level,
                "xp": new_xp
            }


class LevelingCog(commands.Cog, name="Leveling"):
    """Leveling & XP Engine with cache-synchronized runtime configuration."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = LevelingDatabase()
        self.db.initialize()
        # In-memory runtime cache: guild_id -> dict
        self._cache: Dict[int, Dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Preload active server configurations into memory for zero SQL overhead on messages."""
        try:
            with self.db._conn() as conn:
                rows = conn.execute("SELECT * FROM leveling_config").fetchall()
                for r in rows:
                    g_id = int(r["guild_id"])
                    d = dict(r)
                    try:
                        d["channel_blacklist"] = set(json.loads(d.get("channel_blacklist") or "[]"))
                    except Exception:
                        d["channel_blacklist"] = set()
                    self._cache[g_id] = d
        except Exception as e:
            print(f"[Leveling] Failed to preload cache: {e}")

    def invalidate_cache(self, guild_id: int) -> None:
        """Syncs database changes immediately into bot runtime memory."""
        cfg = self.db.get_config(guild_id)
        self._cache[guild_id] = {
            "enabled": cfg.get("enabled", 1),
            "xp_multiplier": cfg.get("xp_multiplier", 1.0),
            "card_background_url": cfg.get("card_background_url", ""),
            "stack_rewards": cfg.get("stack_rewards", 1),
            "announce_channel_id": cfg.get("announce_channel_id"),
            "announce_message": cfg.get("announce_message"),
            "channel_blacklist": set(cfg.get("channel_blacklist", []))
        }

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        g_id = message.guild.id
        cfg = self._cache.get(g_id)
        if not cfg:
            # First time in guild: load and cache
            self.invalidate_cache(g_id)
            cfg = self._cache.get(g_id, {})

        if not cfg.get("enabled", 1):
            return

        # Check channel blacklist
        if str(message.channel.id) in cfg.get("channel_blacklist", set()):
            return

        multiplier = float(cfg.get("xp_multiplier", 1.0))
        base_xp = 15
        xp_gain = max(1, int(base_xp * multiplier))

        result = self.db.add_xp(g_id, message.author.id, xp_gain)
        if result.get("leveled_up"):
            await self._handle_level_up(message.guild, message.author, result["new_level"], cfg)

    async def _handle_level_up(
        self,
        guild: discord.Guild,
        member: discord.Member,
        new_level: int,
        cfg: Dict[str, Any]
    ) -> None:
        # Check and grant level rewards
        rewards = self.db.get_rewards(guild.id)
        stack_rewards = bool(cfg.get("stack_rewards", 1))

        eligible_roles = []
        obsolete_roles = []
        for r in rewards:
            role = guild.get_role(int(r["role_id"]))
            if not role:
                continue
            if r["level"] <= new_level:
                if stack_rewards:
                    eligible_roles.append(role)
                else:
                    eligible_roles = [role] # Only highest
            else:
                obsolete_roles.append(role)

        try:
            bot_top = guild.me.top_role.position if guild.me else 0
            for role in eligible_roles:
                if role.position < bot_top and role not in member.roles:
                    await member.add_roles(role, reason=f"Level {new_level} reached")
            if not stack_rewards:
                for role in obsolete_roles:
                    if role.position < bot_top and role in member.roles:
                        await member.remove_roles(role, reason="Stackable rewards disabled (replaced by higher rank)")
        except Exception as e:
            print(f"[Leveling] Failed to update roles for {member}: {e}")

        # Send announcement
        announce_ch_id = cfg.get("announce_channel_id")
        target_ch = guild.get_channel(int(announce_ch_id)) if announce_ch_id else message.channel
        if target_ch and target_ch.permissions_for(guild.me).send_messages:
            msg_template = cfg.get("announce_message") or "Congratulations {user}, you leveled up to **Level {level}**!"
            msg_text = msg_template.replace("{user}", member.mention).replace("{level}", str(new_level))
            embed = embed_success(title="Level Up!", description=msg_text)
            try:
                await target_ch.send(embed=embed)
            except Exception:
                pass

    @app_commands.command(name="rank", description="Check your current level and XP rank")
    async def rank(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        g_id = interaction.guild_id
        stats = self.db.get_user_xp(g_id, target.id)
        cfg = self.db.get_config(g_id)

        current_xp = stats["xp"]
        current_lvl = stats["level"]
        next_lvl_xp = int(((current_lvl + 1) / 0.1) ** 2)

        embed = embed_info(
            title=f"Rank Card — {target.display_name}",
            description=f"**Level**: `{current_lvl}`\n**Total XP**: `{current_xp:,}` / `{next_lvl_xp:,}`"
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        if cfg.get("card_background_url"):
            embed.set_image(url=cfg["card_background_url"])

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    cog = LevelingCog(bot)
    await bot.add_cog(cog)
