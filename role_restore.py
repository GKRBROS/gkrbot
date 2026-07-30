"""
role_restore.py – Role Restore System for GKR Bot.

When a member leaves and rejoins the server, they automatically get back
all the roles they had before (as long as those roles still exist).

Commands (admin only):
  /rolerestore toggle  – Enable/disable the system for this server
  /rolerestore status  – Show current settings
"""

import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "role_restore.sqlite3")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class RoleRestoreDB:
    def __init__(self):
        self._init()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id    TEXT PRIMARY KEY,
                    enabled     INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saved_roles (
                    guild_id    TEXT NOT NULL,
                    user_id     TEXT NOT NULL,
                    role_ids    TEXT NOT NULL,
                    left_at     TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            conn.commit()

    # ── Settings ──────────────────────────────────────────────────────────────

    def is_enabled(self, guild_id: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT enabled FROM guild_settings WHERE guild_id = ?",
                (str(guild_id),)
            ).fetchone()
        return bool(row["enabled"]) if row else True  # default enabled

    def set_enabled(self, guild_id: int, enabled: bool):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, enabled) VALUES (?, ?)",
                (str(guild_id), 1 if enabled else 0)
            )
            conn.commit()

    # ── Role Storage ──────────────────────────────────────────────────────────

    def save_roles(self, guild_id: int, user_id: int, role_ids: list[int]):
        role_str = ",".join(str(r) for r in role_ids)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO saved_roles (guild_id, user_id, role_ids, left_at) VALUES (?, ?, ?, ?)",
                (str(guild_id), str(user_id), role_str, datetime.datetime.utcnow().isoformat())
            )
            conn.commit()

    def get_roles(self, guild_id: int, user_id: int) -> list[int]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT role_ids FROM saved_roles WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id))
            ).fetchone()
        if not row or not row["role_ids"]:
            return []
        return [int(r) for r in row["role_ids"].split(",") if r]

    def delete_saved(self, guild_id: int, user_id: int):
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM saved_roles WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id))
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class RoleRestoreCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = RoleRestoreDB()

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Save member's roles when they leave."""
        if not self.db.is_enabled(member.guild.id):
            return

        # Save all roles except @everyone and managed (bot/integration) roles
        role_ids = [
            r.id for r in member.roles
            if not r.is_default() and not r.managed
        ]
        if role_ids:
            self.db.save_roles(member.guild.id, member.id, role_ids)
            print(f"[RoleRestore] Saved {len(role_ids)} roles for {member.name} in {member.guild.name}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Restore saved roles when a member rejoins."""
        if not self.db.is_enabled(member.guild.id):
            return

        saved_ids = self.db.get_roles(member.guild.id, member.id)
        if not saved_ids:
            return

        guild = member.guild
        roles_to_restore = []
        missing = []

        for role_id in saved_ids:
            role = guild.get_role(role_id)
            if role and not role.managed and role < guild.me.top_role:
                roles_to_restore.append(role)
            else:
                missing.append(str(role_id))

        if roles_to_restore:
            try:
                await member.add_roles(*roles_to_restore, reason="Role Restore: member rejoined")
                print(f"[RoleRestore] ✅ Restored {len(roles_to_restore)} roles for {member.name} in {guild.name}")
            except discord.Forbidden:
                print(f"[RoleRestore] ❌ Missing permissions to restore roles for {member.name}")
            except Exception as e:
                print(f"[RoleRestore] ❌ Error restoring roles for {member.name}: {e}")

        # Clean up saved data after restore
        self.db.delete_saved(member.guild.id, member.id)

    # ── Slash Commands ────────────────────────────────────────────────────────

    restore_group = app_commands.Group(
        name="rolerestore",
        description="Manage the Role Restore system"
    )

    @restore_group.command(name="toggle", description="Enable or disable role restore when members rejoin")
    @app_commands.default_permissions(manage_guild=True)
    async def toggle(self, interaction: discord.Interaction):
        current = self.db.is_enabled(interaction.guild.id)
        new_state = not current
        self.db.set_enabled(interaction.guild.id, new_state)
        status = "✅ **Enabled**" if new_state else "❌ **Disabled**"
        embed = discord.Embed(
            title="🔄 Role Restore",
            description=f"Role Restore is now {status}.\n\n"
                        f"{'Members who rejoin will automatically get their old roles back!' if new_state else 'Rejoining members will not get their roles back.'}",
            color=0x2ECC71 if new_state else 0xE74C3C,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @restore_group.command(name="status", description="Show the current Role Restore configuration")
    @app_commands.default_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction):
        enabled = self.db.is_enabled(interaction.guild.id)
        embed = discord.Embed(
            title="🔄 Role Restore Status",
            color=0x2ECC71 if enabled else 0x95A5A6,
        )
        embed.add_field(name="System", value="✅ Enabled" if enabled else "❌ Disabled", inline=True)
        embed.add_field(
            name="How it works",
            value="When a member leaves, their roles are saved.\nWhen they rejoin, those roles are automatically restored.",
            inline=False
        )
        embed.add_field(
            name="Note",
            value="Roles higher than the bot's top role and bot-managed roles cannot be restored.",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RoleRestoreCog(bot))
    print("🔄 Role Restore system loaded!")
