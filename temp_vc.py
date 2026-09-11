"""
temp_vc.py – Temporary Voice Channel (Auto-VC) system for GKR Bot.

Features:
  • Full 18-button control panel (Name, Limit, Lock, Unlock, Hide, Unhide,
    Waiting, Chat, Trust, Untrust, Invite, Kick, Region, Ban, Unban,
    Claim, Transfer, Delete)
  • Auto-cleanup on bot restart (orphaned temp VCs are deleted)
  • Per-channel ban list (stored in DB)
  • Trust/Untrust whitelist (stored in DB)
  • Waiting room mode
  • Region picker dropdown
  • Futuristic embed UI with animated/custom emojis
"""

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import sqlite3
import os
import datetime
from bot_config import BOT_NAME
from typing import Optional, List, Dict, Union, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "gkr_bot.db")

# ─── Voice region choices ─────────────────────────────────────────────────────
REGIONS = [
    ("🌐  Automatic",       None),
    ("🇺🇸  US East",         "us-east"),
    ("🇺🇸  US West",         "us-west"),
    ("🇺🇸  US Central",      "us-central"),
    ("🇺🇸  US South",        "us-south"),
    ("🇬🇧  Europe",          "europe"),
    ("🇸🇬  Singapore",       "singapore"),
    ("🇯🇵  Japan",           "japan"),
    ("🇦🇺  Sydney",          "sydney"),
    ("🇧🇷  Brazil",          "brazil"),
    ("🇮🇳  India",           "india"),
    ("🇰🇷  South Korea",     "southkorea"),
    ("🇿🇦  South Africa",    "southafrica"),
    ("🇭🇰  Hong Kong",       "hongkong"),
    ("🇷🇺  Russia",          "russia"),
]


# ─── Database ──────────────────────────────────────────────────────────────────

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tempvc_hubs (
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL PRIMARY KEY,
                category_id INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tempvc_channels (
                channel_id  INTEGER NOT NULL PRIMARY KEY,
                guild_id    INTEGER NOT NULL,
                owner_id    INTEGER NOT NULL,
                locked      INTEGER NOT NULL DEFAULT 0,
                hidden      INTEGER NOT NULL DEFAULT 0,
                waiting     INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tempvc_banned (
                channel_id  INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tempvc_trusted (
                channel_id  INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tempvc_cohosts (
                channel_id  INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        conn.commit()


def get_hubs(guild_id: int):
    with _db() as conn:
        rows = conn.execute(
            "SELECT channel_id FROM tempvc_hubs WHERE guild_id = ?", (guild_id,)
        ).fetchall()
    return [r["channel_id"] for r in rows]


def add_hub(guild_id: int, channel_id: int, category_id: int):
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tempvc_hubs (guild_id, channel_id, category_id) VALUES (?,?,?)",
            (guild_id, channel_id, category_id),
        )
        conn.commit()


def remove_hub(guild_id: int, channel_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM tempvc_hubs WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
        conn.commit()


def add_temp_channel(channel_id: int, guild_id: int, owner_id: int):
    with _db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tempvc_channels (channel_id, guild_id, owner_id) VALUES (?,?,?)",
            (channel_id, guild_id, owner_id),
        )
        conn.commit()


def remove_temp_channel(channel_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM tempvc_channels WHERE channel_id=?", (channel_id,))
        conn.execute("DELETE FROM tempvc_banned WHERE channel_id=?", (channel_id,))
        conn.execute("DELETE FROM tempvc_trusted WHERE channel_id=?", (channel_id,))
        conn.execute("DELETE FROM tempvc_cohosts WHERE channel_id=?", (channel_id,))
        conn.commit()


def get_temp_channel(channel_id: int):
    with _db() as conn:
        return conn.execute("SELECT * FROM tempvc_channels WHERE channel_id=?", (channel_id,)).fetchone()


def get_all_temp_channels():
    with _db() as conn:
        return conn.execute("SELECT * FROM tempvc_channels").fetchall()


def get_owner(channel_id: int):
    row = get_temp_channel(channel_id)
    return row["owner_id"] if row else None


def set_owner(channel_id: int, owner_id: int):
    with _db() as conn:
        conn.execute("UPDATE tempvc_channels SET owner_id=? WHERE channel_id=?", (owner_id, channel_id))
        conn.commit()


def ban_user(channel_id: int, user_id: int):
    with _db() as conn:
        conn.execute("INSERT OR IGNORE INTO tempvc_banned (channel_id, user_id) VALUES (?,?)", (channel_id, user_id))
        conn.commit()


def unban_user(channel_id: int, user_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM tempvc_banned WHERE channel_id=? AND user_id=?", (channel_id, user_id))
        conn.commit()


def get_banned(channel_id: int):
    with _db() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM tempvc_banned WHERE channel_id=?", (channel_id,)).fetchall()]


def trust_user(channel_id: int, user_id: int):
    with _db() as conn:
        conn.execute("INSERT OR IGNORE INTO tempvc_trusted (channel_id, user_id) VALUES (?,?)", (channel_id, user_id))
        conn.commit()


def untrust_user(channel_id: int, user_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM tempvc_trusted WHERE channel_id=? AND user_id=?", (channel_id, user_id))
        conn.commit()


def get_trusted(channel_id: int):
    with _db() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM tempvc_trusted WHERE channel_id=?", (channel_id,)).fetchall()]


def add_cohost(channel_id: int, user_id: int):
    with _db() as conn:
        conn.execute("INSERT OR IGNORE INTO tempvc_cohosts (channel_id, user_id) VALUES (?,?)", (channel_id, user_id))
        conn.commit()


def remove_cohost(channel_id: int, user_id: int):
    with _db() as conn:
        conn.execute("DELETE FROM tempvc_cohosts WHERE channel_id=? AND user_id=?", (channel_id, user_id))
        conn.commit()


def get_cohosts(channel_id: int) -> list[int]:
    with _db() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM tempvc_cohosts WHERE channel_id=?", (channel_id,)).fetchall()]


def is_cohost(channel_id: int, user_id: int) -> bool:
    with _db() as conn:
        row = conn.execute("SELECT user_id FROM tempvc_cohosts WHERE channel_id=? AND user_id=?", (channel_id, user_id)).fetchone()
        return row is not None


def is_owner_or_cohost(channel_id: int, user_id: int) -> bool:
    owner = get_owner(channel_id)
    if owner and owner == user_id:
        return True
    return is_cohost(channel_id, user_id)


# ─── Modals ───────────────────────────────────────────────────────────────────

class RenameModal(discord.ui.Modal, title="✏️  Rename Your Channel"):
    new_name = discord.ui.TextInput(
        label="New Channel Name",
        placeholder="e.g.  GKR Gaming Den  /  Study Room",
        max_length=100,
        required=True,
    )

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.vc.edit(name=self.new_name.value)
            await interaction.response.send_message(
                f"✏️  Channel renamed to **{self.new_name.value}**.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌  Failed to rename: {e}", ephemeral=True)


class LimitModal(discord.ui.Modal, title="👥  Set User Limit"):
    new_limit = discord.ui.TextInput(
        label="User Limit (0 = unlimited, max 99)",
        placeholder="Enter a number from 0 to 99",
        max_length=2,
        required=True,
    )

    def __init__(self, vc: discord.VoiceChannel):
        super().__init__()
        self.vc = vc

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.new_limit.value)
            if not (0 <= limit <= 99):
                raise ValueError
            await self.vc.edit(user_limit=limit)
            limit_str = f"**{limit}**" if limit > 0 else "**Unlimited**"
            await interaction.response.send_message(f"👥  User limit set to {limit_str}.", ephemeral=True)
        except (ValueError, TypeError):
            await interaction.response.send_message("❌  Enter a valid number between **0** and **99**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌  Failed: {e}", ephemeral=True)


# ─── Selection Views ──────────────────────────────────────────────────────────

class MemberSelect(discord.ui.Select):
    def __init__(self, vc: discord.VoiceChannel, action: str, exclude_self_id: int):
        self.vc = vc
        self.action = action
        options = [
            discord.SelectOption(
                label=m.display_name[:100],
                value=str(m.id),
                description=f"@{m.name}"[:100],
            )
            for m in vc.members
            if m.id != exclude_self_id and not m.bot
        ]
        if not options:
            options = [discord.SelectOption(label="No members available", value="none", description="—")]
        super().__init__(placeholder=f"Choose a member to {action}...", options=options[:25], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌  No members available.", ephemeral=True)
            return
        member_id = int(self.values[0])
        member = self.vc.guild.get_member(member_id)
        if not member:
            await interaction.response.send_message("❌  Member not found.", ephemeral=True)
            return

        if self.action == "kick":
            if member.voice and member.voice.channel == self.vc:
                await member.move_to(None)
                await interaction.response.send_message(f"🦵  **{member.display_name}** was removed from the channel.", ephemeral=True)
            else:
                await interaction.response.send_message("❌  That member is no longer in the channel.", ephemeral=True)

        elif self.action == "ban":
            ban_user(self.vc.id, member_id)
            await self.vc.set_permissions(member, connect=False, view_channel=False)
            if member.voice and member.voice.channel == self.vc:
                await member.move_to(None)
            await interaction.response.send_message(f"🚫  **{member.display_name}** has been **banned** from this channel.", ephemeral=True)

        elif self.action == "trust":
            trust_user(self.vc.id, member_id)
            await self.vc.set_permissions(member, connect=True, view_channel=True)
            await interaction.response.send_message(f"✅  **{member.display_name}** is now **trusted** — they can join even when locked.", ephemeral=True)

        elif self.action == "untrust":
            untrust_user(self.vc.id, member_id)
            await self.vc.set_permissions(member, overwrite=None)
            await interaction.response.send_message(f"🚷  **{member.display_name}** is no longer trusted.", ephemeral=True)

        elif self.action == "cohost":
            add_cohost(self.vc.id, member_id)
            await self.vc.set_permissions(member, connect=True, view_channel=True, manage_channels=True, move_members=True)
            await interaction.response.send_message(f"⭐  **{member.display_name}** has been granted **Co-Host Power**! They can now manage this voice channel.", ephemeral=True)

        elif self.action == "uncohost":
            remove_cohost(self.vc.id, member_id)
            await self.vc.set_permissions(member, manage_channels=False, move_members=False)
            await interaction.response.send_message(f"🔻  **{member.display_name}**'s **Co-Host Power** was removed.", ephemeral=True)

        elif self.action == "transfer":
            set_owner(self.vc.id, member_id)
            await self.vc.set_permissions(interaction.user, manage_channels=False, move_members=False)
            await self.vc.set_permissions(member, connect=True, manage_channels=True, move_members=True)
            try:
                await self.vc.edit(name=f"🎮  {member.display_name}'s Channel")
            except Exception:
                pass
            await interaction.response.send_message(f"🔁  Ownership transferred to **{member.display_name}**!", ephemeral=True)


class MemberSelectView(discord.ui.View):
    def __init__(self, vc: discord.VoiceChannel, action: str, exclude_self_id: int):
        super().__init__(timeout=30)
        self.add_item(MemberSelect(vc, action, exclude_self_id))


class AnyMemberSelect(discord.ui.Select):
    """Used for unban — shows members from the ban list."""
    def __init__(self, vc: discord.VoiceChannel, guild: discord.Guild, banned_ids: list[int]):
        self.vc = vc
        self.guild = guild
        options = []
        for uid in banned_ids[:25]:
            m = guild.get_member(uid)
            label = m.display_name[:100] if m else f"User {uid}"
            options.append(discord.SelectOption(label=label, value=str(uid), description=f"ID: {uid}"))
        if not options:
            options = [discord.SelectOption(label="No banned members", value="none")]
        super().__init__(placeholder="Choose a member to unban...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("❌  No banned members.", ephemeral=True)
            return
        uid = int(self.values[0])
        unban_user(self.vc.id, uid)
        m = self.guild.get_member(uid)
        if m:
            await self.vc.set_permissions(m, overwrite=None)
        name = m.display_name if m else f"User {uid}"
        await interaction.response.send_message(f"✅  **{name}** has been **unbanned** from this channel.", ephemeral=True)


class AnyMemberSelectView(discord.ui.View):
    def __init__(self, vc, guild, banned_ids):
        super().__init__(timeout=30)
        self.add_item(AnyMemberSelect(vc, guild, banned_ids))


class RegionSelect(discord.ui.Select):
    def __init__(self, vc: discord.VoiceChannel):
        self.vc = vc
        options = [discord.SelectOption(label=label, value=str(rtc) if rtc else "auto") for label, rtc in REGIONS]
        super().__init__(placeholder="🌐  Choose a voice region...", options=options[:25], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        region = None if self.values[0] == "auto" else self.values[0]
        try:
            await self.vc.edit(rtc_region=region)
            label = next((lbl for lbl, rtc in REGIONS if (str(rtc) if rtc else "auto") == self.values[0]), self.values[0])
            await interaction.response.send_message(f"🌐  Region changed to **{label}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌  Failed to change region: {e}", ephemeral=True)


class RegionSelectView(discord.ui.View):
    def __init__(self, vc):
        super().__init__(timeout=30)
        self.add_item(RegionSelect(vc))


# ─── Control Panel ────────────────────────────────────────────────────────────

PANEL_DESCRIPTION = (
    "**Your voice channel control center.**\n"
    "Manage privacy, members, and settings below.\n"
    "━━━━━━━━━━━━━━━━━━━━━━━"
)


class TempVCControlPanel(discord.ui.View):
    """Persistent 19-button control panel for Temp VC owners and co-hosts."""

    def __init__(self):
        super().__init__(timeout=None)

    # ── core helpers ──────────────────────────────────────────────────────────

    async def _get_vc(self, interaction: discord.Interaction):
        channel = interaction.channel
        if isinstance(channel, discord.VoiceChannel):
            vc = channel
        else:
            if not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.response.send_message("❌  You must be inside the voice channel to use its controls.", ephemeral=True)
                return None, None
            vc = interaction.user.voice.channel
        owner_id = get_owner(vc.id)
        if not owner_id:
            await interaction.response.send_message("❌  This is not a managed temporary voice channel.", ephemeral=True)
            return None, None
        return vc, owner_id

    async def _check_owner(self, interaction: discord.Interaction, allow_cohost: bool = True) -> bool:
        vc, owner_id = await self._get_vc(interaction)
        if not vc:
            return False
        if allow_cohost and is_owner_or_cohost(vc.id, interaction.user.id):
            return True
        if interaction.user.id != owner_id:
            msg = (
                "❌  Only the **channel owner** can do that."
                if not allow_cohost
                else "❌  Only the **channel owner** or an authorized **Co-Host** can do that.\n> Use **👑 Claim** if the owner has left."
            )
            await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True

    # ══════════════════════════════════════════════════════════════════════════
    # ROW 0 — Name · Limit · Lock · Unlock · Hide
    # ══════════════════════════════════════════════════════════════════════════

    @discord.ui.button(label="NAME", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="tempvc:rename", row=0)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        await interaction.response.send_modal(RenameModal(vc))

    @discord.ui.button(label="LIMIT", emoji="👥", style=discord.ButtonStyle.secondary, custom_id="tempvc:limit", row=0)
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        await interaction.response.send_modal(LimitModal(vc))

    @discord.ui.button(label="LOCK", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="tempvc:lock", row=0)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        await vc.set_permissions(everyone, connect=False)
        await interaction.response.send_message("🔒  Channel **locked** — no new members can join.", ephemeral=True)

    @discord.ui.button(label="UNLOCK", emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="tempvc:unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        await vc.set_permissions(everyone, connect=True)
        await interaction.response.send_message("🔓  Channel **unlocked** — open to everyone.", ephemeral=True)

    @discord.ui.button(label="HIDE", emoji="🙈", style=discord.ButtonStyle.secondary, custom_id="tempvc:hide", row=0)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        await vc.set_permissions(everyone, view_channel=False)
        await interaction.response.send_message("🙈  Channel **hidden** from the channel list.", ephemeral=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ROW 1 — Unhide · Waiting · Chat · Trust · Untrust
    # ══════════════════════════════════════════════════════════════════════════

    @discord.ui.button(label="UNHIDE", emoji="👁️", style=discord.ButtonStyle.secondary, custom_id="tempvc:unhide", row=1)
    async def unhide(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        await vc.set_permissions(everyone, view_channel=True)
        await interaction.response.send_message("👁️  Channel is **visible** again.", ephemeral=True)

    @discord.ui.button(label="WAITING", emoji="⏳", style=discord.ButtonStyle.secondary, custom_id="tempvc:waiting", row=1)
    async def waiting(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        overwrite = vc.overwrites_for(everyone)
        currently_speak = overwrite.speak
        if currently_speak is False:
            await vc.set_permissions(everyone, speak=None)
            await interaction.response.send_message("🔊  **Waiting room disabled** — all members can speak.", ephemeral=True)
        else:
            await vc.set_permissions(everyone, speak=False)
            await interaction.response.send_message("⏳  **Waiting room enabled** — new members will be muted until you unmute them.", ephemeral=True)

    @discord.ui.button(label="CHAT", emoji="💬", style=discord.ButtonStyle.secondary, custom_id="tempvc:chat", row=1)
    async def chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        overwrite = vc.overwrites_for(everyone)
        currently_send = overwrite.send_messages
        if currently_send is False:
            await vc.set_permissions(everyone, send_messages=None)
            await interaction.response.send_message("💬  **Text chat enabled** — members can now type.", ephemeral=True)
        else:
            await vc.set_permissions(everyone, send_messages=False)
            await interaction.response.send_message("🔕  **Text chat disabled** — only the owner can post.", ephemeral=True)

    @discord.ui.button(label="TRUST", emoji="✅", style=discord.ButtonStyle.secondary, custom_id="tempvc:trust", row=1)
    async def trust(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        options = [
            discord.SelectOption(label=m.display_name[:100], value=str(m.id), description=f"@{m.name}"[:100])
            for m in interaction.guild.members
            if not m.bot and m.id != interaction.user.id
        ]
        if not options:
            return await interaction.response.send_message("❌  No members found to trust.", ephemeral=True)
        await interaction.response.send_message(
            "Select a member to **trust** (they can join even when locked):",
            view=MemberSelectView(vc, "trust", interaction.user.id),
            ephemeral=True,
        )

    @discord.ui.button(label="UNTRUST", emoji="🚷", style=discord.ButtonStyle.secondary, custom_id="tempvc:untrust", row=1)
    async def untrust(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        trusted = get_trusted(vc.id)
        if not trusted:
            return await interaction.response.send_message("❌  No trusted members to remove.", ephemeral=True)
        await interaction.response.send_message(
            "Select a member to **remove trust** from:",
            view=MemberSelectView(vc, "untrust", interaction.user.id),
            ephemeral=True,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # ROW 2 — Invite · Kick · Region · Ban · Unban
    # ══════════════════════════════════════════════════════════════════════════

    @discord.ui.button(label="INVITE", emoji="🔗", style=discord.ButtonStyle.secondary, custom_id="tempvc:invite", row=2)
    async def invite(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        try:
            invite = await vc.create_invite(max_age=3600, max_uses=10, reason="TempVC: owner-requested invite")
            await interaction.response.send_message(
                f"🔗  **Invite link created!**\n{invite.url}\n> *Expires in 1 hour · Max 10 uses*",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌  Failed to create invite: {e}", ephemeral=True)

    @discord.ui.button(label="KICK", emoji="🦵", style=discord.ButtonStyle.danger, custom_id="tempvc:kick", row=2)
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        members_in = [m for m in vc.members if m.id != interaction.user.id and not m.bot]
        if not members_in:
            return await interaction.response.send_message("❌  No members to kick.", ephemeral=True)
        await interaction.response.send_message(
            "Select a member to **remove** from the channel:",
            view=MemberSelectView(vc, "kick", interaction.user.id),
            ephemeral=True,
        )

    @discord.ui.button(label="REGION", emoji="🌐", style=discord.ButtonStyle.secondary, custom_id="tempvc:region", row=2)
    async def region(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        await interaction.response.send_message(
            "🌐  Select a **voice region** for your channel:",
            view=RegionSelectView(vc),
            ephemeral=True,
        )

    @discord.ui.button(label="BAN", emoji="🚫", style=discord.ButtonStyle.danger, custom_id="tempvc:ban", row=2)
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        all_options = [
            discord.SelectOption(label=m.display_name[:100], value=str(m.id), description=f"@{m.name}"[:100])
            for m in interaction.guild.members
            if not m.bot and m.id != interaction.user.id and m.id not in get_banned(vc.id)
        ]
        if not all_options:
            return await interaction.response.send_message("❌  No members available to ban.", ephemeral=True)
        view = discord.ui.View(timeout=30)
        select = discord.ui.Select(placeholder="Choose a member to ban...", options=all_options[:25])
        async def ban_cb(i2: discord.Interaction):
            uid = int(select.values[0])
            m2 = interaction.guild.get_member(uid)
            if m2:
                ban_user(vc.id, uid)
                await vc.set_permissions(m2, connect=False, view_channel=False)
                if m2.voice and m2.voice.channel == vc:
                    await m2.move_to(None)
                await i2.response.send_message(f"🚫  **{m2.display_name}** has been **banned** from this channel.", ephemeral=True)
            else:
                await i2.response.send_message("❌  Member not found.", ephemeral=True)
        select.callback = ban_cb
        view.add_item(select)
        await interaction.response.send_message("Select a member to **ban** from this channel:", view=view, ephemeral=True)

    @discord.ui.button(label="UNBAN", emoji="💚", style=discord.ButtonStyle.success, custom_id="tempvc:unban", row=2)
    async def unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=True): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        banned = get_banned(vc.id)
        if not banned:
            return await interaction.response.send_message("❌  No banned members in this channel.", ephemeral=True)
        await interaction.response.send_message(
            "Select a member to **unban**:",
            view=AnyMemberSelectView(vc, interaction.guild, banned),
            ephemeral=True,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # ROW 3 — Claim · Transfer · Co-Host · Delete
    # ══════════════════════════════════════════════════════════════════════════

    @discord.ui.button(label="CLAIM", emoji="👑", style=discord.ButtonStyle.primary, custom_id="tempvc:claim", row=3)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self._get_vc(interaction)
        if not vc: return
        if interaction.user.id == owner_id:
            return await interaction.response.send_message("👑  You **already own** this channel.", ephemeral=True)
        owner_in_vc = any(m.id == owner_id for m in vc.members)
        if owner_in_vc:
            return await interaction.response.send_message(
                "❌  The current owner is still in the channel.\n> You can only claim after they leave.",
                ephemeral=True,
            )
        set_owner(vc.id, interaction.user.id)
        await vc.set_permissions(interaction.user, connect=True, manage_channels=True, move_members=True)
        try:
            await vc.edit(name=f"🎮  {interaction.user.display_name}'s Channel")
        except Exception:
            pass
        await interaction.response.send_message(
            f"👑  **{interaction.user.display_name}** is now the channel owner!", ephemeral=False
        )

    @discord.ui.button(label="TRANSFER", emoji="🔁", style=discord.ButtonStyle.primary, custom_id="tempvc:transfer", row=3)
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=False): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        members_in = [m for m in vc.members if m.id != interaction.user.id and not m.bot]
        if not members_in:
            return await interaction.response.send_message("❌  No other members in the channel to transfer to.", ephemeral=True)
        await interaction.response.send_message(
            "Select a member to **transfer ownership** to:",
            view=MemberSelectView(vc, "transfer", interaction.user.id),
            ephemeral=True,
        )

    @discord.ui.button(label="CO-HOST", emoji="⭐", style=discord.ButtonStyle.primary, custom_id="tempvc:cohost", row=3)
    async def cohost_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=False): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        members_in = [m for m in vc.members if m.id != interaction.user.id and not m.bot]
        current_cohosts = get_cohosts(vc.id)

        view = discord.ui.View(timeout=45)
        add_options = [
            discord.SelectOption(label=f"⭐ Grant: {m.display_name}"[:100], value=f"add_{m.id}", description=f"Give control panel powers to @{m.name}"[:100])
            for m in members_in if m.id not in current_cohosts
        ]
        remove_options = [
            discord.SelectOption(label=f"🔻 Revoke: {interaction.guild.get_member(uid).display_name if interaction.guild.get_member(uid) else f'User {uid}'}"[:100], value=f"rem_{uid}", description="Remove Co-Host powers")
            for uid in current_cohosts
        ]
        all_options = add_options + remove_options
        if not all_options:
            return await interaction.response.send_message("❌  No other members in the channel to grant Co-Host powers to.", ephemeral=True)

        select = discord.ui.Select(placeholder="⭐ Choose a member to grant or revoke Co-Host power...", options=all_options[:25])

        async def cohost_cb(i2: discord.Interaction):
            val = select.values[0]
            if val.startswith("add_"):
                uid = int(val.replace("add_", ""))
                m2 = interaction.guild.get_member(uid)
                if m2:
                    add_cohost(vc.id, uid)
                    await vc.set_permissions(m2, connect=True, view_channel=True, manage_channels=True, move_members=True)
                    await i2.response.send_message(f"⭐  **{m2.display_name}** has been granted **Co-Host Power**! They can now manage this voice channel.", ephemeral=True)
                else:
                    await i2.response.send_message("❌  Member not found.", ephemeral=True)
            elif val.startswith("rem_"):
                uid = int(val.replace("rem_", ""))
                m2 = interaction.guild.get_member(uid)
                remove_cohost(vc.id, uid)
                if m2:
                    await vc.set_permissions(m2, manage_channels=False, move_members=False)
                    name = m2.display_name
                else:
                    name = f"User {uid}"
                await i2.response.send_message(f"🔻  Removed Co-Host power from **{name}**.", ephemeral=True)

        select.callback = cohost_cb
        view.add_item(select)
        await interaction.response.send_message("⭐  **Temp VC Co-Host Power Management**\nSelect a member to grant or revoke channel management powers:", view=view, ephemeral=True)

    @discord.ui.button(label="DELETE", emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="tempvc:delete", row=3)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction, allow_cohost=False): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        remove_temp_channel(vc.id)
        await interaction.response.send_message("🗑️  Channel is being **deleted**...", ephemeral=True)
        try:
            await vc.delete(reason=f"TempVC: owner {interaction.user} manually deleted")
        except Exception as e:
            print(f"[TempVC] Failed to delete VC {vc.id}: {e}")


# ─── Embed Builder ────────────────────────────────────────────────────────────

def _build_panel_embed(member: discord.Member, vc: discord.VoiceChannel) -> discord.Embed:
    cohosts = get_cohosts(vc.id)
    cohost_str = ", ".join(f"<@{uid}>" for uid in cohosts) if cohosts else "*None*"

    embed = discord.Embed(
        title="🎮  Temp VC — Control Panel",
        description=(
            f"**{member.display_name}**, you own this channel.\n"
            "Use the buttons below to manage your voice channel.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 Lock/Unlock   🙈 Hide/Unhide\n"
            "👥 Set Limit      ✏️ Rename\n"
            "✅ Trust/Untrust  🦵 Kick/🚫 Ban\n"
            "🔗 Invite          🌐 Region\n"
            "⭐ Co-Host        👑 Claim/🔁 Transfer\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "*Auto-deleted when everyone leaves.*"
        ),
        color=0x5865F2,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="📡  Channel", value=vc.mention, inline=True)
    embed.add_field(name="👑  Owner", value=member.mention, inline=True)
    embed.add_field(name="⭐  Co-Hosts", value=cohost_str, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"{BOT_NAME} Temp VC  •  Your channel, your rules")
    return embed


# ─── Cog ──────────────────────────────────────────────────────────────────────

class TempVCCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        """On bot start/restart — clean up orphaned temp VC channels in background once ready."""
        asyncio.create_task(self._startup_cleanup_task())

    async def _startup_cleanup_task(self) -> None:
        await self.bot.wait_until_ready()
        await self._cleanup_orphaned_channels()

    async def _cleanup_orphaned_channels(self) -> None:
        """Delete all tracked temp VCs that still exist in Discord after a restart."""
        rows = get_all_temp_channels()
        cleaned = 0
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                remove_temp_channel(row["channel_id"])
                continue
            ch = guild.get_channel(row["channel_id"])
            if ch is None:
                # Channel already deleted — just clean DB
                remove_temp_channel(row["channel_id"])
                cleaned += 1
            else:
                # Channel exists but bot restarted — delete it
                try:
                    await ch.delete(reason="TempVC: cleanup after bot restart")
                except Exception:
                    pass
                remove_temp_channel(row["channel_id"])
                cleaned += 1
        if cleaned:
            print(f"[TempVC] 🧹 Cleaned up {cleaned} orphaned temp VC(s) after restart.")
        else:
            print("[TempVC] ✅ No orphaned temp VCs to clean up.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild

        # ── 1. Member joined a hub channel → create temp VC ──────────────────
        if after.channel and after.channel.id in get_hubs(guild.id):
            hub = after.channel
            category = hub.category
            channel_name = f"🎮  {member.display_name}'s Channel"
            try:
                new_vc = await guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    reason="TempVC: auto-created for member",
                )
                await new_vc.set_permissions(member, connect=True, manage_channels=True, move_members=True, speak=True)
                await member.move_to(new_vc)
                add_temp_channel(new_vc.id, guild.id, member.id)

                embed = _build_panel_embed(member, new_vc)
                view = TempVCControlPanel()
                await new_vc.send(embed=embed, view=view)

            except discord.Forbidden:
                print(f"[TempVC] Missing permissions to create VC in {guild.name}")
            except Exception as e:
                print(f"[TempVC] Error creating VC: {e}")

        # ── 2. Member left a temp VC → auto-delete if empty ──────────────────
        if before.channel:
            row = get_temp_channel(before.channel.id)
            if row:
                vc = before.channel
                human_members = [m for m in vc.members if not m.bot]
                if not human_members:
                    await asyncio.sleep(1.5)
                    vc = guild.get_channel(before.channel.id)
                    if vc and not [m for m in vc.members if not m.bot]:
                        remove_temp_channel(vc.id)
                        try:
                            await vc.delete(reason="TempVC: auto-deleted (empty)")
                        except Exception as e:
                            print(f"[TempVC] Failed to delete VC: {e}")

    # ── Slash Commands ─────────────────────────────────────────────────────────

    tempvc_group = app_commands.Group(name="tempvc", description="🎮  Temporary Voice Channel System")

    @tempvc_group.command(name="setup", description="Set up the Temp VC system in this server")
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = await guild.create_category("🎮  Temp Voice Channels")
        hub = await guild.create_voice_channel("➕  Join to Create", category=category)
        add_hub(guild.id, hub.id, category.id)

        embed = discord.Embed(
            title="✅  Temp VC System Ready!",
            description=(
                f"**Category:** {category.name}\n"
                f"**Hub Channel:** {hub.mention}\n\n"
                "Members just need to **join the hub** and the bot will auto-create a private channel for them!\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "📌  The hub channel never gets deleted — it resets after each use."
            ),
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{BOT_NAME} Temp VC System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tempvc_group.command(name="sethub", description="Mark an existing voice channel as the Temp VC hub")
    @app_commands.describe(channel="The voice channel members should join to create a temp VC")
    @app_commands.default_permissions(administrator=True)
    async def sethub(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        add_hub(interaction.guild.id, channel.id, channel.category_id)
        await interaction.response.send_message(
            f"✅  {channel.mention} is now the **Temp VC hub**. Members who join it will get their own channel.",
            ephemeral=True,
        )

    @tempvc_group.command(name="removehub", description="Remove a voice channel from the Temp VC hub list")
    @app_commands.describe(channel="The hub voice channel to remove")
    @app_commands.default_permissions(administrator=True)
    async def removehub(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        remove_hub(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"✅  {channel.mention} is **no longer** a Temp VC hub.", ephemeral=True
        )

    @tempvc_group.command(name="cleanup", description="Manually delete all orphaned temp VC channels in this server")
    @app_commands.default_permissions(administrator=True)
    async def cleanup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        rows = get_all_temp_channels()
        guild_rows = [r for r in rows if r["guild_id"] == guild.id]
        cleaned = 0
        for row in guild_rows:
            ch = guild.get_channel(row["channel_id"])
            if ch:
                try:
                    await ch.delete(reason=f"TempVC: manual cleanup by {interaction.user}")
                except Exception:
                    pass
            remove_temp_channel(row["channel_id"])
            cleaned += 1
        embed = discord.Embed(
            title="🧹  Temp VC Cleanup Complete",
            description=f"Deleted and removed **{cleaned}** orphaned temp VC channel(s) from this server.",
            color=0x57F287,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{BOT_NAME} Temp VC System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tempvc_group.command(name="list", description="List all active temporary voice channels")
    @app_commands.default_permissions(manage_channels=True)
    async def list_channels(self, interaction: discord.Interaction):
        with _db() as conn:
            rows = conn.execute(
                "SELECT channel_id, owner_id FROM tempvc_channels WHERE guild_id=?",
                (interaction.guild.id,),
            ).fetchall()
        if not rows:
            return await interaction.response.send_message("No active temp VCs right now.", ephemeral=True)
        lines = []
        for r in rows:
            ch = interaction.guild.get_channel(r["channel_id"])
            owner = interaction.guild.get_member(r["owner_id"])
            ch_name = ch.name if ch else f"*(deleted)* `{r['channel_id']}`"
            owner_name = owner.mention if owner else f"*Unknown*"
            members = len(ch.members) if ch else 0
            lines.append(f"🎮  **{ch_name}** — {owner_name}  ·  `{members}` members")
        embed = discord.Embed(
            title="🎮  Active Temp VCs",
            description="\n".join(lines),
            color=0x5865F2,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{BOT_NAME} Temp VC System  •  {len(rows)} active channel(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tempvc_group.command(name="panel", description="Get the control panel for your current temporary voice channel")
    async def panel(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌  You must be in a voice channel to use this.", ephemeral=True)
        vc = interaction.user.voice.channel
        if not get_owner(vc.id):
            return await interaction.response.send_message("❌  You are not in a temporary voice channel.", ephemeral=True)
        embed = _build_panel_embed(interaction.user, vc)
        await interaction.response.send_message(embed=embed, view=TempVCControlPanel(), ephemeral=True)

    @tempvc_group.command(name="sendpanel", description="Drop the master control panel into the current text channel")
    @app_commands.default_permissions(administrator=True)
    async def sendpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮  Temp VC — Control Panel",
            description=(
                "**Manage your temporary voice channel below!**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Join the hub channel to create your own temp VC, then use the buttons to:\n\n"
                "🔒 **Lock / Unlock** your channel\n"
                "🙈 **Hide / Unhide** from the list\n"
                "👥 **Set a user limit**\n"
                "✅ **Trust / Untrust** members\n"
                "🦵 **Kick** someone out\n"
                "🚫 **Ban / Unban** members\n"
                "🌐 **Change voice region**\n"
                "🔗 **Create an invite**\n"
                "🔁 **Transfer** channel ownership\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "*You must be connected to your voice channel for buttons to work.*"
            ),
            color=0x5865F2,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{BOT_NAME} Temp VC System  •  Your channel, your rules")
        await interaction.channel.send(embed=embed, view=TempVCControlPanel())
        await interaction.response.send_message("✅  Master control panel deployed.", ephemeral=True)

    @tempvc_group.command(name="cohost", description="Grant, revoke, or list Co-Host managers for your Temp VC")
    @app_commands.describe(
        action="Choose whether to grant (add), revoke (remove), or list co-hosts",
        member="The member to grant or revoke Co-Host powers"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Grant (Add)", value="add"),
        app_commands.Choice(name="Revoke (Remove)", value="remove"),
        app_commands.Choice(name="List Co-Hosts", value="list"),
    ])
    async def cohost_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        member: Optional[discord.Member] = None
    ) -> None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌  You must be in a voice channel to use this.", ephemeral=True)
        vc = interaction.user.voice.channel
        owner_id = get_owner(vc.id)
        if not owner_id:
            return await interaction.response.send_message("❌  You are not in a temporary voice channel.", ephemeral=True)
        if interaction.user.id != owner_id:
            return await interaction.response.send_message("❌  Only the **channel owner** can assign or remove Co-Hosts.", ephemeral=True)

        if action == "list":
            cohosts = get_cohosts(vc.id)
            if not cohosts:
                return await interaction.response.send_message("ℹ️  This channel does not have any Co-Hosts assigned.", ephemeral=True)
            cohost_list = "\n".join(f"• <@{uid}>" for uid in cohosts)
            embed = discord.Embed(
                title="⭐  Active Co-Hosts",
                description=f"The following members have full control powers for {vc.mention}:\n\n{cohost_list}",
                color=0x5865F2,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if not member:
            return await interaction.response.send_message("❌  Please specify a member to grant or revoke powers.", ephemeral=True)
        if member.id == interaction.user.id:
            return await interaction.response.send_message("👑  You are already the channel owner.", ephemeral=True)
        if member.bot:
            return await interaction.response.send_message("❌  Cannot assign Co-Host to a bot.", ephemeral=True)

        if action == "add":
            add_cohost(vc.id, member.id)
            await vc.set_permissions(member, connect=True, view_channel=True, manage_channels=True, move_members=True)
            await interaction.response.send_message(
                f"⭐  **{member.mention}** has been granted **Co-Host Power**! They can now operate all control panel buttons.",
                ephemeral=True
            )
        elif action == "remove":
            remove_cohost(vc.id, member.id)
            await vc.set_permissions(member, manage_channels=False, move_members=False)
            await interaction.response.send_message(
                f"🔻  Removed Co-Host power from **{member.mention}**.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    _init_db()
    await bot.add_cog(TempVCCog(bot))
    bot.add_view(TempVCControlPanel())
    print("🎮 Temp VC System Loaded")

