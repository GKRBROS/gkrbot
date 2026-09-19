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
from gkr_ui import embed_success, embed_error, embed_info, C
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

PAGE_SIZE = 25  # Discord's hard cap on select menu options


class GuildPickerView(discord.ui.View):
    """Step 1: pick the source server from a dropdown instead of pasting an ID.

    Paginated because a bot in more than 25 servers can't fit them all in
    one select menu — Discord's own limit, not something we can raise.
    """

    def __init__(self, cog: "RoleSyncCog", invoking_guild: discord.Guild):
        super().__init__(timeout=180)
        self.cog = cog
        self.invoking_guild = invoking_guild
        self.guilds = sorted(
            (g for g in cog.bot.guilds if g.id != invoking_guild.id),
            key=lambda g: g.name.lower(),
        )
        self.page = 0
        self._build()

    @property
    def max_page(self) -> int:
        return max(0, (len(self.guilds) - 1) // PAGE_SIZE)

    def _build(self) -> None:
        self.clear_items()
        start = self.page * PAGE_SIZE
        chunk = self.guilds[start:start + PAGE_SIZE]

        if not chunk:
            select = discord.ui.Select(
                placeholder="I'm not in any other servers yet",
                options=[discord.SelectOption(label="No servers available", value="none")],
                disabled=True,
                row=0,
            )
            self.add_item(select)
            return

        options = [
            discord.SelectOption(label=g.name[:100], description=f"ID: {g.id}", value=str(g.id))
            for g in chunk
        ]
        select = discord.ui.Select(
            placeholder=f"Select source server — page {self.page + 1}/{self.max_page + 1}",
            options=options,
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

        if self.max_page > 0:
            prev_btn = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary, disabled=(self.page == 0), row=1)
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, disabled=(self.page >= self.max_page), row=1)
            prev_btn.callback = self._prev
            next_btn.callback = self._next
            self.add_item(prev_btn)
            self.add_item(next_btn)

    async def _prev(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        self._build()
        await interaction.response.edit_message(view=self)

    async def _next(self, interaction: discord.Interaction) -> None:
        self.page = min(self.max_page, self.page + 1)
        self._build()
        await interaction.response.edit_message(view=self)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.data["values"][0]
        if guild_id == "none":
            return

        source_guild = self.cog.bot.get_guild(int(guild_id))
        if not source_guild:
            await interaction.response.send_message("❌ That server is no longer available.", ephemeral=True)
            return

        roles = [r for r in source_guild.roles if not r.is_default() and not r.managed]
        if not roles:
            await interaction.response.send_message("❌ No usable roles found in that server.", ephemeral=True)
            return

        view = RoleSyncStep2View(self.cog, interaction.guild, source_guild, roles)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class RoleSyncStep2View(discord.ui.View):
    """Step 2: pick the source role and target role. Both role lists are
    paginated (25 per page) so servers with more than 25 roles are fully
    reachable instead of silently cutting off after the first 25."""

    def __init__(
        self,
        cog: "RoleSyncCog",
        target_guild: discord.Guild,
        source_guild: discord.Guild,
        source_roles: list[discord.Role],
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.target_guild = target_guild
        self.source_guild = source_guild
        # Highest role first — the roles people actually look for tend to be
        # nearer the top rather than buried at the very bottom of the list.
        self.source_roles = sorted(source_roles, key=lambda r: r.position, reverse=True)
        self.role_page = 0

        self.selected_source_role: Optional[int] = None
        self.selected_source_role_name: Optional[str] = None
        self.selected_target_role: Optional[int] = None
        self.selected_target_role_name: Optional[str] = None

        self._build()

    @property
    def max_role_page(self) -> int:
        return max(0, (len(self.source_roles) - 1) // PAGE_SIZE)

    def build_embed(self) -> discord.Embed:
        src_status = f"✅ `{self.selected_source_role_name}`" if self.selected_source_role_name else "*not selected yet*"
        tgt_status = f"✅ {self.selected_target_role_name}" if self.selected_target_role_name else "*not selected yet*"
        return discord.Embed(
            title="⚙️ Role Sync Setup — Step 2",
            description=(
                f"**Source Server**: `{self.source_guild.name}`\n\n"
                f"**Source Role** (from `{self.source_guild.name}`): {src_status}\n"
                f"**Target Role** (granted in **this** server): {tgt_status}\n\n"
                f"This server has **{len(self.source_roles)}** usable roles"
                + (f", shown {PAGE_SIZE} at a time — use Prev/Next to page through all of them." if len(self.source_roles) > PAGE_SIZE else ".")
            ),
            color=0x3498DB,
        )

    def _build(self) -> None:
        self.clear_items()
        start = self.role_page * PAGE_SIZE
        chunk = self.source_roles[start:start + PAGE_SIZE]

        options = [
            discord.SelectOption(
                label=r.name[:100],
                value=str(r.id),
                emoji="🔵",
                default=(self.selected_source_role == r.id),
            )
            for r in chunk
        ]
        src_select = discord.ui.Select(
            placeholder=f"Source role — page {self.role_page + 1}/{self.max_role_page + 1}",
            options=options,
            row=0,
        )
        src_select.callback = self._on_source_role
        self.add_item(src_select)

        if self.max_role_page > 0:
            prev_btn = discord.ui.Button(label="◀ Prev Roles", style=discord.ButtonStyle.secondary, disabled=(self.role_page == 0), row=1)
            next_btn = discord.ui.Button(label="Next Roles ▶", style=discord.ButtonStyle.secondary, disabled=(self.role_page >= self.max_role_page), row=1)
            prev_btn.callback = self._prev_roles
            next_btn.callback = self._next_roles
            self.add_item(prev_btn)
            self.add_item(next_btn)

        # Target role uses native RoleSelect since it's always the current
        # guild, which discord.py can populate natively without our own
        # pagination — Discord itself handles large role lists here.
        tgt_select = discord.ui.RoleSelect(
            placeholder="Select Target Role (to grant in THIS server)",
            min_values=1,
            max_values=1,
            row=2,
        )
        tgt_select.callback = self._on_target_role
        self.add_item(tgt_select)

        save_btn = discord.ui.Button(label="✅ Save Rule", style=discord.ButtonStyle.success, row=3)
        save_btn.callback = self._save
        self.add_item(save_btn)

    async def _prev_roles(self, interaction: discord.Interaction) -> None:
        self.role_page = max(0, self.role_page - 1)
        self._build()
        await interaction.response.edit_message(view=self)

    async def _next_roles(self, interaction: discord.Interaction) -> None:
        self.role_page = min(self.max_role_page, self.role_page + 1)
        self._build()
        await interaction.response.edit_message(view=self)

    async def _on_source_role(self, interaction: discord.Interaction) -> None:
        role_id = int(interaction.data["values"][0])
        self.selected_source_role = role_id
        role_obj = self.source_guild.get_role(role_id)
        self.selected_source_role_name = role_obj.name if role_obj else str(role_id)
        self._build()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_target_role(self, interaction: discord.Interaction) -> None:
        role_id = int(interaction.data["values"][0])
        self.selected_target_role = role_id
        role_obj = self.target_guild.get_role(role_id)
        self.selected_target_role_name = role_obj.mention if role_obj else str(role_id)
        self._build()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

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

        checking_embed = discord.Embed(
            title="✅ Role Sync Rule Saved",
            description=(
                f"**Source Server**: `{self.source_guild.name}`\n"
                f"**Source Role**: `{self.selected_source_role_name}`\n"
                f"**→ Target Role**: {self.selected_target_role_name}\n\n"
                "🔄 Checking for existing members who already qualify..."
            ),
            color=0x57F287,
        )
        await interaction.response.edit_message(embed=checking_embed, view=None)

        # Backfill: apply the rule right now to anyone who already has the
        # source role and is already a member of this server, instead of
        # only catching them on their next join or next role change.
        synced, qualifying = await self.cog.backfill_rule(
            self.target_guild, self.source_guild, self.selected_source_role, self.selected_target_role
        )

        embed = discord.Embed(
            title="✅ Role Sync Rule Saved",
            description=(
                f"**Source Server**: `{self.source_guild.name}`\n"
                f"**Source Role**: `{self.selected_source_role_name}`\n"
                f"**→ Target Role**: {self.selected_target_role_name}\n\n"
                f"**Backfilled {synced} existing member(s)** who already had the source role and "
                f"were already in this server ({qualifying} qualifying member(s) checked in total).\n\n"
                "Going forward, this also applies automatically whenever someone joins this server "
                "or receives the source role in the source server."
            ),
            color=0x57F287,
        )
        try:
            await interaction.edit_original_response(embed=embed, view=None)
        except Exception as exc:
            print(f"[RoleSync] Could not update setup confirmation message: {exc}")


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
        view = GuildPickerView(self, interaction.guild)
        if not view.guilds:
            await interaction.response.send_message(
                "❌ I'm not in any other servers yet — invite me to the source server first.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title="⚙️ Role Sync Setup — Step 1",
            description="Select the **source server** — the server that already has the role you want to copy from.",
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

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

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _get_member_safe(self, guild: discord.Guild, user_id: int) -> Optional[discord.Member]:
        """guild.get_member() only checks Discord.py's local member cache and
        silently returns None if that member simply isn't cached yet — a
        common cause of role sync appearing to "not work" even though the
        person genuinely is in that server. Falls back to a real API fetch."""
        member = guild.get_member(user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(user_id)
        except (discord.NotFound, discord.HTTPException):
            return None

    async def backfill_rule(
        self,
        target_guild: discord.Guild,
        source_guild: discord.Guild,
        source_role_id: int,
        target_role_id: int,
    ) -> tuple[int, int]:
        """Apply a newly-saved rule immediately to anyone who already
        qualifies right now, instead of making them wait for their next
        join or their next role change to get synced.

        Returns (synced_count, qualifying_count).
        """
        target_role = target_guild.get_role(target_role_id)
        if not target_role:
            return 0, 0

        synced = 0
        qualifying = 0
        try:
            async for member in source_guild.fetch_members(limit=None):
                if not any(r.id == source_role_id for r in member.roles):
                    continue
                qualifying += 1

                target_member = await self._get_member_safe(target_guild, member.id)
                if not target_member or target_role in target_member.roles:
                    continue

                try:
                    await target_member.add_roles(target_role, reason=f"Role Sync backfill from {source_guild.name}")
                    synced += 1
                except discord.Forbidden:
                    print(f"[RoleSync] Missing permission to assign role '{target_role.name}' in {target_guild.name}")
                except Exception as exc:
                    print(f"[RoleSync] Backfill error for {member}: {exc}")
        except discord.Forbidden:
            print(f"[RoleSync] Missing permission to list members of {source_guild.name} for backfill")
        except Exception as exc:
            print(f"[RoleSync] Backfill fetch error: {exc}")

        return synced, qualifying

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
            source_member = await self._get_member_safe(source_guild, member.id)
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

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """LIVE sync: on_member_join alone only catches the role at the exact
        moment someone joins the target server. If a member is already in
        BOTH servers and only receives the source role afterward, nothing
        was ever pushing that role over — this is what actually closes that
        gap, watching for role changes in any server used as a sync SOURCE
        and immediately applying the target role wherever the member is
        already present."""
        if before.roles == after.roles:
            return
        gained = {r.id for r in after.roles} - {r.id for r in before.roles}
        if not gained:
            return

        rules = self.db.get_all_rules()
        relevant = [
            r for r in rules
            if int(r["source_guild_id"]) == after.guild.id and int(r["source_role_id"]) in gained
        ]
        if not relevant:
            return

        for rule in relevant:
            target_guild = self.bot.get_guild(int(rule["target_guild_id"]))
            if not target_guild:
                continue

            target_member = await self._get_member_safe(target_guild, after.id)
            if not target_member:
                continue  # not (yet) in the target server — on_member_join covers that case

            target_role = target_guild.get_role(int(rule["target_role_id"]))
            if not target_role or target_role in target_member.roles:
                continue

            try:
                await target_member.add_roles(target_role, reason=f"Role Sync from {after.guild.name}")
                print(f"[RoleSync] Live-synced role '{target_role.name}' to {target_member} in {target_guild.name} (from {after.guild.name})")
            except discord.Forbidden:
                print(f"[RoleSync] Missing permission to assign role '{target_role.name}' in {target_guild.name}")
            except Exception as exc:
                print(f"[RoleSync] Error during live sync: {exc}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleSyncCog(bot))
    print("🔄 Role Sync loaded!")