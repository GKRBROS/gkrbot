"""
automod_badge.py
────────────────
Creates placeholder AutoMod rules across all guilds so the bot qualifies
for Discord's "Uses AutoMod" profile badge (requires ≥100 active rules).

Usage
-----
  python automod_badge.py          # creates rules
  DISCORD_TOKEN=... python automod_badge.py

Slash command (bot owner only):
  /clean_automod                   # deletes all badge-placeholder rules

discord.py v2.3+   |   no privileged intents needed
"""

import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands

# ── Token ─────────────────────────────────────────────────────────────────────
TOKEN: str = os.getenv("DISCORD_TOKEN", "PASTE_BOT_TOKEN_HERE")

# ── Tuning ────────────────────────────────────────────────────────────────────
GLOBAL_TARGET   = 100          # badge threshold
GLOBAL_CAP      = 105          # stop after this many to give a safe buffer
RULE_DELAY      = 1.5          # seconds between API calls to avoid rate limits
BADGE_PREFIX    = "automod_badge_check_"

# Per-server Discord limits (as of 2024)
MAX_KEYWORD_RULES = 6
MAX_MENTION_RULES = 1          # 1 mention-spam rule per server

# ── AutoMod helpers ───────────────────────────────────────────────────────────

def _has_permission(guild: discord.Guild, bot_member: discord.Member) -> bool:
    perms = guild.me.guild_permissions
    return perms.administrator or perms.manage_guild


def _existing_counts(rules: list[discord.AutoModRule]) -> dict:
    """Count how many of each trigger type already exist."""
    counts = {
        discord.AutoModRuleTriggerType.keyword:      0,
        discord.AutoModRuleTriggerType.mention_spam: 0,
    }
    for r in rules:
        t = r.trigger.type
        if t in counts:
            counts[t] += 1
    return counts


async def _create_keyword_rule(guild: discord.Guild, slot: int) -> bool:
    """Create one keyword placeholder rule. Returns True on success."""
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
        print(f"    ⚠  Keyword slot {slot} failed: {e.status} {e.text!r}")
        return False


async def _create_mention_rule(guild: discord.Guild) -> bool:
    """Create one mention-spam placeholder rule. Returns True on success."""
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
        print(f"    ⚠  MentionSpam rule failed: {e.status} {e.text!r}")
        return False


# ── Bot ───────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


@bot.event
async def on_ready() -> None:
    print(f"\n{'─'*60}")
    print(f"  Logged in as {bot.user} ({bot.user.id})")
    print(f"  Guilds: {len(bot.guilds)}")
    print(f"  Target: {GLOBAL_TARGET} active AutoMod rules")
    print(f"{'─'*60}\n")

    # Sync slash commands
    try:
        synced = await tree.sync()
        print(f"  Synced {len(synced)} slash command(s).\n")
    except Exception as e:
        print(f"  Slash sync error: {e}\n")

    global_count   = 0   # running total (existing + newly created)
    global_created = 0   # rules we created this run
    guilds_used    = 0

    for guild in bot.guilds:
        if global_count >= GLOBAL_CAP:
            print(f"🏁 Global cap {GLOBAL_CAP} reached — stopping early.\n")
            break

        print(f"[{guild.name}]  id={guild.id}")

        # Permission check
        if not _has_permission(guild, guild.me):
            print(f"  ✗ Missing manage_guild / administrator — skipping.\n")
            continue

        # Fetch existing rules
        try:
            existing_rules = await guild.fetch_automod_rules()
            await asyncio.sleep(RULE_DELAY)
        except discord.HTTPException as e:
            print(f"  ✗ Could not fetch rules: {e} — skipping.\n")
            continue

        counts     = _existing_counts(existing_rules)
        kw_have    = counts[discord.AutoModRuleTriggerType.keyword]
        men_have   = counts[discord.AutoModRuleTriggerType.mention_spam]
        guild_total = len(existing_rules)

        print(f"  Existing rules: {guild_total} total  "
              f"(keyword={kw_have}, mention_spam={men_have})")

        global_count += guild_total
        guild_created = 0

        # ── Create Keyword rules up to server limit ──────────────────────────
        for slot in range(kw_have + 1, MAX_KEYWORD_RULES + 1):
            if global_count >= GLOBAL_CAP:
                break
            ok = await _create_keyword_rule(guild, slot)
            await asyncio.sleep(RULE_DELAY)
            if ok:
                global_count  += 1
                global_created += 1
                guild_created  += 1
                print(f"  ✓ Created keyword rule slot {slot}  "
                      f"[total so far: {global_count}]")

        # ── Create MentionSpam rule if missing ───────────────────────────────
        if men_have == 0 and global_count < GLOBAL_CAP:
            ok = await _create_mention_rule(guild)
            await asyncio.sleep(RULE_DELAY)
            if ok:
                global_count  += 1
                global_created += 1
                guild_created  += 1
                print(f"  ✓ Created mention_spam rule  "
                      f"[total so far: {global_count}]")

        if guild_created:
            guilds_used += 1
        print(f"  → Created {guild_created} rule(s) this guild.\n")

    # ── Summary ──────────────────────────────────────────────────────────────
    badge_ok = "✅  ELIGIBLE" if global_count >= GLOBAL_TARGET else "❌  NOT YET ELIGIBLE"
    print(f"\n{'═'*60}")
    print(f"  BADGE STATUS : {badge_ok}")
    print(f"  Total active AutoMod rules tracked : {global_count}")
    print(f"  Rules created this run             : {global_created}")
    print(f"  Guilds that received new rules     : {guilds_used}")
    print(f"{'═'*60}\n")


# ── /automod_status  (owner-only) ────────────────────────────────────────────

@tree.command(name="automod_status", description="[Owner] List ALL guilds with their AutoMod rule status.")
async def automod_status(interaction: discord.Interaction) -> None:
    """Scan every guild the bot is in and show AutoMod rule counts per server."""
    app_info = await bot.application_info()
    if interaction.user.id != app_info.owner.id:
        await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    grand_total  = 0
    grand_badge  = 0
    grand_active = 0
    guild_data   = []   # list of (has_automod, line_str)

    for guild in bot.guilds:
        gname = discord.utils.escape_markdown(guild.name)
        try:
            rules = await guild.fetch_automod_rules()
            await asyncio.sleep(0.5)
        except discord.HTTPException as e:
            guild_data.append((False, f"❓ **{gname}** `{guild.id}` — fetch failed ({e.status})"))
            continue

        total       = len(rules)
        active      = sum(1 for r in rules if r.enabled)
        badge_rules = [r for r in rules if r.name.startswith(BADGE_PREFIX)]
        other       = total - len(badge_rules)
        kw          = sum(1 for r in rules if r.trigger.type == discord.AutoModRuleTriggerType.keyword)
        men         = sum(1 for r in rules if r.trigger.type == discord.AutoModRuleTriggerType.mention_spam)

        grand_total  += total
        grand_badge  += len(badge_rules)
        grand_active += active

        if total == 0:
            icon = "🔴"   # no automod at all
            detail = "No AutoMod rules"
        elif active == 0:
            icon = "🟡"   # rules exist but all disabled
            detail = f"`{total}` rules (all disabled)"
        else:
            icon = "🟢"   # has active automod
            detail = (
                f"`{total}` rules (`{active}` active) | "
                f"kw=`{kw}` men=`{men}` badge=`{len(badge_rules)}` other=`{other}`"
            )

        has_automod = active > 0
        guild_data.append((has_automod, f"{icon} **{gname}** `{guild.id}` — {detail}"))

    # Sort: 🟢 active first, 🟡 disabled second, 🔴 none last
    guild_data.sort(key=lambda x: (not x[0], x[1]))

    # Count groups
    has_active  = sum(1 for has, _ in guild_data if has)
    no_active   = len(guild_data) - has_active
    badge_ok    = grand_total >= GLOBAL_TARGET

    summary = (
        f"{'✅ BADGE ELIGIBLE' if badge_ok else '❌ NOT YET ELIGIBLE'} "
        f"— **{grand_total}/{GLOBAL_TARGET}** total rules | **{grand_active}** active\n"
        f"🟢 AutoMod ON: **{has_active}** servers | 🔴 No AutoMod: **{no_active}** servers\n"
        f"Badge rules: **{grand_badge}** | Other rules: **{grand_total - grand_badge}**\n"
        f"Total servers scanned: **{len(bot.guilds)}**\n\n"
        f"**Legend:** 🟢 active rules · 🟡 rules exist but disabled · 🔴 no rules · ❓ fetch failed\n"
        "─────────────────────────────\n"
    )

    lines    = [line for _, line in guild_data]
    all_text = summary + "\n".join(lines)

    # Chunk into 4000-char pages
    pages     = []
    cur_chunk = summary
    for line in lines:
        if len(cur_chunk) + len(line) + 1 > 4000:
            pages.append(cur_chunk)
            cur_chunk = ""
        cur_chunk += line + "\n"
    if cur_chunk:
        pages.append(cur_chunk)

    total_pages = len(pages)
    embeds = [
        discord.Embed(
            title=f"🛡️ AutoMod Status — Page {i+1}/{total_pages}",
            description=page,
            color=0x57F287 if badge_ok else 0xED4245,
        )
        for i, page in enumerate(pages)
    ]

    # Send up to 10 embeds per followup (Discord limit)
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        if i == 0:
            await interaction.followup.send(embeds=batch, ephemeral=True)
        else:
            await interaction.followup.send(embeds=batch, ephemeral=True)


# ── /clean_automod  (owner-only) ──────────────────────────────────────────────

@tree.command(name="clean_automod", description="[Owner] Delete all AutoMod badge placeholder rules.")
async def clean_automod(interaction: discord.Interaction) -> None:
    """Remove every rule whose name starts with the BADGE_PREFIX across all guilds."""
    app_info = await bot.application_info()
    if interaction.user.id != app_info.owner.id:
        await interaction.response.send_message(
            "❌ Owner-only command.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    removed = 0
    errors  = 0

    for guild in bot.guilds:
        try:
            rules = await guild.fetch_automod_rules()
            await asyncio.sleep(RULE_DELAY)
        except discord.HTTPException:
            continue

        for rule in rules:
            if rule.name.startswith(BADGE_PREFIX):
                try:
                    await rule.delete(reason="AutoMod badge cleanup requested by owner")
                    removed += 1
                    await asyncio.sleep(RULE_DELAY)
                    print(f"  🗑  Deleted '{rule.name}' in {guild.name}")
                except discord.HTTPException as e:
                    errors += 1
                    print(f"  ⚠  Could not delete '{rule.name}' in {guild.name}: {e}")

    await interaction.followup.send(
        f"✅ Cleanup done — removed **{removed}** placeholder rule(s), "
        f"{errors} error(s).",
        ephemeral=True,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if TOKEN == "PASTE_BOT_TOKEN_HERE":
        raise ValueError("Set DISCORD_TOKEN env var or replace PASTE_BOT_TOKEN_HERE in the file.")
    bot.run(TOKEN)
