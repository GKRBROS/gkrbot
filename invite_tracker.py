"""
invite_tracker.py — Per-server invite tracking.
Tracks which invite link was used when a member joins, and logs
who invited them to the server's existing log channel via ServerLogsCog.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional


class InviteTrackerCog(commands.Cog):
    """Tracks who invited new members via invite link comparison."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Cache: guild_id -> {invite_code: uses}
        self._invite_cache: dict[int, dict[str, int]] = {}

    async def cog_load(self) -> None:
        # Schedule invite caching after bot is ready — do NOT block here
        pass

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Cache all invites once the bot is logged in and ready."""
        await self._cache_all_invites()

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _cache_all_invites(self) -> None:
        """Build the invite cache for all guilds."""
        for guild in self.bot.guilds:
            await self._cache_guild_invites(guild)

    async def _cache_guild_invites(self, guild: discord.Guild) -> None:
        """Cache current invite usage counts for a single guild."""
        try:
            invites = await guild.invites()
            self._invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
        except (discord.Forbidden, discord.HTTPException):
            pass  # bot might not have Manage Guild permission here

    async def _find_used_invite(
        self, guild: discord.Guild
    ) -> Optional[discord.Invite]:
        """Compare current invites against cached ones to find the used invite."""
        old_cache = self._invite_cache.get(guild.id, {})
        try:
            current_invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None

        # Find the invite whose use count increased
        for invite in current_invites:
            old_uses = old_cache.get(invite.code, 0)
            if invite.uses > old_uses:
                # Update cache immediately
                self._invite_cache[guild.id] = {inv.code: inv.uses for inv in current_invites}
                return invite

        # Update cache anyway
        self._invite_cache[guild.id] = {inv.code: inv.uses for inv in current_invites}
        return None

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Cache invites when the bot joins a new guild."""
        await self._cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        """Update cache when a new invite is created."""
        if invite.guild:
            cache = self._invite_cache.setdefault(invite.guild.id, {})
            cache[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        """Remove invite from cache when deleted."""
        if invite.guild:
            self._invite_cache.get(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Detect which invite was used and log it."""
        if member.bot:
            return
        invite = await self._find_used_invite(member.guild)

        embed = discord.Embed(
            title="🔗 Member Joined via Invite",
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"{member.mention} (`{member.id}`)", inline=False)

        if invite:
            inviter = invite.inviter
            inviter_str = f"{inviter.mention} (`{inviter.id}`)" if inviter else "Unknown"
            embed.add_field(name="Invited By", value=inviter_str, inline=True)
            embed.add_field(name="Invite Code", value=f"`{invite.code}`", inline=True)
            embed.add_field(name="Total Uses", value=f"`{invite.uses}`", inline=True)
            if invite.max_uses:
                embed.add_field(name="Max Uses", value=f"`{invite.max_uses}`", inline=True)
        else:
            embed.add_field(name="Invited By", value="*Could not determine (vanity URL or no permission)*", inline=False)

        # Route through ServerLogsCog using "member_join" event so it respects the guild's log channel
        cog = self.bot.get_cog("ServerLogsCog")
        if cog:
            await cog.logger._send(member.guild, "member_join", embed)

    # ── Commands ──────────────────────────────────────────────────────────────

    invite_group = app_commands.Group(name="invites", description="Invite tracker commands")

    @invite_group.command(name="leaderboard", description="Show the top inviters in this server")
    @app_commands.default_permissions(manage_guild=True)
    async def invite_leaderboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            invites = await interaction.guild.invites()
        except discord.Forbidden:
            await interaction.followup.send("❌ I need the **Manage Server** permission to view invites.", ephemeral=True)
            return

        # Aggregate uses by inviter
        counts: dict[int, tuple[str, int]] = {}
        for inv in invites:
            if inv.inviter:
                uid = inv.inviter.id
                name = str(inv.inviter)
                counts[uid] = (name, counts.get(uid, (name, 0))[1] + (inv.uses or 0))

        if not counts:
            await interaction.followup.send("No invite data found.", ephemeral=True)
            return

        sorted_inviters = sorted(counts.values(), key=lambda x: x[1], reverse=True)[:10]
        lines = [f"`{i+1}.` **{name}** — `{uses}` invites" for i, (name, uses) in enumerate(sorted_inviters)]

        embed = discord.Embed(
            title="🏆 Invite Leaderboard",
            description="\n".join(lines),
            color=0xF1C40F,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InviteTrackerCog(bot))
    print("🔗 Invite Tracker loaded!")
