"""
dev_global_logs.py — Developer-only global bot monitoring system.

Accessible ONLY inside the developer guild (DISCORD_GUILD_ID).
Creates a set of global log channels in the developer guild, one per
log category. All events from all servers the bot is in are forwarded
to these channels with the guild name and ID clearly shown.

Log channels created:
  #dev-role-logs        — role changes across all servers
  #dev-member-logs      — join/leave/ban events
  #dev-message-logs     — deleted/edited messages
  #dev-command-logs     — slash commands used
  #dev-invite-logs      — invite tracking across all servers
  #dev-server-events    — channel/server-level events
"""

from __future__ import annotations

import os
import sqlite3
import datetime

import discord
from discord import app_commands
from discord.ext import commands

DEV_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))

DB_PATH = os.path.join(os.path.dirname(__file__), "dev_logs.sqlite3")

# Channel definitions: (key, name, topic)
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

    def get_channel(self, key: str) -> int | None:
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

    def get_all(self) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT key, channel_id FROM dev_log_channels").fetchall()
        return {r["key"]: int(r["channel_id"]) for r in rows}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _guild_footer(guild: discord.Guild) -> str:
    return f"🌐 {guild.name}  •  {guild.id}"


MEMBERS_PER_PAGE = 20


async def _build_members_embed(guild: discord.Guild, page: int) -> discord.Embed:
    """Build a paginated embed of guild members."""
    members = sorted(guild.members, key=lambda m: m.display_name.lower())
    total = len(members)
    bots = sum(1 for m in members if m.bot)
    humans = total - bots
    online = sum(1 for m in members if m.status != discord.Status.offline)

    start = page * MEMBERS_PER_PAGE
    end = start + MEMBERS_PER_PAGE
    page_members = members[start:end]
    total_pages = max(1, (total + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE)

    lines = []
    for m in page_members:
        status_emoji = {
            discord.Status.online: "🟢",
            discord.Status.idle: "🟡",
            discord.Status.dnd: "🔴",
            discord.Status.offline: "⚫",
        }.get(m.status, "⚫")
        bot_tag = " 🤖" if m.bot else ""
        lines.append(f"{status_emoji} **{m.display_name}**{bot_tag} `{m.id}`")

    embed = discord.Embed(
        title=f"👥 {guild.name} — Members",
        description="\n".join(lines) or "*No members*",
        color=0x5865F2,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Total", value=str(total), inline=True)
    embed.add_field(name="Humans", value=str(humans), inline=True)
    embed.add_field(name="Bots", value=str(bots), inline=True)
    embed.add_field(name="Online", value=str(online), inline=True)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.set_footer(text=f"Page {page + 1}/{total_pages}  •  Guild ID: {guild.id}")
    return embed


class _MembersPaginatorView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild = guild
        self.page = 0
        total = len(guild.members)
        self.total_pages = max(1, (total + MEMBERS_PER_PAGE - 1) // MEMBERS_PER_PAGE)

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page > 0:
            self.page -= 1
        embed = await _build_members_embed(self.guild, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶ Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.page < self.total_pages - 1:
            self.page += 1
        embed = await _build_members_embed(self.guild, self.page)
        await interaction.response.edit_message(embed=embed, view=self)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class DevLogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DevLogsDB()

    async def cog_load(self) -> None:
        """Register /dev as a guild-specific command so it ONLY shows in the dev guild."""
        if DEV_GUILD_ID:
            dev_guild_obj = discord.Object(id=DEV_GUILD_ID)
            # Add the group to the tree scoped to the dev guild only
            self.bot.tree.add_command(self.dev_group, guild=dev_guild_obj)

    async def cog_unload(self) -> None:
        """Remove the guild-specific command when the cog unloads."""
        if DEV_GUILD_ID:
            dev_guild_obj = discord.Object(id=DEV_GUILD_ID)
            self.bot.tree.remove_command("dev", guild=dev_guild_obj)

    # ── Send helper ───────────────────────────────────────────────────────────

    async def _forward(self, key: str, embed: discord.Embed) -> None:
        """Forward an embed to the correct dev log channel."""
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

    # dev_group is registered guild-only in cog_load — NOT as a global command
    dev_group = app_commands.Group(
        name="dev",
        description="[Developer Only] Bot management commands",
    )

    @dev_group.command(name="setup_logs", description="Create or update the global dev log channels")
    async def setup_logs(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message("❌ This command can only be used in the developer guild.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # Find or create the category
        category: discord.CategoryChannel | None = discord.utils.get(guild.categories, name="🔧 Dev Logs")
        if not category:
            category = await guild.create_category("🔧 Dev Logs")

        created = []
        updated = []

        for key, ch_name, topic in DEV_LOG_CHANNELS:
            existing_id = self.db.get_channel(key)
            existing = guild.get_channel(existing_id) if existing_id else None

            if existing:
                updated.append(ch_name)
            else:
                # Create new channel
                ch = await guild.create_text_channel(ch_name, category=category, topic=topic)
                self.db.set_channel(key, ch.id)
                created.append(ch_name)

        parts = []
        if created:
            parts.append("**Created:** " + ", ".join(f"`#{n}`" for n in created))
        if updated:
            parts.append("**Already existed:** " + ", ".join(f"`#{n}`" for n in updated))

        embed = discord.Embed(
            title="✅ Dev Log Channels Ready",
            description="\n".join(parts) or "All channels already exist.",
            color=0x57F287,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dev_group.command(name="status", description="Show all dev log channel assignments")
    async def status(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message("❌ Developer only.", ephemeral=True)
            return

        mapping = self.db.get_all()
        lines = []
        for key, _, _ in DEV_LOG_CHANNELS:
            ch_id = mapping.get(key)
            ch = interaction.guild.get_channel(ch_id) if ch_id else None
            status = ch.mention if ch else "❌ Not set"
            lines.append(f"`{key}` → {status}")

        embed = discord.Embed(title="🔧 Dev Log Status", description="\n".join(lines), color=0x3498DB)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev_group.command(name="guilds", description="List all guilds the bot is in")
    async def list_guilds(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message("❌ Developer only.", ephemeral=True)
            return

        lines = [f"`{g.id}` — **{g.name}** ({g.member_count} members)" for g in self.bot.guilds]
        embed = discord.Embed(
            title=f"🌐 Bot is in {len(self.bot.guilds)} servers",
            description="\n".join(lines[:25]),
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev_group.command(name="members", description="View all members of any guild the bot is in")
    @app_commands.describe(guild_id="The server ID to view members for (leave blank for current server)")
    async def list_members(self, interaction: discord.Interaction, guild_id: str = "") -> None:
        if interaction.guild_id != DEV_GUILD_ID:
            await interaction.response.send_message("❌ Developer only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Resolve target guild
        if guild_id.strip():
            if not guild_id.strip().isdigit():
                await interaction.followup.send("❌ Guild ID must be a number.", ephemeral=True)
                return
            target_guild = self.bot.get_guild(int(guild_id.strip()))
            if not target_guild:
                await interaction.followup.send("❌ Bot is not in that server, or the ID is wrong.", ephemeral=True)
                return
        else:
            # Show a guild picker dropdown
            guilds = self.bot.guilds
            options = [
                discord.SelectOption(
                    label=g.name[:100],
                    value=str(g.id),
                    description=f"{g.member_count} members • ID: {g.id}",
                )
                for g in guilds[:25]
            ]
            bot_ref = self.bot

            class _GuildSelect(discord.ui.Select):
                def __init__(self_inner):
                    super().__init__(placeholder="Select a server to inspect...", options=options)

                async def callback(self_inner, select_interaction: discord.Interaction):
                    await select_interaction.response.defer(ephemeral=True)
                    chosen_guild = bot_ref.get_guild(int(self_inner.values[0]))
                    if chosen_guild:
                        emb = await _build_members_embed(chosen_guild, page=0)
                        pag_view = _MembersPaginatorView(bot_ref, chosen_guild)
                        await select_interaction.followup.send(embed=emb, view=pag_view, ephemeral=True)

            view = discord.ui.View(timeout=60)
            view.add_item(_GuildSelect())
            await interaction.followup.send("Select a server to inspect:", view=view, ephemeral=True)
            return

        embed = await _build_members_embed(target_guild, page=0)
        view = _MembersPaginatorView(self.bot, target_guild)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ── Global event listeners ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="📥 Member Joined", color=0x57F287, timestamp=discord.utils.utcnow())
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=True)
        embed.add_field(name="Account Age", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=_guild_footer(member.guild))
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="📤 Member Left", color=0xE74C3C, timestamp=discord.utils.utcnow())
        embed.add_field(name="User", value=f"{member} (`{member.id}`)", inline=True)
        embed.set_footer(text=_guild_footer(member.guild))
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="🔨 Member Banned", color=0xE74C3C, timestamp=discord.utils.utcnow())
        embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=True)
        embed.set_footer(text=_guild_footer(guild))
        await self._forward("member_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        if role.guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="🆕 Role Created", color=role.color, timestamp=discord.utils.utcnow())
        embed.add_field(name="Role", value=f"{role.mention} (`{role.id}`)", inline=True)
        embed.set_footer(text=_guild_footer(role.guild))
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        if role.guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="🗑️ Role Deleted", color=0xE74C3C, timestamp=discord.utils.utcnow())
        embed.add_field(name="Role", value=f"`{role.name}` (`{role.id}`)", inline=True)
        embed.set_footer(text=_guild_footer(role.guild))
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.guild.id == DEV_GUILD_ID:
            return
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if not added and not removed:
            return
        embed = discord.Embed(title="🔄 Member Roles Updated", color=0x3498DB, timestamp=discord.utils.utcnow())
        embed.add_field(name="Member", value=f"{after.mention} (`{after.id}`)", inline=False)
        if added:
            embed.add_field(name="Roles Added", value=" ".join(r.mention for r in added), inline=True)
        if removed:
            embed.add_field(name="Roles Removed", value=" ".join(r.mention for r in removed), inline=True)
        embed.set_footer(text=_guild_footer(after.guild))
        await self._forward("role_logs", embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.guild.id == DEV_GUILD_ID or message.author.bot:
            return
        embed = discord.Embed(title="🗑️ Message Deleted", color=0xE74C3C, timestamp=discord.utils.utcnow())
        embed.add_field(name="Author", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="Content", value=message.content[:1024], inline=False)
        embed.set_footer(text=_guild_footer(message.guild))
        await self._forward("message_logs", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.guild.id == DEV_GUILD_ID or before.author.bot:
            return
        if before.content == after.content:
            return
        embed = discord.Embed(title="✏️ Message Edited", color=0xF39C12, timestamp=discord.utils.utcnow())
        embed.add_field(name="Author", value=f"{before.author.mention} (`{before.author.id}`)", inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=before.content[:512] or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content[:512] or "*empty*", inline=False)
        embed.set_footer(text=_guild_footer(before.guild))
        await self._forward("message_logs", embed)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command) -> None:
        if not interaction.guild or interaction.guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="⌨️ Command Used", color=0x9B59B6, timestamp=discord.utils.utcnow())
        embed.add_field(name="Command", value=f"`/{command.qualified_name}`", inline=True)
        embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        embed.add_field(name="Channel", value=interaction.channel.mention if interaction.channel else "Unknown", inline=True)
        embed.set_footer(text=_guild_footer(interaction.guild))
        await self._forward("command_logs", embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if not invite.guild or invite.guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="🔗 Invite Created", color=0x1ABC9C, timestamp=discord.utils.utcnow())
        embed.add_field(name="Code", value=f"`{invite.code}`", inline=True)
        embed.add_field(name="Created By", value=f"{invite.inviter.mention}" if invite.inviter else "Unknown", inline=True)
        embed.add_field(name="Max Uses", value=str(invite.max_uses or "∞"), inline=True)
        embed.set_footer(text=_guild_footer(invite.guild))
        await self._forward("invite_logs", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="📁 Channel Created", color=0x57F287, timestamp=discord.utils.utcnow())
        embed.add_field(name="Channel", value=f"`{channel.name}` (`{channel.id}`)", inline=True)
        embed.add_field(name="Type", value=str(channel.type), inline=True)
        embed.set_footer(text=_guild_footer(channel.guild))
        await self._forward("server_events", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id == DEV_GUILD_ID:
            return
        embed = discord.Embed(title="📁 Channel Deleted", color=0xE74C3C, timestamp=discord.utils.utcnow())
        embed.add_field(name="Channel", value=f"`{channel.name}` (`{channel.id}`)", inline=True)
        embed.set_footer(text=_guild_footer(channel.guild))
        await self._forward("server_events", embed)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if after.id == DEV_GUILD_ID:
            return
        if before.name != after.name:
            embed = discord.Embed(title="🏠 Server Renamed", color=0xF39C12, timestamp=discord.utils.utcnow())
            embed.add_field(name="Before", value=before.name, inline=True)
            embed.add_field(name="After", value=after.name, inline=True)
            embed.set_footer(text=_guild_footer(after))
            await self._forward("server_events", embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DevLogsCog(bot))
    print("🔧 Dev Global Logs loaded!")
