"""
automod_booster.py — AutoMod Badge 100-Rule Booster
Generates AutoMod keyword & mention rules across all guilds until 100 rules are active.
"""

import asyncio
import os
import sys
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Ensure safe printing on Windows consoles
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TARGET_RULES = 100

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


def safe_name(name: str) -> str:
    """Return an ASCII-safe representation of a server name for logging."""
    return name.encode("ascii", "replace").decode("ascii")


@bot.event
async def on_ready():
    print(f"=== AutoMod Booster Online ===")
    print(f"Bot Account: {bot.user} (ID: {bot.user.id})")
    print(f"Total Servers Joined: {len(bot.guilds)}\n")

    # Step 1: Pre-scan existing rules across all servers
    existing_rule_count = 0
    guild_rule_map = {}

    print("--- Scanning Existing AutoMod Rules ---")
    for g in bot.guilds:
        s_name = safe_name(g.name)[:28]
        try:
            rules = await g.fetch_automod_rules()
            guild_rule_map[g.id] = rules
            existing_rule_count += len(rules)
            print(f"  * {s_name:<28} :: {len(rules)} existing rules")
        except discord.Forbidden:
            print(f"  * {s_name:<28} :: [SKIP] No Manage Server permission")
            guild_rule_map[g.id] = None
        except discord.HTTPException as exc:
            print(f"  * {s_name:<28} :: [WARN] HTTP error {exc.status}")
            guild_rule_map[g.id] = None

    print(f"\nInitial Total Active Rules: {existing_rule_count}/{TARGET_RULES}\n")

    if existing_rule_count >= TARGET_RULES:
        print(f"SUCCESS: Already at or above target ({existing_rule_count} rules)! Badge requirements met.")
        await bot.close()
        return

    # Step 2: Create rules to hit target
    total_active = existing_rule_count
    created_this_run = 0

    print("--- Creating Required Rules ---")
    for g in bot.guilds:
        if total_active >= TARGET_RULES:
            break

        rules = guild_rule_map.get(g.id)
        if rules is None:
            continue

        s_name = safe_name(g.name)[:25]
        existing_names = {r.name for r in rules}
        kw_rules = [r for r in rules if r.trigger_type == discord.AutoModRuleTriggerType.keyword]
        has_mention = any(r.trigger_type == discord.AutoModRuleTriggerType.mention_spam for r in rules)

        action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)

        # 1. Fill keyword rules up to 6 per server
        for i in range(len(kw_rules), 6):
            if total_active >= TARGET_RULES:
                break

            rule_name = f"AM-KW-{i+1}-{g.id % 1000}"
            if rule_name in existing_names:
                continue

            unique_word = f"badgetest_{i}_{int(time.time()) % 10000}"
            trigger = discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                keyword_filter=[unique_word]
            )

            try:
                await g.create_automod_rule(
                    name=rule_name,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=trigger,
                    actions=[action],
                    enabled=True,
                    reason="AutoMod Badge Milestone Rule"
                )
                total_active += 1
                created_this_run += 1
                print(f"  [+] {s_name}: Created '{rule_name}' ({total_active}/{TARGET_RULES})")
                await asyncio.sleep(1.2)
            except discord.Forbidden:
                print(f"  [!] {s_name}: Missing permission to create rule.")
                break
            except discord.HTTPException as exc:
                if exc.status == 429:
                    retry_after = getattr(exc, "retry_after", 5.0)
                    print(f"  [~] Rate limit hit. Waiting {retry_after:.1f}s...")
                    await asyncio.sleep(retry_after)
                else:
                    print(f"  [x] Error in {s_name}: {exc}")
                continue

        # 2. Add Mention-Spam rule (1 per server)
        if not has_mention and total_active < TARGET_RULES:
            rule_name = f"AM-Mention-{g.id % 1000}"
            if rule_name not in existing_names:
                trigger = discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.mention_spam,
                    mention_limit=5
                )
                try:
                    await g.create_automod_rule(
                        name=rule_name,
                        event_type=discord.AutoModRuleEventType.message_send,
                        trigger=trigger,
                        actions=[action],
                        enabled=True,
                        reason="AutoMod Badge Milestone Rule"
                    )
                    total_active += 1
                    created_this_run += 1
                    print(f"  [+] {s_name}: Created '{rule_name}' ({total_active}/{TARGET_RULES})")
                    await asyncio.sleep(1.2)
                except (discord.Forbidden, discord.HTTPException):
                    pass

    print("\n=================================")
    print(f"Finished execution!")
    print(f"New Rules Created: {created_this_run}")
    print(f"Total Active Rules: {total_active}/{TARGET_RULES}")
    print("=================================")

    await bot.close()


if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN not found in environment.")
    else:
        bot.run(TOKEN)
