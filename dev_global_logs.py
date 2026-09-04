"""
dev_global_logs.py — Developer-Only Global Bot Monitoring System.

Accessible ONLY inside the developer guild (DISCORD_GUILD_ID).
Dispatches cross-server activity using the centralized GKR design system.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional, List, Dict

import discord
from discord import app_commands
from discord.ext import commands

from gkr_ui import (
    C,
    create_audit_embed,
    embed_success,
    embed_error,
    embed_info,
    fmt_rel,
    Paginator,
)

DEV_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
DB_PATH = os.path.join(os.path.dirname(__file__), "dev_logs.sqlite3")

DEV_LOG_CHANNELS = [
    ("role_logs",    "dev-role-logs",    "All role & member-role events across all servers"),
    ("member_logs",  "dev-member-logs",  "All member join/leave/ban events across all servers"),
    ("message_logs", "dev-message-logs", "All deleted and edited messages across all servers"),
    ("command_logs", "dev-command-logs", "All slash commands used across all servers"),
    ("invite_logs",  "dev-invite-logs",  "All invite events across all servers"),
    ("server_events","dev-server-events","Channel, role, and server-level changes across all servers"),
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class DevLogsDB:
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
                CREATE TABLE IF NOT EXISTS dev_log_channels (
                    key        TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL
                )
            """)
            c.commit()

    def get_channel(self, key: str) -> Optional[int]:
        with self._conn() as c:
            row = c.execute("SELECT channel_id FROM dev_log_channels WHERE key=?", (key,)).fetchone()
        return int(row["channel_id"]) if row else None

    def set_channel(self, key: str, channel_id: int) -> None:
        with self._conn() as c:
            c.execute("""
                INSERT INTO dev_log_channels (key, channel_id) VALUES (?,?)
                ON CONFLICT(key) DO UPDATE SET channel_id=excluded.channel_id
            """, (key, str(channel_id)))
            c.commit()

    def get_all(self) -> Dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT key, channel_id FROM dev_log_channels").fetchall()
        return {r["key"]: int(r["channel_id"]) for r in rows}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guild_footer(guild: discord.Guild) -> str:
    return f"{guild.name} · {guild.id}"


MEMBERS_PER_PAGE = 20

def _build_members_embeds(guild: discord.Guild) -> List[discord.Embed]:
    members = sorted(guild.members, key=lambda m: m.display_name.lower())
    total = len(members)
    chunks = [members[i:i + MEMBERS_PER_PAGE] for i in range(0, total, MEMBERS_PER_PAGE)]
    if not chunks:
        return [embed_info(f"👥 {guild.name} — Members", "No members found in guild.")]

    pages = []
    total_pages = len(chunks)
    for idx, chunk in enumerate(chunks):
        lines = []
        for m in chunk:
            bot_badge = " `[BOT]`" if m.bot else ""
            lines.append(f"• **{m.display_name}**{bot_badge} ({m.mention})")

        e = discord.Embed(
            title=f"👥 {guild.name} — Member Directory",
            description="\n".join(lines),
            color=C.BRAND
        )
        e.set_footer(text=f"Page {idx+1}/{total_pages} · {total:,} total members · {guild.name}")
        pages.append(e)
    return pages


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class DevLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DevLogsDB()

    async def cog_load(self) -> None:
        if DEV_GUILD_ID:
            dev_guild_obj = discord.Object(id=DEV_GUILD_ID)
            self.bot.tree.add_command(self.dev_group, guild=dev_guild_obj)

    async def cog_unload(self) -> None:
        if DEV_GUILD_ID:
            dev_guild_obj = discord.Object(id=DEV_GUILD_ID)
            self.bot.tree.remove_command("dev", guild=dev_guild_obj)

    async def _forward(self, key: str, embed: discord.Embed) -> None:
        if not DEV_GUILD_ID:
            return
        channel_id = self.db.get_channel(key)
        if not channel_id:
            return
        dev_guild = self.bot.get_guild(DEV_GUILD_ID)
        if not dev_guild:
            return
        channel = dev_guild.get_channel(channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except Exception as exc:
                print(f"[DevLogs] Failed to forward to #{channel.name}: {exc}")

    # ── Dev Command Group (Guild Only) ─────────────────────────────────────────

    dev_group = app_commands.Group(
        name="dev",
        description="[Developer Only] Global bot management commands",
    )

    @dev_group.command(name="setup_logs", description="Create or configure the global dev log channels")
    async def setup_logs(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("This command can only be used in the developer guild."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        category = discord.utils.get(guild.categories, name="🔧 Dev Logs")
        if not category:
            category = await guild.create_category("🔧 Dev Logs")

        created, updated = [], []
        for key, ch_name, topic in DEV_LOG_CHANNELS:
            existing_id = self.db.get_channel(key)
            existing = guild.get_channel(existing_id) if existing_id else None
            if existing:
                updated.append(ch_name)
            else:
                ch = await guild.create_text_channel(ch_name, category=category, topic=topic)
                self.db.set_channel(key, ch.id)
                created.append(ch_name)

        desc_lines = []
        if created:
            desc_lines.append(f"**Created:** {', '.join(f'`#{n}`' for n in created)}")
        if updated:
            desc_lines.append(f"**Configured:** {', '.join(f'`#{n}`' for n in updated)}")

        embed = embed_success("Dev Log Channels Ready", "\n".join(desc_lines) or "All channels are configured.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dev_group.command(name="status", description="Show all dev log channel assignments")
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("Developer only."), ephemeral=True)
            return

        mapping = self.db.get_all()
        lines = []
        for key, _, desc in DEV_LOG_CHANNELS:
            ch_id = mapping.get(key)
            ch = interaction.guild.get_channel(ch_id) if ch_id else None
            status = ch.mention if ch else "`Not configured`"
            lines.append(f"• **{key}**: {status}")

        embed = embed_info("🔧  Dev Log Channels", "\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev_group.command(name="guilds", description="List all guilds the bot is currently in")
    async def list_guilds(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("Developer only."), ephemeral=True)
            return

        lines = [f"• **{g.name}** — `{g.member_count:,}` members" for g in self.bot.guilds]
        embed = embed_info(f"🌐  Active Guilds ({len(self.bot.guilds)})", "\n".join(lines[:25]))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev_group.command(name="members", description="View members of any guild the bot is in")
    @app_commands.describe(guild_id="The server ID to inspect")
    async def list_members(self, interaction: discord.Interaction, guild_id: str = "") -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message(embed=embed_error("Developer only."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        if guild_id.strip():
            if not guild_id.strip().isdigit():
                await interaction.followup.send(embed=embed_error("Server ID must be a numeric integer."), ephemeral=True)
                return
            target_guild = self.bot.get_guild(int(guild_id.strip()))
            if not target_guild:
                await interaction.followup.send(embed=embed_error("Bot is not in that server or ID is invalid."), ephemeral=True)
                return
        else:
            target_guild = interaction.guild

        pages = _build_members_embeds(target_guild)
        view = Paginator(pages, interaction.user.id)
        await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)


    # ── Global Event Forwarders ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="📥 Member joined",
            subject=member.mention,
            details=[f"Account created {fmt_rel(member.created_at)}", f"Member #{member.guild.member_count:,}"],
            color=C.SUCCESS,
            thumbnail_url=member.display_avatar.url,
            footer_text=_guild_footer(member.guild)
        )
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="📤 Member left",
            subject=member.mention,
            color=C.DANGER,
            thumbnail_url=member.display_avatar.url,
            footer_text=_guild_footer(member.guild)
        )
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="🔨 Member banned",
            subject=user.mention,
            color=C.DANGER,
            thumbnail_url=user.display_avatar.url,
            footer_text=_guild_footer(guild)
        )
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        if role.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="🎭 Role created",
            subject=role.mention,
            details=[f"Color #{role.color.value:06x}"],
            color=C.PURPLE,
            footer_text=_guild_footer(role.guild)
        )
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if role.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="🗑️ Role deleted",
            subject=f"@{role.name}",
            color=C.DANGER,
            footer_text=_guild_footer(role.guild)
        )
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.guild.id == DEV_GUILD_ID:
            return
        added = [r for r in after.roles if r not in before.roles and r.name != "@everyone"]
        removed = [r for r in before.roles if r not in after.roles and r.name != "@everyone"]
        if not added and not removed:
            return

        details = [f"+ {r.mention}" for r in added] + [f"- {r.mention}" for r in removed]
        embed = create_audit_embed(
            title="🎭 Member roles updated",
            subject=after.mention,
            details=details,
            color=C.PURPLE,
            thumbnail_url=after.display_avatar.url,
            footer_text=_guild_footer(after.guild)
        )
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.guild.id == DEV_GUILD_ID or message.author.bot:
            return
        content = f"> {message.content[:500]}" if message.content else "*[No text content]*"
        embed = create_audit_embed(
            title="🗑️ Message deleted",
            subject=f"#{message.channel.name}",
            actor=message.author,
            details=[content],
            color=C.DANGER,
            thumbnail_url=message.author.display_avatar.url,
            footer_text=_guild_footer(message.guild)
        )
        await self._forward("message_logs", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.guild.id == DEV_GUILD_ID or before.author.bot or before.content == after.content:
            return
        embed = create_audit_embed(
            title="📝 Message edited",
            subject=f"#{after.channel.name}",
            actor=after.author,
            changes=[("Content", before.content[:200], after.content[:200])],
            color=C.WARNING,
            thumbnail_url=after.author.display_avatar.url,
            footer_text=_guild_footer(before.guild)
        )
        await self._forward("message_logs", embed)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command) -> None:
        if not interaction.guild or interaction.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="⌨️ Command used",
            subject=f"/{command.qualified_name}",
            actor=interaction.user,
            details=[f"Channel: {interaction.channel.mention if interaction.channel else 'N/A'}"],
            color=C.BRAND,
            thumbnail_url=interaction.user.display_avatar.url if interaction.user else None,
            footer_text=_guild_footer(interaction.guild)
        )
        await self._forward("command_logs", embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if not invite.guild or invite.guild.id == DEV_GUILD_ID:
            return
        details = [f"Channel: {invite.channel.mention if invite.channel else 'N/A'}", f"Max uses: {invite.max_uses or '∞'}"]
        embed = create_audit_embed(
            title="🔗 Invite created",
            subject=f"discord.gg/{invite.code}",
            actor=invite.inviter,
            details=details,
            color=C.CYAN,
            footer_text=_guild_footer(invite.guild)
        )
        await self._forward("invite_logs", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="➕ Channel created",
            subject=channel.mention if hasattr(channel, "mention") else f"#{channel.name}",
            details=[f"Type: {channel.type}"],
            color=C.SUCCESS,
            footer_text=_guild_footer(channel.guild)
        )
        await self._forward("server_events", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id == DEV_GUILD_ID:
            return
        embed = create_audit_embed(
            title="➖ Channel deleted",
            subject=f"#{channel.name}",
            details=[f"Type: {channel.type}"],
            color=C.DANGER,
            footer_text=_guild_footer(channel.guild)
        )
        await self._forward("server_events", embed)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if after.id == DEV_GUILD_ID or before.name == after.name:
            return
        embed = create_audit_embed(
            title="⚙️ Server renamed",
            subject=after.name,
            changes=[("Name", before.name, after.name)],
            color=C.BRAND,
            footer_text=_guild_footer(after)
        )
        await self._forward("server_events", embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DevLogsCog(bot))
    print("🔧 Dev Global Logs loaded!")
