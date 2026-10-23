"""
moderation.py — Advanced Moderation & Administration System.

Structured with the GKR Centralized Design System:
  • /ban, /unban, /unbanall, /banlist — Server ban management
  • /kick — Member kick with permission safety
  • /mute, /unmute, /mutelist — Clean moderation infraction cards
  • /staffrole — Add/remove/list staff roles
  • /saye, /sayt — Official announcements
  • /config, /status — Administration overview & bot health
"""

from __future__ import annotations

import asyncio
import datetime
import os
import platform
import re
import sqlite3
from typing import Optional, List, Union

import discord
from discord import app_commands
from discord.ext import commands

from gkr_ui import (
    C,
    BOT_NAME,
    create_moderation_embed,
    embed_success,
    embed_error,
    embed_info,
    embed_warning,
    fmt_duration,
    fmt_rel,
    fmt_ts,
)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "moderation.sqlite3")
DEV_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))


# ---------------------------------------------------------------------------
# Database (Staff Roles)
# ---------------------------------------------------------------------------

class ModerationDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS staff_roles (
                    guild_id TEXT NOT NULL,
                    role_id  TEXT NOT NULL,
                    PRIMARY KEY (guild_id, role_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS infractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    moderator_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT DEFAULT 'active'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS automod_config (
                    guild_id TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    log_channel_id TEXT DEFAULT NULL,
                    anti_invites INTEGER DEFAULT 1,
                    anti_links INTEGER DEFAULT 0,
                    anti_badwords INTEGER DEFAULT 1,
                    keyword_blacklist TEXT DEFAULT '[]',
                    action TEXT DEFAULT 'delete'
                )
            """)
            conn.commit()

    def add_staff_role(self, guild_id: int, role_id: int) -> bool:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO staff_roles (guild_id, role_id) VALUES (?, ?)",
                    (str(guild_id), str(role_id))
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_staff_role(self, guild_id: int, role_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM staff_roles WHERE guild_id=? AND role_id=?",
                (str(guild_id), str(role_id))
            )
            conn.commit()
        return cur.rowcount > 0

    def get_staff_roles(self, guild_id: int) -> List[int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role_id FROM staff_roles WHERE guild_id=?", (str(guild_id),)
            ).fetchall()
        return [int(r["role_id"]) for r in rows]

    def add_infraction(self, guild_id: int, user_id: int, action: str, reason: str, moderator_id: int) -> int:
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO infractions (guild_id, user_id, action, reason, moderator_id, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
            """, (str(guild_id), str(user_id), action, reason, str(moderator_id), time.time()))
            conn.commit()
            return cur.lastrowid

    def get_infractions(self, guild_id: int) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT id, user_id, action, reason, moderator_id, created_at, status
                FROM infractions WHERE guild_id=? ORDER BY created_at DESC LIMIT 100
            """, (str(guild_id),)).fetchall()
        return [dict(r) for r in rows]

    def revoke_infraction(self, guild_id: int, infraction_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("""
                UPDATE infractions SET status='revoked' WHERE guild_id=? AND id=?
            """, (str(guild_id), infraction_id))
            conn.commit()
        return cur.rowcount > 0

    def get_automod_config(self, guild_id: int) -> Dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM automod_config WHERE guild_id=?", (str(guild_id),)).fetchone()
            if not row:
                return {
                    "enabled": 1,
                    "log_channel_id": None,
                    "anti_invites": 1,
                    "anti_links": 0,
                    "anti_badwords": 1,
                    "keyword_blacklist": [],
                    "action": "delete"
                }
            d = dict(row)
            try:
                d["keyword_blacklist"] = json.loads(d.get("keyword_blacklist") or "[]")
            except Exception:
                d["keyword_blacklist"] = []
            return d

    def set_automod_config(self, guild_id: int, config: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO automod_config (
                    guild_id, enabled, log_channel_id, anti_invites, anti_links, anti_badwords, keyword_blacklist, action
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled=excluded.enabled,
                    log_channel_id=excluded.log_channel_id,
                    anti_invites=excluded.anti_invites,
                    anti_links=excluded.anti_links,
                    anti_badwords=excluded.anti_badwords,
                    keyword_blacklist=excluded.keyword_blacklist,
                    action=excluded.action
            """, (
                str(guild_id),
                int(config.get("enabled", 1)),
                str(config.get("log_channel_id") or "") or None,
                int(config.get("anti_invites", 1)),
                int(config.get("anti_links", 0)),
                int(config.get("anti_badwords", 1)),
                json.dumps(config.get("keyword_blacklist", [])),
                str(config.get("action", "delete"))
            ))
            conn.commit()


# ---------------------------------------------------------------------------
# Duration Parser
# ---------------------------------------------------------------------------

def parse_duration(raw: str) -> Optional[datetime.timedelta]:
    """Parse duration string like '10m', '2h', '7d', '30s'. Max 28 days."""
    pattern = re.fullmatch(r"(\d+)\s*(s|sec|m|min|h|hr|d|day|days)?", raw.strip().lower())
    if not pattern:
        return None
    amount = int(pattern.group(1))
    unit   = pattern.group(2) or "m"

    if unit.startswith("s"):
        delta = datetime.timedelta(seconds=amount)
    elif unit.startswith("m"):
        delta = datetime.timedelta(minutes=amount)
    elif unit.startswith("h"):
        delta = datetime.timedelta(hours=amount)
    elif unit.startswith("d"):
        delta = datetime.timedelta(days=amount)
    else:
        return None

    return min(delta, datetime.timedelta(days=28))


# ---------------------------------------------------------------------------
# Autocomplete & Views
# ---------------------------------------------------------------------------

async def banned_user_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete currently banned users so staff can select directly."""
    choices = []
    if not interaction.guild:
        return choices
    try:
        low = current.lower().strip()
        async for ban in interaction.guild.bans(limit=100):
            u = ban.user
            tag = f"{u.name}#{u.discriminator}" if u.discriminator != "0" else u.name
            display = f"{tag} ({u.id})"
            if not low or low in tag.lower() or low in str(u.id):
                choices.append(app_commands.Choice(name=display[:100], value=str(u.id)))
                if len(choices) >= 25:
                    break
    except Exception:
        pass
    return choices


class ConfirmUnbanAllView(discord.ui.View):
    """Confirmation modal view before mass unbanning."""
    def __init__(self, author_id: int):
        super().__init__(timeout=60.0)
        self.author_id = author_id
        self.value: Optional[bool] = None

    @discord.ui.button(label="Confirm Unban All", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command runner can confirm this.", ephemeral=True)
            return
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the command runner can cancel this.", ephemeral=True)
            return
        self.value = False
        self.stop()
        await interaction.response.edit_message(
            embed=embed_info("Cancelled", "Unban all operation was cancelled."),
            view=None,
        )


# ---------------------------------------------------------------------------
# Moderation Cog
# ---------------------------------------------------------------------------

class ModerationCog(commands.Cog):
    mod = app_commands.Group(name="mod", description="Advanced Moderation & Administration System")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ModerationDatabase()
        self.db.initialize()
        self._start_time = discord.utils.utcnow()

    async def cog_load(self) -> None:
        """Move /mod devmessage out of the public tree; scope it to dev guild only."""
        if DEV_GUILD_ID:
            g = discord.Object(id=DEV_GUILD_ID)
            # Remove from the global /mod group so it's never synced publicly
            self.mod.remove_command("devmessage")
            # Re-register as a standalone guild-scoped command
            self.bot.tree.add_command(self.devmessage_standalone, guild=g, override=True)

    async def cog_unload(self) -> None:
        if DEV_GUILD_ID:
            self.bot.tree.remove_command("devmessage", guild=discord.Object(id=DEV_GUILD_ID))

    # ── Core Implementations ──────────────────────────────────────────────────

    async def _ban_impl(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str = "No reason provided",
        delete_days: int = 0,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(embed=embed_error("This command can only be used in a server."), ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=embed_error("You cannot ban yourself."), ephemeral=True)
            return
        if user.id == self.bot.user.id:
            await interaction.response.send_message(embed=embed_error("I cannot ban myself."), ephemeral=True)
            return
        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message(embed=embed_error("You cannot ban the server owner."), ephemeral=True)
            return

        member = interaction.guild.get_member(user.id)
        if member:
            if member.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
                await interaction.response.send_message(embed=embed_error("You cannot ban a member with an equal or higher role."), ephemeral=True)
                return
            if member.top_role >= interaction.guild.me.top_role:
                await interaction.response.send_message(embed=embed_error("I cannot ban this member because their highest role is equal to or higher than mine."), ephemeral=True)
                return

        delete_days = max(0, min(7, delete_days))
        delete_seconds = delete_days * 86400

        try:
            await interaction.guild.ban(
                user,
                reason=f"[{interaction.user}] {reason}",
                delete_message_seconds=delete_seconds,
            )
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("Missing permissions to ban this user."), ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=embed_error(f"Discord API error: {e}"), ephemeral=True)
            return

        embed = create_moderation_embed(
            action_title="🔨  Member Banned",
            user=user,
            moderator=interaction.user,
            reason=reason,
            color=C.DANGER,
        )
        if delete_days > 0:
            embed.add_field(name="Messages Purged", value=f"Previous {delete_days} day{'s' if delete_days != 1 else ''}", inline=True)
        await interaction.response.send_message(embed=embed)

    async def _unban_impl(
        self,
        interaction: discord.Interaction,
        user_input: str,
        reason: str = "No reason provided",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(embed=embed_error("This command can only be used in a server."), ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message(embed=embed_error("Bot lacks `Ban Members` permission to unban."), ephemeral=True)
            return

        clean_id = re.sub(r"[<@!>]", "", user_input.strip())
        target_user: Optional[Union[discord.User, discord.Object]] = None

        if clean_id.isdigit():
            uid = int(clean_id)
            try:
                target_user = await self.bot.fetch_user(uid)
            except Exception:
                target_user = discord.Object(id=uid)
        else:
            try:
                async for ban in interaction.guild.bans(limit=1000):
                    tag = f"{ban.user.name}#{ban.user.discriminator}" if ban.user.discriminator != "0" else ban.user.name
                    if user_input.lower() in (ban.user.name.lower(), tag.lower()):
                        target_user = ban.user
                        break
            except Exception:
                pass

        if not target_user:
            await interaction.response.send_message(
                embed=embed_error("Could not find a banned user matching that name or ID.\nPlease provide a valid User ID or select from autocomplete."),
                ephemeral=True
            )
            return

        try:
            await interaction.guild.unban(target_user, reason=f"[{interaction.user}] {reason}")
        except discord.NotFound:
            await interaction.response.send_message(
                embed=embed_error("That user is not currently banned in this server."),
                ephemeral=True
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=embed_error("Bot lacks permission to unban this user."),
                ephemeral=True
            )
            return
        except Exception as e:
            await interaction.response.send_message(
                embed=embed_error(f"Failed to unban: {e}"),
                ephemeral=True
            )
            return

        if isinstance(target_user, discord.User):
            embed = create_moderation_embed(
                action_title="🔓  Member Unbanned",
                user=target_user,
                moderator=interaction.user,
                reason=reason,
                color=C.SUCCESS,
            )
        else:
            embed = discord.Embed(
                title="🔓  Member Unbanned",
                description=f"**User:** <@{clean_id}> (`{clean_id}`)\n**Moderator:** {interaction.user.mention}\n**Reason:**\n> {reason}",
                color=C.SUCCESS,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="Moderation Log")

        await interaction.response.send_message(embed=embed)

    async def _unbanall_impl(self, interaction: discord.Interaction, force: bool = False) -> None:
        if not interaction.guild:
            await interaction.response.send_message(embed=embed_error("This command can only be used in a server."), ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message(embed=embed_error("Bot lacks `Ban Members` permission to unban."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        try:
            bans = [b async for b in interaction.guild.bans(limit=2500)]
        except discord.Forbidden:
            await interaction.followup.send(embed=embed_error("Missing permissions to view server ban list."), ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(embed=embed_error(f"Failed to fetch ban list: {e}"), ephemeral=True)
            return

        total = len(bans)
        if total == 0:
            await interaction.followup.send(embed=embed_info("No Active Bans", "There are currently no banned users in this server."))
            return

        if not force:
            view = ConfirmUnbanAllView(author_id=interaction.user.id)
            confirm_embed = discord.Embed(
                title="⚠️ Confirm Unban All",
                description=f"Are you sure you want to unban all **{total:,}** banned member{'s' if total != 1 else ''}?\nThis action cannot be undone.",
                color=C.WARNING,
            )
            confirm_embed.set_footer(text="Click 'Confirm Unban All' within 60 seconds")
            msg = await interaction.followup.send(embed=confirm_embed, view=view)
            await view.wait()

            if view.value is not True:
                if view.value is None:
                    await msg.edit(embed=embed_info("Timed Out", "Unban all confirmation timed out."), view=None)
                return

            progress_msg = msg
        else:
            progress_msg = await interaction.followup.send(
                embed=embed_info("Starting Unban All", f"Beginning unban process for **{total:,}** members...")
            )

        unbanned_count = 0
        failed_count = 0

        status_embed = discord.Embed(
            title="🔄  Unbanning Members in Progress...",
            description=f"Progress: `0 / {total:,}` unbanned\nPlease wait...",
            color=C.BRAND,
        )
        await progress_msg.edit(embed=status_embed, view=None)

        last_edit = discord.utils.utcnow()

        for idx, ban in enumerate(bans, start=1):
            try:
                await interaction.guild.unban(ban.user, reason=f"Bulk Unban by [{interaction.user}]")
                unbanned_count += 1
            except Exception:
                failed_count += 1

            await asyncio.sleep(0.35)

            now = discord.utils.utcnow()
            if (idx % 10 == 0 or idx == total) and (now - last_edit).total_seconds() >= 3.0:
                status_embed.description = f"Progress: `{unbanned_count:,} / {total:,}` unbanned" + (f" ({failed_count} failed)" if failed_count else "")
                try:
                    await progress_msg.edit(embed=status_embed)
                    last_edit = now
                except Exception:
                    pass

        result_embed = discord.Embed(
            title="✅  Bulk Unban Completed",
            description=f"Successfully unbanned **{unbanned_count:,}** member{'s' if unbanned_count != 1 else ''}." + (f"\nFailed to unban: **{failed_count:,}**" if failed_count else ""),
            color=C.SUCCESS,
            timestamp=discord.utils.utcnow(),
        )
        result_embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        result_embed.add_field(name="Total Processed", value=f"`{total:,}`", inline=True)
        result_embed.set_footer(text="Moderation Log · Unban All")
        await progress_msg.edit(embed=result_embed, view=None)

    async def _banlist_impl(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(embed=embed_error("This command can only be used in a server."), ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message(embed=embed_error("Bot lacks `Ban Members` permission."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            bans = [b async for b in interaction.guild.bans(limit=100)]
        except Exception as e:
            await interaction.followup.send(embed=embed_error(f"Failed to fetch ban list: {e}"), ephemeral=True)
            return

        if not bans:
            await interaction.followup.send(embed=embed_success("No Active Bans", "No members are currently banned in this server."), ephemeral=True)
            return

        lines = []
        for b in bans[:25]:
            u = b.user
            tag = f"{u.name}#{u.discriminator}" if u.discriminator != "0" else u.name
            reason = b.reason or "No reason provided"
            if len(reason) > 40:
                reason = reason[:37] + "..."
            lines.append(f"• **{tag}** (`{u.id}`) — *{reason}*")

        embed = discord.Embed(
            title=f"🔨  Server Ban List ({len(bans):,})",
            description="\n".join(lines),
            color=C.DANGER,
            timestamp=discord.utils.utcnow()
        )
        if len(bans) > 25:
            embed.set_footer(text=f"Showing latest 25 of {len(bans):,} bans")
        else:
            embed.set_footer(text=f"Total: {len(bans):,} bans")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _kick_impl(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(embed=embed_error("This command can only be used in a server."), ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=embed_error("You cannot kick yourself."), ephemeral=True)
            return
        if user.id == self.bot.user.id:
            await interaction.response.send_message(embed=embed_error("I cannot kick myself."), ephemeral=True)
            return
        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message(embed=embed_error("You cannot kick the server owner."), ephemeral=True)
            return

        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(embed=embed_error("You cannot kick a member with an equal or higher role."), ephemeral=True)
            return
        if user.top_role >= interaction.guild.me.top_role:
            await interaction.response.send_message(embed=embed_error("I cannot kick this member because their highest role is equal to or higher than mine."), ephemeral=True)
            return

        try:
            await user.kick(reason=f"[{interaction.user}] {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("Missing permissions to kick this member."), ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(embed=embed_error(f"Failed to kick: {e}"), ephemeral=True)
            return

        embed = create_moderation_embed(
            action_title="👢  Member Kicked",
            user=user,
            moderator=interaction.user,
            reason=reason,
            color=C.WARNING,
        )
        await interaction.response.send_message(embed=embed)

    async def _mute_impl(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: str = "1h",
        reason: str = "No reason provided",
    ) -> None:
        if user.bot:
            await interaction.response.send_message(embed=embed_error("Cannot timeout a bot account."), ephemeral=True)
            return
        if user == interaction.user:
            await interaction.response.send_message(embed=embed_error("You cannot timeout yourself."), ephemeral=True)
            return
        if user.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message(embed=embed_error("You cannot timeout a member with an equal or higher role."), ephemeral=True)
            return

        delta = parse_duration(duration)
        if not delta:
            await interaction.response.send_message(embed=embed_error("Invalid duration. Use formats like `10m`, `2h`, `1d`."), ephemeral=True)
            return

        until = discord.utils.utcnow() + delta
        try:
            await user.timeout(until, reason=f"[{interaction.user}] {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("Missing permissions to timeout this member."), ephemeral=True)
            return

        dur_str = fmt_duration(delta.total_seconds())
        embed = create_moderation_embed(
            action_title="🔇  Member Timed Out",
            user=user,
            moderator=interaction.user,
            reason=reason,
            duration_str=dur_str,
            expires_at=until,
            color=C.DANGER,
        )
        await interaction.response.send_message(embed=embed)

    async def _unmute_impl(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        if not user.is_timed_out():
            await interaction.response.send_message(embed=embed_info("Not Timed Out", f"{user.mention} is not currently timed out."), ephemeral=True)
            return
        try:
            await user.timeout(None, reason=f"[{interaction.user}] {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed_error("Missing permissions to remove timeout."), ephemeral=True)
            return

        embed = create_moderation_embed(
            action_title="🔊  Timeout Removed",
            user=user,
            moderator=interaction.user,
            reason=reason,
            color=C.SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    async def _mutelist_impl(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        muted = [m for m in interaction.guild.members if m.is_timed_out() and not m.bot]
        if not muted:
            await interaction.followup.send(embed=embed_success("No Active Timeouts", "No members are currently timed out."), ephemeral=True)
            return

        lines = []
        for m in muted[:20]:
            expires = m.communication_disabled_until
            exp_str = fmt_rel(expires) if expires else "Unknown"
            lines.append(f"• **{m.display_name}** ({m.mention}) — expires {exp_str}")

        embed = discord.Embed(
            title=f"🔇  Active Timeouts ({len(muted):,})",
            description="\n".join(lines),
            color=C.WARNING
        )
        if len(muted) > 20:
            embed.set_footer(text=f"Showing latest 20 of {len(muted):,} timed-out members")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /mod Group Commands ───────────────────────────────────────────────────

    @mod.command(name="unban", description="Unban a member from the server")
    @app_commands.describe(user="The member to unban (select from list, type username, or paste User ID)", reason="Reason for unbanning")
    @app_commands.autocomplete(user=banned_user_autocomplete)
    @app_commands.default_permissions(ban_members=True)
    async def mod_unban(self, interaction: discord.Interaction, user: str, reason: str = "No reason provided") -> None:
        await self._unban_impl(interaction, user, reason)

    @mod.command(name="unbanall", description="Unban all banned members in this server")
    @app_commands.describe(force="Skip the confirmation prompt and immediately unban all")
    @app_commands.default_permissions(administrator=True)
    async def mod_unbanall(self, interaction: discord.Interaction, force: bool = False) -> None:
        await self._unbanall_impl(interaction, force)

    @mod.command(name="banlist", description="List all currently banned members in the server")
    @app_commands.default_permissions(ban_members=True)
    async def mod_banlist(self, interaction: discord.Interaction) -> None:
        await self._banlist_impl(interaction)

    @mod.command(name="ban", description="Ban a member or user from the server")
    @app_commands.describe(
        user="The user or member to ban",
        reason="Reason for the ban",
        delete_days="Number of days of messages to delete (0-7)"
    )
    @app_commands.choices(delete_days=[
        app_commands.Choice(name="Don't delete any messages", value=0),
        app_commands.Choice(name="Previous 24 Hours (1 day)", value=1),
        app_commands.Choice(name="Previous 3 Days", value=3),
        app_commands.Choice(name="Previous 7 Days", value=7),
    ])
    @app_commands.default_permissions(ban_members=True)
    async def mod_ban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str = "No reason provided",
        delete_days: int = 0
    ) -> None:
        await self._ban_impl(interaction, user, reason, delete_days)

    @mod.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(user="The member to kick", reason="Reason for kicking")
    @app_commands.default_permissions(kick_members=True)
    async def mod_kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided"
    ) -> None:
        await self._kick_impl(interaction, user, reason)

    @mod.command(name="mute", description="Timeout (mute) a member")
    @app_commands.describe(
        user="The member to timeout",
        duration="Duration e.g. 10m, 2h, 7d (default: 1h, max: 28d)",
        reason="Reason for the timeout",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mod_mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: str = "1h",
        reason: str = "No reason provided",
    ) -> None:
        await self._mute_impl(interaction, user, duration, reason)

    @mod.command(name="unmute", description="Remove timeout from a member")
    @app_commands.describe(user="The member to unmute", reason="Reason for removal")
    @app_commands.default_permissions(moderate_members=True)
    async def mod_unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        await self._unmute_impl(interaction, user, reason)

    @mod.command(name="mutelist", description="List all currently timed-out members")
    @app_commands.default_permissions(moderate_members=True)
    async def mod_mutelist(self, interaction: discord.Interaction) -> None:
        await self._mutelist_impl(interaction)

    @mod.command(name="staffrole", description="Manage administrative staff roles")
    @app_commands.describe(action="Action to perform", role="The target role")
    @app_commands.choices(action=[
        app_commands.Choice(name="Add",    value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="List",   value="list"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def staffrole(
        self,
        interaction: discord.Interaction,
        action: str,
        role: Optional[discord.Role] = None,
    ) -> None:
        if action == "list":
            role_ids = self.db.get_staff_roles(interaction.guild.id)
            if not role_ids:
                await interaction.response.send_message(embed=embed_info("Staff Roles", "No staff roles configured."), ephemeral=True)
                return
            mentions = [r.mention for rid in role_ids if (r := interaction.guild.get_role(rid))]
            embed = discord.Embed(
                title="🛡️  Configured Staff Roles",
                description="\n".join(f"• {m}" for m in mentions) or "No valid roles found.",
                color=C.BRAND
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not role:
            await interaction.response.send_message(embed=embed_error("Please specify a role to add or remove."), ephemeral=True)
            return

        if action == "add":
            added = self.db.add_staff_role(interaction.guild.id, role.id)
            if added:
                await interaction.response.send_message(embed=embed_success("Staff Role Added", f"{role.mention} has been designated as a staff role."), ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed_info("Already Configured", f"{role.mention} is already in the staff roles list."), ephemeral=True)
        else:
            removed = self.db.remove_staff_role(interaction.guild.id, role.id)
            if removed:
                await interaction.response.send_message(embed=embed_success("Staff Role Removed", f"{role.mention} was removed from staff roles."), ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed_info("Not Found", f"{role.mention} was not configured as a staff role."), ephemeral=True)

    @mod.command(name="saye", description="Send a formatted embed announcement as the bot")
    @app_commands.describe(channel="Target channel", title="Embed title", message="Body content", color="Hex color code (e.g. #5865F2)")
    @app_commands.default_permissions(manage_messages=True)
    async def saye(self, interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str, color: str = "#5865F2") -> None:
        try:
            color_int = int(color.replace("#", ""), 16)
        except ValueError:
            color_int = C.BRAND

        embed = discord.Embed(title=title, description=message, color=color_int)
        if interaction.guild and interaction.guild.icon:
            embed.set_footer(text=interaction.guild.name, icon_url=interaction.guild.icon.url)
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(embed=embed_error(f"Failed to send to {channel.mention}: {e}"), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Embed Dispatched", f"Sent to {channel.mention}."), ephemeral=True)

    @mod.command(name="sayt", description="Send a plain text message as the bot")
    @app_commands.describe(channel="Target channel", message="Message content")
    @app_commands.default_permissions(manage_messages=True)
    async def sayt(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str) -> None:
        try:
            await channel.send(message)
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(embed=embed_error(f"Failed to send to {channel.mention}: {e}"), ephemeral=True)
            return
        await interaction.response.send_message(embed=embed_success("Message Dispatched", f"Sent to {channel.mention}."), ephemeral=True)

    @mod.command(name="config", description="View server configuration overview")
    @app_commands.default_permissions(manage_guild=True)
    async def config_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        staff_role_ids = self.db.get_staff_roles(guild.id)
        staff_str = " ".join(f"<@&{rid}>" for rid in staff_role_ids) if staff_role_ids else "*None*"

        lines = [
            f"**Server:** {guild.name} (`{guild.id}`)",
            f"**Members:** `{guild.member_count:,}` · **Channels:** `{len(guild.channels):,}`",
            f"**Staff Roles:** {staff_str}",
            f"**Active Modules:** `{len(self.bot.cogs)}` loaded",
        ]

        embed = discord.Embed(
            title="⚙️  Server Configuration Overview",
            description="\n".join(lines),
            color=C.BRAND
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @mod.command(name="status", description="Show bot health, uptime, and system performance")
    async def status(self, interaction: discord.Interaction) -> None:
        uptime = discord.utils.utcnow() - self._start_time
        uptime_str = fmt_duration(uptime.total_seconds())

        latency_ms = round(self.bot.latency * 1000, 1)
        latency_badge = "🟢 Good" if latency_ms < 100 else ("🟡 Normal" if latency_ms < 250 else "🔴 High")

        lines = [
            f"**Uptime:** `{uptime_str}`",
            f"**Gateway Ping:** `{latency_ms}ms` ({latency_badge})",
            f"**Active Guilds:** `{len(self.bot.guilds):,}` · **Cached Users:** `{sum(g.member_count for g in self.bot.guilds):,}`",
            f"**Platform:** Python `{platform.python_version()}` · discord.py `{discord.__version__}`",
            f"**Loaded Modules:** `{len(self.bot.cogs)}` modules active",
        ]

        embed = discord.Embed(
            title=f"🤖  {BOT_NAME} Bot System Status",
            description="\n".join(lines),
            color=C.SUCCESS if latency_ms < 200 else C.WARNING,
            timestamp=discord.utils.utcnow()
        )

        try:
            from bot_status_msg import get_status_message
            status_msg = get_status_message()
            if status_msg and status_msg.get("active") and status_msg.get("message"):
                embed.add_field(
                    name="📢 Developer Notice",
                    value=f"```\n{status_msg['message']}\n```\n*Updated: {status_msg.get('updated_at', 'recently')} by {status_msg.get('author', 'Dev')}*",
                    inline=False
                )
        except Exception:
            pass

        await interaction.response.send_message(embed=embed)

    @mod.command(name="devmessage", description="Set or clear the global developer status message (Dev only)")
    @app_commands.describe(message="The notice to broadcast (leave blank to clear)", active="Whether the notice is active")
    async def devmessage(self, interaction: discord.Interaction, message: Optional[str] = None, active: bool = True) -> None:
        from bot_status_msg import set_status_message, clear_status_message
        is_allowed = False
        try:
            if await self.bot.is_owner(interaction.user):
                is_allowed = True
            else:
                from admin_api import _admin_ids
                if interaction.user.id in _admin_ids(self.bot):
                    is_allowed = True
        except Exception:
            is_allowed = False

        if not is_allowed:
            return await interaction.response.send_message(
                embed=discord.Embed(title="❌ Access Denied", description="Only bot developers can use this command.", color=C.DANGER),
                ephemeral=True
            )

        if not message or not message.strip():
            clear_status_message()
            return await interaction.response.send_message(
                embed=discord.Embed(title="✅ Notice Cleared", description="The global developer status notice has been removed.", color=C.SUCCESS),
                ephemeral=True
            )

        saved = set_status_message(message.strip(), author=interaction.user.display_name, active=active)
        state_str = "🟢 Active" if active else "⏸️ Disabled"
        embed = discord.Embed(
            title="📢 Developer Notice Updated",
            description=f"**Status:** {state_str}\n\n> {saved['message']}\n\n*This notice is now visible in `/status` and system panels.*",
            color=C.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Standalone guild-scoped copy used by cog_load
    @app_commands.command(name="devmessage", description="[Dev only] Set or clear the global developer status message")
    @app_commands.describe(message="The notice to broadcast (leave blank to clear)", active="Whether the notice is active")
    async def devmessage_standalone(self, interaction: discord.Interaction, message: Optional[str] = None, active: bool = True) -> None:
        from bot_status_msg import set_status_message, clear_status_message
        # Guild check
        if DEV_GUILD_ID and interaction.guild_id != DEV_GUILD_ID:
            return await interaction.response.send_message(embed=embed_error("Dev guild only."), ephemeral=True)
        # Owner check
        is_allowed = False
        try:
            from blacklist import is_bot_staff
            is_allowed = await is_bot_staff(interaction, self.bot)
        except Exception:
            try:
                is_allowed = await self.bot.is_owner(interaction.user)
            except Exception:
                pass
        if not is_allowed:
            return await interaction.response.send_message(
                embed=discord.Embed(title="❌ Access Denied", description="Bot owner only.", color=C.DANGER),
                ephemeral=True
            )
        if not message or not message.strip():
            clear_status_message()
            return await interaction.response.send_message(
                embed=discord.Embed(title="✅ Notice Cleared", description="Global developer status notice removed.", color=C.SUCCESS),
                ephemeral=True
            )
        saved = set_status_message(message.strip(), author=interaction.user.display_name, active=active)
        state_str = "🟢 Active" if active else "⏸️ Disabled"
        embed = discord.Embed(
            title="📢 Developer Notice Updated",
            description=f"**Status:** {state_str}\n\n> {saved['message']}\n\n*Visible in `/status` and system panels.*",
            color=C.SUCCESS
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
