"""
automod_system.py
─────────────────
AutoMod Management Cog & Profile Badge Booster.

Commands (Bot Owner Only):
  /automod_status  - List all servers, rule counts, and badge eligibility
  /automod_deploy  - Create harmless placeholder AutoMod rules across servers (up to 105 rules)
  /clean_automod   - Delete all badge placeholder rules across all servers
"""

import asyncio
import os
import discord
from discord import app_commands
from discord.ext import commands

from gkr_ui import embed_info, embed_error, embed_success

GLOBAL_TARGET = 100       # Discord badge threshold
GLOBAL_CAP = 105          # Safe buffer stop threshold
RULE_DELAY = 1.5          # Delay between Discord API calls to prevent 429
BADGE_PREFIX = "automod_badge_check_"

MAX_KEYWORD_RULES = 6
MAX_MENTION_RULES = 1


def _has_automod_perm(guild: discord.Guild) -> bool:
    perms = guild.me.guild_permissions
    return perms.administrator or perms.manage_guild


def _existing_counts(rules: list[discord.AutoModRule]) -> dict:
    counts = {
        discord.AutoModRuleTriggerType.keyword: 0,
        discord.AutoModRuleTriggerType.mention_spam: 0,
    }
    for r in rules:
        t = getattr(getattr(r, "trigger", None), "type", None)
        if t in counts:
            counts[t] += 1
    return counts


async def _create_kw_rule(guild: discord.Guild, slot: int) -> bool:
    name = f"{BADGE_PREFIX}{slot}"
    trigger = discord.AutoModTrigger(
        type=discord.AutoModRuleTriggerType.keyword,
        keyword_filter=[f"automod_placeholder_{slot}_xqz"],
    )
    action = discord.AutoModRuleAction(
        type=discord.AutoModRuleActionType.block_message,
    )
    try:
        await guild.create_automod_rule(
            name=name,
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=trigger,
            actions=[action],
            enabled=True,
            reason="AutoMod badge — placeholder rule (harmless)",
        )
        return True
    except discord.HTTPException as e:
        print(f"[{guild.name}] Keyword slot {slot} failed: {e.status} {e.text!r}")
        return False


async def _create_men_rule(guild: discord.Guild) -> bool:
    trigger = discord.AutoModTrigger(
        type=discord.AutoModRuleTriggerType.mention_spam,
        mention_limit=50,
    )
    action = discord.AutoModRuleAction(
        type=discord.AutoModRuleActionType.block_message,
    )
    try:
        await guild.create_automod_rule(
            name=f"{BADGE_PREFIX}mention_spam",
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=trigger,
            actions=[action],
            enabled=True,
            reason="AutoMod badge — mention spam placeholder (harmless)",
        )
        return True
    except discord.HTTPException as e:
        print(f"[{guild.name}] MentionSpam rule failed: {e.status} {e.text!r}")
        return False


class AutoModSystemCog(commands.Cog, name="AutoMod System"):
    """AutoMod monitoring and badge booster operations."""

    automod_group = app_commands.Group(name="automod", description="AutoMod management and badge booster")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._deploy_lock = asyncio.Lock()
        print("🛡️  AutoMod System Cog initialized")

    async def _require_owner(self, interaction: discord.Interaction) -> bool:
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                embed=embed_error("Only the bot owner can execute AutoMod administration commands.", title="Access Restricted"),
                ephemeral=True
            )
            return False
        return True

    # ── /automod status ──────────────────────────────────────────────────────

    @automod_group.command(name="status", description="[Owner] Scan all servers for AutoMod rules and badge status")
    async def automod_status(self, interaction: discord.Interaction) -> None:
        if not await self._require_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        grand_total = 0
        grand_badge = 0
        grand_active = 0
        guild_data = []

        for guild in self.bot.guilds:
            gname = discord.utils.escape_markdown(guild.name)
            if not _has_automod_perm(guild):
                guild_data.append((False, f"❓ **{gname}** `{guild.id}` — missing permissions (manage_guild)"))
                continue

            try:
                rules = await guild.fetch_automod_rules()
                await asyncio.sleep(0.4)
            except discord.HTTPException as e:
                guild_data.append((False, f"❓ **{gname}** `{guild.id}` — fetch failed ({e.status})"))
                continue

            total = len(rules)
            active = sum(1 for r in rules if r.enabled)
            badge_rules = [r for r in rules if r.name.startswith(BADGE_PREFIX)]
            other = total - len(badge_rules)
            kw = sum(1 for r in rules if getattr(getattr(r, "trigger", None), "type", None) == discord.AutoModRuleTriggerType.keyword)
            men = sum(1 for r in rules if getattr(getattr(r, "trigger", None), "type", None) == discord.AutoModRuleTriggerType.mention_spam)

            grand_total += total
            grand_badge += len(badge_rules)
            grand_active += active

            if total == 0:
                icon = "🔴"
                detail = "No AutoMod rules"
            elif active == 0:
                icon = "🟡"
                detail = f"`{total}` rules (all disabled)"
            else:
                icon = "🟢"
                detail = f"`{total}` rules (`{active}` active) | kw=`{kw}` men=`{men}` badge=`{len(badge_rules)}` other=`{other}`"

            has_automod = active > 0
            guild_data.append((has_automod, f"{icon} **{gname}** `{guild.id}` — {detail}"))

        # Sort: active first, then inactive
        guild_data.sort(key=lambda x: (not x[0], x[1]))

        has_active = sum(1 for has, _ in guild_data if has)
        no_active = len(guild_data) - has_active
        badge_ok = grand_total >= GLOBAL_TARGET

        summary = (
            f"{'✅ **BADGE ELIGIBLE**' if badge_ok else '❌ **NOT YET ELIGIBLE**'} "
            f"— **{grand_total}/{GLOBAL_TARGET}** total rules (Active: `{grand_active}`)\n"
            f"🟢 AutoMod ON: **{has_active}** servers | 🔴 No AutoMod: **{no_active}** servers\n"
            f"Badge placeholder rules: **{grand_badge}** | Other server rules: **{grand_total - grand_badge}**\n"
            f"Total servers scanned: **{len(self.bot.guilds)}**\n\n"
            f"**Legend:** 🟢 Active rules · 🟡 Rules exist but disabled · 🔴 No rules · ❓ No permission\n"
            "─────────────────────────────\n"
        )

        lines = [line for _, line in guild_data]

        pages = []
        cur_chunk = summary
        for line in lines:
            if len(cur_chunk) + len(line) + 1 > 3900:
                pages.append(cur_chunk)
                cur_chunk = ""
            cur_chunk += line + "\n"
        if cur_chunk:
            pages.append(cur_chunk)

        total_pages = len(pages)
        embeds = []
        for i, page in enumerate(pages):
            embed = discord.Embed(
                title=f"🛡️ AutoMod Status Across Servers ({i+1}/{total_pages})",
                description=page,
                color=0x57F287 if badge_ok else 0xED4245,
            )
            embeds.append(embed)

        for i in range(0, len(embeds), 10):
            batch = embeds[i:i+10]
            await interaction.followup.send(embeds=batch, ephemeral=True)

    # ── /automod deploy ──────────────────────────────────────────────────────

    @automod_group.command(name="deploy", description="[Owner] Create placeholder AutoMod rules across servers to reach 100 rules")
    async def automod_deploy(self, interaction: discord.Interaction) -> None:
        if not await self._require_owner(interaction):
            return

        if self._deploy_lock.locked():
            await interaction.response.send_message(
                embed=embed_error("AutoMod deployment is already running in background.", title="Already Running"),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=embed_info(
                "🚀 AutoMod Deployment Started",
                f"Starting AutoMod rule creation across servers to reach **{GLOBAL_CAP}** total active rules.\n"
                f"This runs safely with a `{RULE_DELAY}s` delay between actions to avoid rate limits.\n"
                "You can run `/automod_status` anytime to check live progress."
            ),
            ephemeral=True
        )

        async def _run_deploy():
            async with self._deploy_lock:
                global_count = 0
                global_created = 0
                guilds_used = 0

                # Pre-scan existing rules
                for g in self.bot.guilds:
                    if _has_automod_perm(g):
                        try:
                            rules = await g.fetch_automod_rules()
                            global_count += len(rules)
                            await asyncio.sleep(0.5)
                        except Exception:
                            pass

                print(f"[AutoMod Deploy] Starting run. Current active rules: {global_count}/{GLOBAL_CAP}")

                for guild in self.bot.guilds:
                    if global_count >= GLOBAL_CAP:
                        print(f"[AutoMod Deploy] Reached target {GLOBAL_CAP} rules. Stopping.")
                        break

                    if not _has_automod_perm(guild):
                        continue

                    try:
                        existing_rules = await guild.fetch_automod_rules()
                        await asyncio.sleep(RULE_DELAY)
                    except discord.HTTPException:
                        continue

                    counts = _existing_counts(existing_rules)
                    kw_have = counts[discord.AutoModRuleTriggerType.keyword]
                    men_have = counts[discord.AutoModRuleTriggerType.mention_spam]
                    guild_created = 0

                    # Create keywords up to 6
                    for slot in range(kw_have + 1, MAX_KEYWORD_RULES + 1):
                        if global_count >= GLOBAL_CAP:
                            break
                        ok = await _create_kw_rule(guild, slot)
                        await asyncio.sleep(RULE_DELAY)
                        if ok:
                            global_count += 1
                            global_created += 1
                            guild_created += 1

                    # Create mention spam up to 1
                    if men_have == 0 and global_count < GLOBAL_CAP:
                        ok = await _create_men_rule(guild)
                        await asyncio.sleep(RULE_DELAY)
                        if ok:
                            global_count += 1
                            global_created += 1
                            guild_created += 1

                    if guild_created:
                        guilds_used += 1
                        print(f"[AutoMod Deploy] {guild.name}: created {guild_created} rules. Global total: {global_count}")

                print(f"[AutoMod Deploy] Completed. Created {global_created} rules across {guilds_used} guilds. Total: {global_count}")

        asyncio.create_task(_run_deploy())

    # ── /automod clean ───────────────────────────────────────────────────────

    @automod_group.command(name="clean", description="[Owner] Delete all badge placeholder AutoMod rules")
    async def clean_automod(self, interaction: discord.Interaction) -> None:
        if not await self._require_owner(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        removed = 0
        errors = 0

        for guild in self.bot.guilds:
            if not _has_automod_perm(guild):
                continue

            try:
                rules = await guild.fetch_automod_rules()
                await asyncio.sleep(0.5)
            except discord.HTTPException:
                continue

            for rule in rules:
                if rule.name.startswith(BADGE_PREFIX):
                    try:
                        await rule.delete(reason="AutoMod badge cleanup requested by owner")
                        removed += 1
                        await asyncio.sleep(RULE_DELAY)
                    except discord.HTTPException:
                        errors += 1

        await interaction.followup.send(
            embed=embed_success(
                "Cleanup Finished",
                f"Successfully deleted **{removed}** placeholder rule(s) across servers.\nErrors encountered: `{errors}`"
            ),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoModSystemCog(bot))
