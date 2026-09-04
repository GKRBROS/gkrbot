"""
invite_tracker.py — Advanced per-server invite tracking with rich embed UI.

Features:
  • Tracks which invite was used when a member joins
  • Rich card embed: Joined Member, Invited By, Invite Code, Total Invites,
    Joined count, Left count, Fake Invites, Account Age, Account Status, Summary
  • Per-guild invite stats stored in SQLite (join/leave counts per inviter)
  • Invite leaderboard command
  • Account age check (flag suspicious accounts < 7 days old)
  • Separate configurable log channel per guild
"""

from __future__ import annotations

import asyncio
import datetime
import os
import sqlite3
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# ─── Database ──────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "invite_tracker.sqlite3")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invite_config (
                guild_id    INTEGER PRIMARY KEY,
                channel_id  INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invite_stats (
                guild_id    INTEGER NOT NULL,
                inviter_id  INTEGER NOT NULL,
                joins       INTEGER NOT NULL DEFAULT 0,
                leaves      INTEGER NOT NULL DEFAULT 0,
                fakes       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, inviter_id)
            )
        """)
        conn.commit()


def _get_channel(guild_id: int) -> Optional[int]:
    with _db() as conn:
        row = conn.execute("SELECT channel_id FROM invite_config WHERE guild_id=?", (guild_id,)).fetchone()
    return row["channel_id"] if row else None


def _set_channel(guild_id: int, channel_id: int):
    with _db() as conn:
        conn.execute(
            "INSERT INTO invite_config (guild_id, channel_id) VALUES (?,?) ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (guild_id, channel_id),
        )
        conn.commit()


def _record_join(guild_id: int, inviter_id: int, is_fake: bool = False):
    with _db() as conn:
        conn.execute(
            "INSERT INTO invite_stats (guild_id, inviter_id, joins, fakes) VALUES (?,?,1,?) ON CONFLICT(guild_id, inviter_id) DO UPDATE SET joins=joins+1, fakes=fakes+?",
            (guild_id, inviter_id, 1 if is_fake else 0, 1 if is_fake else 0),
        )
        conn.commit()


def _record_leave(guild_id: int, inviter_id: int):
    with _db() as conn:
        conn.execute(
            "INSERT INTO invite_stats (guild_id, inviter_id, leaves) VALUES (?,?,1) ON CONFLICT(guild_id, inviter_id) DO UPDATE SET leaves=leaves+1",
            (guild_id, inviter_id),
        )
        conn.commit()


def _get_stats(guild_id: int, inviter_id: int) -> dict:
    with _db() as conn:
        row = conn.execute(
            "SELECT joins, leaves, fakes FROM invite_stats WHERE guild_id=? AND inviter_id=?",
            (guild_id, inviter_id),
        ).fetchone()
    if row:
        return {"joins": row["joins"], "leaves": row["leaves"], "fakes": row["fakes"]}
    return {"joins": 0, "leaves": 0, "fakes": 0}


def _get_leaderboard(guild_id: int, limit: int = 10):
    with _db() as conn:
        return conn.execute(
            "SELECT inviter_id, joins, leaves, fakes FROM invite_stats WHERE guild_id=? ORDER BY (joins - leaves - fakes) DESC LIMIT ?",
            (guild_id, limit),
        ).fetchall()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _account_age_str(created_at: datetime.datetime) -> tuple[str, bool]:
    """Returns (age string, is_new_account bool)."""
    now = discord.utils.utcnow()
    delta = now - created_at
    days = delta.days
    if days < 1:
        hours = delta.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}", True
    elif days < 7:
        return f"{days} day{'s' if days != 1 else ''}", True
    elif days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''}", False
    elif days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''}", False
    else:
        years = days // 365
        return f"{years} year{'s' if years != 1 else ''}", False


def _account_status(member: discord.Member) -> tuple[str, str]:
    """Returns (status label, emoji)."""
    created = member.created_at
    now = discord.utils.utcnow()
    age_days = (now - created).days

    if member.bot:
        return "Bot Account", "🤖"
    if age_days < 3:
        return "⚠️  Very New Account", "🚨"
    if age_days < 7:
        return "New Account", "⚠️"
    return "✅  Normal Account", "🛡️"


# ─── Embed Builder ────────────────────────────────────────────────────────────

def _build_join_embed(
    member: discord.Member,
    invite: Optional[discord.Invite],
    inviter: Optional[discord.User | discord.Member],
    stats: dict,
    total_inviter_invites: int,
) -> discord.Embed:
    guild = member.guild
    age_str, is_new = _account_age_str(member.created_at)
    status_label, status_emoji = _account_status(member)

    # Color based on account risk
    if is_new and (discord.utils.utcnow() - member.created_at).days < 3:
        color = 0xED4245  # red — very suspicious
    elif is_new:
        color = 0xFEE75C  # yellow — new account
    else:
        color = 0x57F287  # green — normal

    embed = discord.Embed(
        title="📨  New Member Joined",
        description=(
            f"Welcome {member.mention} to **{guild.name}**!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    # ── Row 1: Joined Member | Invited By | Invite Code
    embed.add_field(
        name="👤  Joined Member",
        value=f"{member.mention}\n`{member.name}`",
        inline=True,
    )

    if inviter:
        embed.add_field(
            name="📨  Invited By",
            value=f"{inviter.mention}\n`{inviter.name}`",
            inline=True,
        )
    else:
        embed.add_field(
            name="📨  Invited By",
            value="*Unknown*\n*(vanity / no perms)*",
            inline=True,
        )

    if invite:
        embed.add_field(
            name="🔗  Invite Code",
            value=f"`{invite.code}`",
            inline=True,
        )
    else:
        embed.add_field(name="🔗  Invite Code", value="*Unknown*", inline=True)

    # ── Row 2: Total Invites | Joined | Left
    embed.add_field(
        name="✅  Total Invites",
        value=f"**{max(0, stats['joins'] - stats['leaves'] - stats['fakes'])}** valid",
        inline=True,
    )
    embed.add_field(name="📥  Joined", value=f"**{stats['joins']}**", inline=True)
    embed.add_field(name="📤  Left", value=f"**{stats['leaves']}**", inline=True)

    # ── Row 3: Fake Invites | Account Age | Account Status
    embed.add_field(
        name="⚠️  Fake Invites",
        value=f"**{stats['fakes']}**",
        inline=True,
    )
    embed.add_field(
        name="🕒  Account Age",
        value=f"**{age_str}**",
        inline=True,
    )
    embed.add_field(
        name=f"{status_emoji}  Account Status",
        value=status_label,
        inline=True,
    )

    # ── Invite Summary
    if inviter:
        valid = max(0, stats['joins'] - stats['leaves'] - stats['fakes'])
        embed.add_field(
            name="📊  Invite Summary",
            value=(
                f"{inviter.mention} now has **{valid}** valid invite{'s' if valid != 1 else ''}.\n"
                f"Joined: **{stats['joins']}** · Left: **{stats['leaves']}** · Fake: **{stats['fakes']}**"
            ),
            inline=False,
        )

    embed.set_footer(
        text="GKR Invite Tracker System",
        icon_url=guild.icon.url if guild.icon else None,
    )
    return embed


def _build_leave_embed(member: discord.Member) -> discord.Embed:
    age_str, _ = _account_age_str(member.created_at)
    embed = discord.Embed(
        title="📤  Member Left",
        description=(
            f"{member.mention} has left **{member.guild.name}**.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xED4245,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤  Member", value=f"{member.mention}\n`{member.name}`", inline=True)
    embed.add_field(name="⌚  Joined Server", value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "*Unknown*", inline=True)
    embed.add_field(name="🕒  Account Age", value=f"**{age_str}**", inline=True)
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    if roles:
        embed.add_field(name="🎭  Roles Held", value=" ".join(roles[:10]), inline=False)
    embed.set_footer(
        text="GKR Invite Tracker System",
        icon_url=member.guild.icon.url if member.guild.icon else None,
    )
    return embed


# ─── Cog ──────────────────────────────────────────────────────────────────────

class InviteTrackerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id → {invite_code: uses}
        self._invite_cache: dict[int, dict[str, int]] = {}
        # guild_id → {member_id: invite_code_used}
        self._member_invite_map: dict[int, dict[int, str]] = {}

    async def cog_load(self) -> None:
        pass

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self._cache_all_invites()

    async def _cache_all_invites(self) -> None:
        for guild in self.bot.guilds:
            await self._cache_guild_invites(guild)

    async def _cache_guild_invites(self, guild: discord.Guild) -> None:
        try:
            invites = await guild.invites()
            self._invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _find_used_invite(self, guild: discord.Guild) -> Optional[discord.Invite]:
        old_cache = self._invite_cache.get(guild.id, {})
        try:
            current_invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None
        for invite in current_invites:
            old_uses = old_cache.get(invite.code, 0)
            if invite.uses and invite.uses > old_uses:
                self._invite_cache[guild.id] = {inv.code: inv.uses for inv in current_invites}
                return invite
        self._invite_cache[guild.id] = {inv.code: inv.uses for inv in current_invites}
        return None

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild:
            self._invite_cache.setdefault(invite.guild.id, {})[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild:
            self._invite_cache.get(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return

        guild = member.guild
        invite = await self._find_used_invite(guild)
        inviter = invite.inviter if invite else None

        # Determine if this looks like a fake invite (brand-new account < 3 days)
        age_days = (discord.utils.utcnow() - member.created_at).days
        is_fake = age_days < 3

        # Record join stats
        if inviter:
            _record_join(guild.id, inviter.id, is_fake=is_fake)
            stats = _get_stats(guild.id, inviter.id)
            total = stats["joins"]
        else:
            stats = {"joins": 0, "leaves": 0, "fakes": 0}
            total = 0

        # Track which invite this member used (for leave tracking)
        if invite and inviter:
            self._member_invite_map.setdefault(guild.id, {})[member.id] = inviter.id

        # Build and send embed
        channel_id = _get_channel(guild.id)
        if not channel_id:
            # Fallback: try to route via ServerLogsCog
            cog = self.bot.get_cog("ServerLogsCog")
            if cog:
                embed = _build_join_embed(member, invite, inviter, stats, total)
                await cog.logger._send(guild, "member_join", embed)
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = _build_join_embed(member, invite, inviter, stats, total)
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[InviteTracker] Failed to send join embed: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return

        guild = member.guild
        # Record leave for whoever invited this member
        inviter_id = self._member_invite_map.get(guild.id, {}).pop(member.id, None)
        if inviter_id:
            _record_leave(guild.id, inviter_id)

        channel_id = _get_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = _build_leave_embed(member)
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[InviteTracker] Failed to send leave embed: {e}")

    # ── Commands ───────────────────────────────────────────────────────────────

    invite_group = app_commands.Group(name="invites", description="🔗  Invite Tracker commands")

    @invite_group.command(name="setchannel", description="Set the channel where join/leave invite logs are posted")
    @app_commands.describe(channel="The text channel to send invite logs to")
    @app_commands.default_permissions(manage_guild=True)
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        _set_channel(interaction.guild.id, channel.id)
        embed = discord.Embed(
            title="✅  Invite Tracker Configured",
            description=f"Join/leave invite logs will be posted to {channel.mention}.",
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="GKR Invite Tracker System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @invite_group.command(name="stats", description="Check invite stats for a specific member")
    @app_commands.describe(member="The member to check invite stats for")
    @app_commands.default_permissions(manage_guild=True)
    async def stats(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.response.defer(ephemeral=True)
        data = _get_stats(interaction.guild.id, member.id)
        valid = max(0, data["joins"] - data["leaves"] - data["fakes"])

        embed = discord.Embed(
            title=f"📊  Invite Stats — {member.display_name}",
            description=f"{member.mention}'s invite breakdown for **{interaction.guild.name}**.",
            color=0x5865F2,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="✅  Valid Invites", value=f"**{valid}**", inline=True)
        embed.add_field(name="📥  Total Joined", value=f"**{data['joins']}**", inline=True)
        embed.add_field(name="📤  Left",          value=f"**{data['leaves']}**", inline=True)
        embed.add_field(name="⚠️  Fake Invites",  value=f"**{data['fakes']}**", inline=True)
        embed.set_footer(text="GKR Invite Tracker System", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @invite_group.command(name="leaderboard", description="Show the top inviters in this server")
    @app_commands.default_permissions(manage_guild=True)
    async def invite_leaderboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        rows = _get_leaderboard(interaction.guild.id, limit=10)

        if not rows:
            await interaction.followup.send("No invite data recorded yet.", ephemeral=True)
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            m = interaction.guild.get_member(row["inviter_id"])
            name = m.display_name if m else f"*Unknown* `{row['inviter_id']}`"
            valid = max(0, row["joins"] - row["leaves"] - row["fakes"])
            medal = medals[i] if i < 3 else f"`#{i+1}`"
            lines.append(
                f"{medal}  **{name}** — `{valid}` valid  ·  `{row['joins']}` joined  ·  `{row['leaves']}` left  ·  `{row['fakes']}` fake"
            )

        embed = discord.Embed(
            title="🏆  Invite Leaderboard",
            description="\n".join(lines),
            color=0xF1C40F,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(
            text=f"GKR Invite Tracker  •  {interaction.guild.name}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @invite_group.command(name="reset", description="Reset invite stats for a member")
    @app_commands.describe(member="The member whose stats to reset")
    @app_commands.default_permissions(administrator=True)
    async def reset_stats(self, interaction: discord.Interaction, member: discord.Member) -> None:
        with _db() as conn:
            conn.execute(
                "DELETE FROM invite_stats WHERE guild_id=? AND inviter_id=?",
                (interaction.guild.id, member.id),
            )
            conn.commit()
        await interaction.response.send_message(
            f"✅  Invite stats for {member.mention} have been **reset**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    _init_db()
    await bot.add_cog(InviteTrackerCog(bot))
    print("🔗 Invite Tracker loaded!")
