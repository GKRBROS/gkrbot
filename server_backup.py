"""
server_backup.py — Full Server Backup and Chat Restoration System

Features:
  • /backup save    — Snapshots the server structure AND the last 1000 messages of every channel into a .json.gz file, sending it to the owner.
  • /backup restore — Takes a .json.gz file, wipes the server, rebuilds structure, and replays messages using Webhooks (with a 5 second delay).
"""

from __future__ import annotations

import asyncio
import datetime
import gzip
import io
import json
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Delay between operations to avoid rate limits (User requested 5 sec increase)
DELAY_MESSAGE = 5.0
DELAY_STRUCTURE = 5.0

# How many messages to backup per channel
MESSAGE_LIMIT = 500


# ---------------------------------------------------------------------------
# Owner Check
# ---------------------------------------------------------------------------

def is_bot_owner():
    def predicate(interaction: discord.Interaction) -> bool:
        owner_id_str = os.getenv("OWNER_DISCORD_ID")
        if not owner_id_str:
            return False
        return interaction.user.id == int(owner_id_str)
    return app_commands.check(predicate)


# ---------------------------------------------------------------------------
# Backup Helpers
# ---------------------------------------------------------------------------

def _serialize_permissions(overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite]) -> dict:
    result = {}
    for target, overwrite in overwrites.items():
        if isinstance(target, discord.Member):
            continue
        allow, deny = overwrite.pair()
        result[target.name] = {"allow": allow.value, "deny": deny.value}
    return result


async def _snapshot_full_backup(guild: discord.Guild, progress_msg: discord.Message) -> dict:
    """Captures roles, channels, overwrites, AND messages."""
    roles_data = []
    for role in sorted(guild.roles, key=lambda r: r.position):
        if role.is_bot_managed() or role.is_integration() or role.is_premium_subscriber():
            continue
        roles_data.append({
            "name": role.name,
            "color": role.color.value,
            "permissions": role.permissions.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "position": role.position,
        })

    categories_data = []
    text_channels_data = []
    voice_channels_data = []

    # Prepare to fetch messages
    text_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]
    
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            categories_data.append({
                "name": ch.name,
                "position": ch.position,
                "overwrites": _serialize_permissions(ch.overwrites),
            })
        elif isinstance(ch, discord.VoiceChannel):
            voice_channels_data.append({
                "name": ch.name,
                "bitrate": ch.bitrate,
                "user_limit": ch.user_limit,
                "position": ch.position,
                "category": ch.category.name if ch.category else None,
                "overwrites": _serialize_permissions(ch.overwrites),
            })

    # Fetch messages for text channels
    for idx, ch in enumerate(text_channels):
        await asyncio.sleep(1.0)
        try:
            await progress_msg.edit(embed=discord.Embed(
                title="📦 Generating Backup...",
                description=f"Fetching messages for `#{ch.name}` ({idx + 1}/{len(text_channels)})...",
                color=0x00AAFF
            ))
        except:
            pass

        messages = []
        try:
            # We reverse so chronological order is maintained (oldest first in list)
            async for msg in ch.history(limit=MESSAGE_LIMIT, oldest_first=False):
                attachments = [a.url for a in msg.attachments]
                messages.append({
                    "author_name": msg.author.display_name,
                    "author_avatar": msg.author.display_avatar.url if msg.author.display_avatar else None,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat(),
                    "attachments": attachments
                })
            messages.reverse()
        except discord.Forbidden:
            pass

        text_channels_data.append({
            "name": ch.name,
            "topic": ch.topic or "",
            "slowmode_delay": ch.slowmode_delay,
            "nsfw": ch.nsfw,
            "position": ch.position,
            "category": ch.category.name if ch.category else None,
            "overwrites": _serialize_permissions(ch.overwrites),
            "messages": messages
        })

    return {
        "server": {
            "name": guild.name,
            "verification_level": guild.verification_level.value,
        },
        "roles": roles_data,
        "categories": categories_data,
        "text_channels": text_channels_data,
        "voice_channels": voice_channels_data,
    }


# ---------------------------------------------------------------------------
# Restore Helpers
# ---------------------------------------------------------------------------

def _build_overwrite_dict(overwrites_raw: dict, guild: discord.Guild) -> dict[discord.Role, discord.PermissionOverwrite]:
    result = {}
    for role_name, bits in overwrites_raw.items():
        if role_name == "@everyone":
            target = guild.default_role
        else:
            target = discord.utils.get(guild.roles, name=role_name)
        if target is None:
            continue
        allow = discord.Permissions(bits["allow"])
        deny = discord.Permissions(bits["deny"])
        ow = discord.PermissionOverwrite.from_pair(allow, deny)
        result[target] = ow
    return result


# ---------------------------------------------------------------------------
# Wipe confirmation view
# ---------------------------------------------------------------------------

class RestoreConfirmView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        self.guild = guild
        self.confirmed = False

    @discord.ui.button(label="⚠️ WIPE & RESTORE", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        owner_id_str = os.getenv("OWNER_DISCORD_ID")
        if not owner_id_str or interaction.user.id != int(owner_id_str):
            await interaction.response.send_message("❌ Only the Bot Owner can confirm this.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.send_message("🔥 Wiping server and starting restore…", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message("✅ Cancelled. Nothing was changed.", ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class ServerBackupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    backup_group = app_commands.Group(
        name="backup",
        description="Full Server Backup System including Chat Messages",
    )

    @backup_group.command(name="save", description="Backup the entire server structure AND chat history")
    @is_bot_owner()
    async def backup_save(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        embed = discord.Embed(
            title="📦 Generating Backup...",
            description="Starting message history fetch. This will take a while depending on server size.",
            color=0x00AAFF
        )
        progress_msg = await interaction.followup.send(embed=embed, ephemeral=True)

        try:
            payload = await _snapshot_full_backup(guild, progress_msg)
        except Exception as e:
            await progress_msg.edit(embed=discord.Embed(title="❌ Backup Failed", description=str(e), color=0xFF0000))
            return

        await progress_msg.edit(embed=discord.Embed(
            title="📦 Compressing Backup...",
            description="Compressing JSON payload into .gz format...",
            color=0x00AAFF
        ))

        # Compress
        raw_json = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        compressed_data = gzip.compress(raw_json)

        file = discord.File(
            fp=io.BytesIO(compressed_data),
            filename=f"{guild.name.replace(' ', '_')}_backup_{datetime.datetime.utcnow().strftime('%Y%m%d')}.json.gz",
        )

        try:
            await interaction.user.send(
                content="✅ **Server Backup Complete**\nHere is your securely compressed backup file. Keep this safe!",
                file=file
            )
            await progress_msg.edit(embed=discord.Embed(
                title="✅ Backup Sent",
                description="The backup file has been DMed to you securely.",
                color=0x2ECC71
            ))
        except discord.Forbidden:
            await progress_msg.edit(embed=discord.Embed(
                title="❌ DM Failed",
                description="I cannot DM you the backup file. Please enable server DMs.",
                color=0xFF0000
            ))

    @backup_group.command(name="restore", description="Restore a server from a .json.gz backup file")
    @app_commands.describe(file="The .json.gz backup file to restore from")
    @is_bot_owner()
    async def backup_restore(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
        await interaction.response.defer(ephemeral=True)

        if not file.filename.endswith(".json.gz"):
            await interaction.followup.send("❌ Please upload a `.json.gz` backup file.", ephemeral=True)
            return

        try:
            raw_gz = await file.read()
            raw_json = gzip.decompress(raw_gz).decode("utf-8")
            payload = json.loads(raw_json)
        except Exception as e:
            await interaction.followup.send(f"❌ Could not decompress or parse backup file: {e}", ephemeral=True)
            return

        guild = interaction.guild

        view = RestoreConfirmView(guild)
        embed = discord.Embed(
            title="⚠️ DANGER: Full Server Restore",
            description=(
                "This will **permanently delete** all channels and roles from this server, "
                "rebuild them from the backup, and replay all saved chat messages.\n\n"
                "**This process will take a long time and cannot be undone.** Are you sure?"
            ),
            color=0xFF0000,
        )
        msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if not view.confirmed:
            return

        # ── Wipe ─────────────────────────────────────────────────────────────
        for ch in list(guild.channels):
            try:
                await ch.delete(reason="GKR Restore Wipe")
                await asyncio.sleep(0.5)
            except Exception:
                pass

        for role in list(guild.roles):
            if role.is_default() or role.is_bot_managed() or role.is_integration() or role.is_premium_subscriber():
                continue
            if role >= guild.me.top_role:
                continue
            try:
                await role.delete(reason="GKR Restore Wipe")
                await asyncio.sleep(0.5)
            except Exception:
                pass

        # ── Rebuild Roles ────────────────────────────────────────────────────
        for role_data in [r for r in payload.get("roles", []) if r["name"] != "@everyone"]:
            try:
                await guild.create_role(
                    name=role_data["name"],
                    color=discord.Color(role_data["color"]),
                    permissions=discord.Permissions(role_data["permissions"]),
                    hoist=role_data["hoist"],
                    mentionable=role_data["mentionable"],
                    reason="GKR Backup Restore"
                )
            except:
                pass
            await asyncio.sleep(DELAY_STRUCTURE)

        # ── Rebuild Categories ───────────────────────────────────────────────
        cat_map = {}
        for cat_data in payload.get("categories", []):
            try:
                overwrites = _build_overwrite_dict(cat_data.get("overwrites", {}), guild)
                new_cat = await guild.create_category(
                    name=cat_data["name"],
                    overwrites=overwrites,
                    reason="GKR Backup Restore"
                )
                cat_map[cat_data["name"]] = new_cat
            except:
                pass
            await asyncio.sleep(DELAY_STRUCTURE)

        # ── Rebuild Channels & Replay Messages ───────────────────────────────
        for ch_data in payload.get("voice_channels", []):
            try:
                category = cat_map.get(ch_data.get("category")) if ch_data.get("category") else None
                overwrites = _build_overwrite_dict(ch_data.get("overwrites", {}), guild)
                await guild.create_voice_channel(
                    name=ch_data["name"],
                    bitrate=min(ch_data.get("bitrate", 64000), guild.bitrate_limit),
                    user_limit=ch_data.get("user_limit", 0),
                    category=category,
                    overwrites=overwrites,
                    reason="GKR Backup Restore",
                )
            except:
                pass
            await asyncio.sleep(DELAY_STRUCTURE)

        for ch_data in payload.get("text_channels", []):
            try:
                category = cat_map.get(ch_data.get("category")) if ch_data.get("category") else None
                overwrites = _build_overwrite_dict(ch_data.get("overwrites", {}), guild)
                new_ch = await guild.create_text_channel(
                    name=ch_data["name"],
                    topic=ch_data.get("topic") or None,
                    slowmode_delay=ch_data.get("slowmode_delay", 0),
                    nsfw=ch_data.get("nsfw", False),
                    category=category,
                    overwrites=overwrites,
                    reason="GKR Backup Restore",
                )
                await asyncio.sleep(DELAY_STRUCTURE)

                messages = ch_data.get("messages", [])
                if messages and isinstance(new_ch, discord.TextChannel):
                    try:
                        webhook = await new_ch.create_webhook(name="GKR Restore")
                        for m in messages:
                            content = m.get("content", "")
                            # Append attachments as links
                            attachments = m.get("attachments", [])
                            if attachments:
                                content += "\n" + "\n".join(attachments)

                            if not content.strip():
                                content = "*[Empty/Unsupported Message]*"

                            # Send via webhook
                            await webhook.send(
                                content=content[:2000],
                                username=m.get("author_name", "Unknown"),
                                avatar_url=m.get("author_avatar") or discord.Embed.Empty,
                            )
                            await asyncio.sleep(DELAY_MESSAGE)
                        
                        await webhook.delete()
                    except Exception as e:
                        print(f"Failed to restore messages in {new_ch.name}: {e}")

            except Exception as e:
                print(f"Failed to create text channel {ch_data.get('name')}: {e}")
                pass
            await asyncio.sleep(DELAY_STRUCTURE)

        try:
            summary_ch = guild.system_channel or next((c for c in guild.text_channels), None)
            if summary_ch:
                await summary_ch.send("✅ **Server Restore Complete!**")
        except:
            pass

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerBackupCog(bot))
    print("📦 Server Backup System loaded!")
