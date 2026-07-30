"""
role_sync.py — Cross-server role synchronisation.

Admins can link a role in Server A to a role in Server B.
When a user who has the source role in Server A joins Server B
(where the bot is also present), they automatically receive the
target role in Server B.

All configuration is per-guild and stored in role_sync.sqlite3.
"""

from __future__ import annotations

import sqlite3
import os
import json

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "role_sync.sqlite3")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class RoleSyncDB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS role_sync_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_guild_id TEXT NOT NULL,
                    source_guild_id TEXT NOT NULL,
                    source_role_id  TEXT NOT NULL,
                    target_role_id  TEXT NOT NULL,
                    UNIQUE(target_guild_id, source_guild_id, source_role_id, target_role_id)
                )
            """)
            c.commit()

    def add_rule(self, target_guild: int, source_guild: int, source_role: int, target_role: int) -> None:
        with self._conn() as c:
            c.execute("""
                INSERT OR IGNORE INTO role_sync_rules
                (target_guild_id, source_guild_id, source_role_id, target_role_id)
                VALUES (?,?,?,?)
            """, (str(target_guild), str(source_guild), str(source_role), str(target_role)))
            c.commit()

    def remove_rule(self, rule_id: int, target_guild: int) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "DELETE FROM role_sync_rules WHERE id=? AND target_guild_id=?",
                (rule_id, str(target_guild))
            )
            c.commit()
            return cur.rowcount > 0

    def get_rules_for_target(self, target_guild: int) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute(
                "SELECT * FROM role_sync_rules WHERE target_guild_id=?",
                (str(target_guild),)
            ).fetchall()

    def get_all_rules(self) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute("SELECT * FROM role_sync_rules").fetchall()


# ---------------------------------------------------------------------------
# Interactive UI
# ---------------------------------------------------------------------------

class RoleSyncSetupModal(discord.ui.Modal, title="Role Sync — Source Server"):
    source_guild_id = discord.ui.TextInput(
        label="Source Server ID",
        placeholder="e.g. 123456789012345678  (the server to copy the role FROM)",
        required=True,
        min_length=15,
        max_length=22,
    )

    def __init__(self, cog: "RoleSyncCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        src_id = self.source_guild_id.value.strip()
        if not src_id.isdigit():
            await interaction.response.send_message("❌ Server ID must be a number.", ephemeral=True)
            return

        source_guild = interaction.client.get_guild(int(src_id))
        if not source_guild:
            await interaction.response.send_message(
                "❌ I'm not in that server, or the ID is wrong. Make sure the bot is a member of the source server.",
                ephemeral=True,
            )
            return

        # Get all roles from source guild for the select menu
        roles = [r for r in source_guild.roles if not r.is_default() and not r.managed]
        if not roles:
            await interaction.response.send_message("❌ No usable roles found in the source server.", ephemeral=True)
            return

        view = RoleSyncStep2View(self.cog, interaction.guild, source_guild, roles)
        embed = discord.Embed(
            title="⚙️ Role Sync Setup — Step 2",
            description=(
                f"**Source Server**: `{source_guild.name}`\n\n"
                "Now select:\n"
                "1. The **Source Role** (role the user must have in the source server)\n"
                "2. The **Target Role** (role they will receive in **this** server)"
            ),
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class RoleSyncStep2View(discord.ui.View):
    def __init__(
        self,
        cog: "RoleSyncCog",
        target_guild: discord.Guild,
        source_guild: discord.Guild,
        source_roles: list[discord.Role],
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.target_guild = target_guild
        self.source_guild = source_guild
        self.selected_source_role: Optional[int] = None
        self.selected_target_role: Optional[int] = None

        # Source role select (from the source guild — we must build manually, RoleSelect only works for current guild)
        options = [
            discord.SelectOption(label=r.name[:100], value=str(r.id), emoji="🔵")
            for r in source_roles[:25]
        ]
        src_select = discord.ui.Select(
            placeholder="Select Source Role (from the other server)",
            options=options,
            row=0,
        )
        src_select.callback = self._on_source_role
        self.add_item(src_select)

        # Target role select uses native RoleSelect for current guild
        tgt_select = discord.ui.RoleSelect(
            placeholder="Select Target Role (to grant in THIS server)",
            min_values=1,
            max_values=1,
            row=1,
        )
        tgt_select.callback = self._on_target_role
        self.add_item(tgt_select)

        # Save button
        save_btn = discord.ui.Button(label="✅ Save Rule", style=discord.ButtonStyle.success, row=2)
        save_btn.callback = self._save
        self.add_item(save_btn)

    async def _on_source_role(self, interaction: discord.Interaction) -> None:
        self.selected_source_role = int(interaction.data["values"][0])
        await interaction.response.send_message("✅ Source role selected.", ephemeral=True)

    async def _on_target_role(self, interaction: discord.Interaction) -> None:
        self.selected_target_role = int(interaction.data["values"][0])
        await interaction.response.send_message("✅ Target role selected.", ephemeral=True)

    async def _save(self, interaction: discord.Interaction) -> None:
        if not self.selected_source_role or not self.selected_target_role:
            await interaction.response.send_message(
                "❌ Please select both a source role and a target role first.", ephemeral=True
            )
            return

        self.cog.db.add_rule(
            self.target_guild.id,
            self.source_guild.id,
            self.selected_source_role,
            self.selected_target_role,
        )

        src_role_name = self.source_guild.get_role(self.selected_source_role)
        tgt_role = self.target_guild.get_role(self.selected_target_role)
        src_name = src_role_name.name if src_role_name else self.selected_source_role
        tgt_name = tgt_role.mention if tgt_role else self.selected_target_role

        embed = discord.Embed(
            title="✅ Role Sync Rule Saved",
            description=(
                f"**Source Server**: `{self.source_guild.name}`\n"
                f"**Source Role**: `{src_name}`\n"
                f"**→ Target Role**: {tgt_name}\n\n"
                "When a member with the source role joins this server, they'll automatically receive the target role."
            ),
            color=0x57F287,
        )
        await interaction.response.edit_message(embed=embed, view=None)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class RoleSyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = RoleSyncDB()

    sync_group = app_commands.Group(name="rolesync", description="Cross-server role sync commands")

    @sync_group.command(name="setup", description="Add a cross-server role sync rule interactively")
    @app_commands.default_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RoleSyncSetupModal(self))

    @sync_group.command(name="list", description="List all role sync rules for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def list_rules(self, interaction: discord.Interaction) -> None:
        rules = self.db.get_rules_for_target(interaction.guild.id)
        if not rules:
            await interaction.response.send_message("No role sync rules configured for this server.", ephemeral=True)
            return

        lines = []
        for r in rules:
            src_guild = self.bot.get_guild(int(r["source_guild_id"]))
            src_guild_name = src_guild.name if src_guild else f"`{r['source_guild_id']}`"
            src_role = src_guild.get_role(int(r["source_role_id"])) if src_guild else None
            tgt_role = interaction.guild.get_role(int(r["target_role_id"]))
            src_name = src_role.name if src_role else r["source_role_id"]
            tgt_name = tgt_role.mention if tgt_role else r["target_role_id"]
            lines.append(f"`ID {r['id']}` — **{src_guild_name}** / `{src_name}` → {tgt_name}")

        embed = discord.Embed(
            title="🔄 Role Sync Rules",
            description="\n".join(lines),
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @sync_group.command(name="remove", description="Remove a role sync rule by its ID")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(rule_id="The rule ID shown in /rolesync list")
    async def remove_rule(self, interaction: discord.Interaction, rule_id: int) -> None:
        success = self.db.remove_rule(rule_id, interaction.guild.id)
        if success:
            await interaction.response.send_message(f"✅ Rule `{rule_id}` removed.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Rule not found.", ephemeral=True)

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """When a member joins, check all sync rules for this guild and apply matching roles."""
        rules = self.db.get_rules_for_target(member.guild.id)
        if not rules:
            return

        for rule in rules:
            source_guild = self.bot.get_guild(int(rule["source_guild_id"]))
            if not source_guild:
                continue

            # Check if the user is in the source guild and has the source role
            source_member = source_guild.get_member(member.id)
            if not source_member:
                continue

            source_role_id = int(rule["source_role_id"])
            if not any(r.id == source_role_id for r in source_member.roles):
                continue

            # Give the target role
            target_role = member.guild.get_role(int(rule["target_role_id"]))
            if not target_role:
                continue

            try:
                await member.add_roles(target_role, reason=f"Role Sync from {source_guild.name}")
                print(f"[RoleSync] Gave {member} the role '{target_role.name}' in {member.guild.name} (synced from {source_guild.name})")
            except discord.Forbidden:
                print(f"[RoleSync] Missing permission to assign role '{target_role.name}' in {member.guild.name}")
            except Exception as exc:
                print(f"[RoleSync] Error: {exc}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleSyncCog(bot))
    print("🔄 Role Sync loaded!")
