"""
temp_vc.py – Temporary Voice Channel (Auto-VC) system for GKR Bot.

How it works:
  1. An admin runs /tempvc setup → the bot creates a Category and a "➕ Join to Create" channel.
  2. When any member joins that hub channel, the bot instantly creates a new VC
     named after them, moves them in, and sends a control panel to the channel's text chat.
  3. When the last person leaves a temp VC the bot auto-deletes it.
  4. The VC owner uses the control panel (buttons) to lock/unlock, hide/unhide,
     set a user limit, rename, or claim ownership.
"""

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "gkr_bot.db")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

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
                owner_id    INTEGER NOT NULL
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
        conn.execute(
            "DELETE FROM tempvc_hubs WHERE guild_id=? AND channel_id=?",
            (guild_id, channel_id),
        )
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
        conn.execute(
            "DELETE FROM tempvc_channels WHERE channel_id=?", (channel_id,)
        )
        conn.commit()


def get_temp_channel(channel_id: int):
    with _db() as conn:
        return conn.execute(
            "SELECT * FROM tempvc_channels WHERE channel_id=?", (channel_id,)
        ).fetchone()


def get_owner(channel_id: int) -> int | None:
    row = get_temp_channel(channel_id)
    return row["owner_id"] if row else None


def set_owner(channel_id: int, owner_id: int):
    with _db() as conn:
        conn.execute(
            "UPDATE tempvc_channels SET owner_id=? WHERE channel_id=?",
            (owner_id, channel_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Control panel view
# ---------------------------------------------------------------------------

class TempVCControlPanel(discord.ui.View):
    """Persistent button panel DM'd to the Temp VC text chat."""

    def __init__(self):
        super().__init__(timeout=None)

    # ---- helpers ----

    async def _get_vc(self, interaction: discord.Interaction):
        """Returns (voice_channel, owner_id) or None if the panel is stale."""
        channel = interaction.channel
        
        # If the panel was sent to the VC text chat, interaction.channel is the VC.
        if isinstance(channel, discord.VoiceChannel):
            vc = channel
        else:
            # If the panel was spawned via /tempvc panel in a normal text channel,
            # we need to look at the user's current voice state.
            if not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.response.send_message(
                    "❌ You must be inside the voice channel to use its controls.", ephemeral=True
                )
                return None, None
            vc = interaction.user.voice.channel
            
        owner_id = get_owner(vc.id)
        if not owner_id:
            await interaction.response.send_message(
                "❌ This is not a managed temporary voice channel.", ephemeral=True
            )
            return None, None
            
        return vc, owner_id

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        vc, owner_id = await self._get_vc(interaction)
        if not vc:
            return False
        if interaction.user.id != owner_id:
            await interaction.response.send_message(
                "❌ Only the channel owner can do that.\n"
                "Use **Claim** if the owner has left.", ephemeral=True
            )
            return False
        return True

    # ---- buttons ----

    @discord.ui.button(label="🔒 Lock", style=discord.ButtonStyle.danger, custom_id="tempvc:lock", row=0)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        await vc.set_permissions(everyone, connect=False)
        await interaction.response.send_message("🔒 Channel **locked**. Nobody new can join.", ephemeral=True)

    @discord.ui.button(label="🔓 Unlock", style=discord.ButtonStyle.success, custom_id="tempvc:unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        await vc.set_permissions(everyone, connect=True)
        await interaction.response.send_message("🔓 Channel **unlocked**. Anyone can join.", ephemeral=True)

    @discord.ui.button(label="👁️ Hide", style=discord.ButtonStyle.secondary, custom_id="tempvc:hide", row=0)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        await vc.set_permissions(everyone, view_channel=False)
        await interaction.response.send_message("👁️ Channel **hidden** from the channel list.", ephemeral=True)

    @discord.ui.button(label="👀 Unhide", style=discord.ButtonStyle.secondary, custom_id="tempvc:unhide", row=0)
    async def unhide(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc, _ = await self._get_vc(interaction)
        everyone = interaction.guild.default_role
        await vc.set_permissions(everyone, view_channel=True)
        await interaction.response.send_message("👀 Channel **visible** again.", ephemeral=True)

    @discord.ui.button(label="👑 Claim", style=discord.ButtonStyle.primary, custom_id="tempvc:claim", row=0)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, owner_id = await self._get_vc(interaction)
        if not vc: return
        # Allow claim only if the owner is no longer in the channel
        owner_in_vc = any(m.id == owner_id for m in vc.members)
        if owner_in_vc:
            await interaction.response.send_message(
                "❌ The owner is still in the channel. You can only claim when they have left.", ephemeral=True
            )
            return
        set_owner(vc.id, interaction.user.id)
        await vc.edit(name=f"🎮 {interaction.user.display_name}'s Channel")
        await interaction.response.send_message(f"👑 **{interaction.user.display_name}** is now the channel owner!", ephemeral=False)

    @discord.ui.button(label="➕ Limit +1", style=discord.ButtonStyle.secondary, custom_id="tempvc:limit_up", row=1)
    async def limit_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc, _ = await self._get_vc(interaction)
        new_limit = min(99, (vc.user_limit or 0) + 1)
        await vc.edit(user_limit=new_limit)
        limit_str = f"{new_limit}" if new_limit > 0 else "unlimited"
        await interaction.response.send_message(f"➕ User limit set to **{limit_str}**.", ephemeral=True)

    @discord.ui.button(label="➖ Limit -1", style=discord.ButtonStyle.secondary, custom_id="tempvc:limit_down", row=1)
    async def limit_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc, _ = await self._get_vc(interaction)
        new_limit = max(0, (vc.user_limit or 0) - 1)
        await vc.edit(user_limit=new_limit)
        limit_str = f"{new_limit}" if new_limit > 0 else "unlimited"
        await interaction.response.send_message(f"➖ User limit set to **{limit_str}**.", ephemeral=True)

    @discord.ui.button(label="✏️ Rename", style=discord.ButtonStyle.secondary, custom_id="tempvc:rename", row=1)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc, _ = await self._get_vc(interaction)
        if not vc: return
        await interaction.response.send_modal(RenameModal(vc))

    @discord.ui.button(label="🚫 Kick Member", style=discord.ButtonStyle.danger, custom_id="tempvc:kick", row=1)
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction): return
        vc, _ = await self._get_vc(interaction)
        # Build select menu of current members (excluding the owner)
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in vc.members
            if m.id != interaction.user.id and not m.bot
        ]
        if not options:
            return await interaction.response.send_message("❌ No members to kick.", ephemeral=True)
        await interaction.response.send_message(
            "Select a member to remove from the channel:",
            view=KickSelectView(vc, options), ephemeral=True
        )


class RenameModal(discord.ui.Modal, title="Rename Your Channel"):
    new_name = discord.ui.TextInput(
        label="New Channel Name",
        placeholder="e.g. GKR Gaming Zone",
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
                f"✏️ Channel renamed to **{self.new_name.value}**.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to rename that channel.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to rename: {e}", ephemeral=True
            )


class KickSelectView(discord.ui.View):
    def __init__(self, vc: discord.VoiceChannel, options):
        super().__init__(timeout=30)
        self.add_item(KickSelect(vc, options))


class KickSelect(discord.ui.Select):
    def __init__(self, vc, options):
        super().__init__(placeholder="Choose a member to kick...", options=options)
        self.vc = vc

    async def callback(self, interaction: discord.Interaction):
        member_id = int(self.values[0])
        member = self.vc.guild.get_member(member_id)
        if member and member.voice and member.voice.channel == self.vc:
            await member.move_to(None)
            await interaction.response.send_message(f"🚫 **{member.display_name}** was removed.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ That member is no longer in the channel.", ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class TempVCCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild

        # ── 1. Member joined a hub channel → create temp VC ──
        if after.channel and after.channel.id in get_hubs(guild.id):
            hub = after.channel
            category = hub.category

            channel_name = f"🎮 {member.display_name}'s Channel"
            try:
                new_vc = await guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    reason="TempVC: auto-created for member",
                )
                # Give owner full control
                await new_vc.set_permissions(member, connect=True, manage_channels=True, move_members=True)
                # Move the member into their new channel
                await member.move_to(new_vc)
                # Track it
                add_temp_channel(new_vc.id, guild.id, member.id)

                # Send control panel into the VC's own text section
                embed = discord.Embed(
                    title="🎮 Temp VC Control Panel",
                    description=(
                        f"Welcome **{member.display_name}**! You own this channel.\n\n"
                        "Use the buttons below to manage your channel.\n"
                        "It will be **auto-deleted** when everyone leaves."
                    ),
                    color=0x8A2BE2,
                )
                embed.set_footer(text="GKR Temp VC System")
                view = TempVCControlPanel()
                await new_vc.send(embed=embed, view=view)

            except discord.Forbidden:
                print(f"[TempVC] Missing permissions to create VC in {guild.name}")
            except Exception as e:
                print(f"[TempVC] Error creating VC: {e}")

        # ── 2. Member left a temp VC → check if empty and delete ──
        if before.channel:
            row = get_temp_channel(before.channel.id)
            if row:
                vc = before.channel
                if len([m for m in vc.members if not m.bot]) == 0:
                    await asyncio.sleep(1)  # small grace period
                    # Re-fetch to be sure
                    vc = guild.get_channel(before.channel.id)
                    if vc and len([m for m in vc.members if not m.bot]) == 0:
                        remove_temp_channel(vc.id)
                        try:
                            await vc.delete(reason="TempVC: auto-deleted (empty)")
                        except Exception as e:
                            print(f"[TempVC] Failed to delete VC: {e}")

    # ── Slash Commands ──

    tempvc_group = app_commands.Group(name="tempvc", description="Temporary Voice Channel System")

    @tempvc_group.command(name="setup", description="Set up the Temp VC system in this server")
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # Create the category
        category = await guild.create_category("🎮 Temp Voice Channels")
        # Create the hub channel inside it
        hub = await guild.create_voice_channel("➕ Join to Create", category=category)

        add_hub(guild.id, hub.id, category.id)

        embed = discord.Embed(
            title="✅ Temp VC System Ready!",
            description=(
                f"Category **{category.name}** and hub channel {hub.mention} have been created.\n\n"
                "Members just need to **join the hub** and the bot will auto-create a private channel for them!"
            ),
            color=0x00FF88,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tempvc_group.command(name="sethub", description="Mark an existing voice channel as the Temp VC hub")
    @app_commands.describe(channel="The voice channel members should join to create a temp VC")
    @app_commands.default_permissions(administrator=True)
    async def sethub(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        add_hub(interaction.guild.id, channel.id, channel.category_id)
        await interaction.response.send_message(
            f"✅ {channel.mention} is now the **Temp VC hub**. When members join it, a channel will be created for them.",
            ephemeral=True,
        )

    @tempvc_group.command(name="removehub", description="Remove a voice channel from the Temp VC hub list")
    @app_commands.describe(channel="The hub voice channel to remove")
    @app_commands.default_permissions(administrator=True)
    async def removehub(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        remove_hub(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"✅ {channel.mention} is no longer a Temp VC hub.", ephemeral=True
        )

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
            ch_name = ch.name if ch else f"(deleted) {r['channel_id']}"
            owner_name = owner.display_name if owner else f"Unknown ({r['owner_id']})"
            lines.append(f"• **{ch_name}** — Owner: {owner_name}")

        embed = discord.Embed(
            title="🎮 Active Temp VCs",
            description="\n".join(lines),
            color=0x8A2BE2,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tempvc_group.command(name="panel", description="Get the control panel for your current temporary voice channel")
    async def panel(self, interaction: discord.Interaction):
        # User must be in a voice channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌ You must be in a voice channel to use this.", ephemeral=True)
            
        vc = interaction.user.voice.channel
        owner_id = get_owner(vc.id)
        
        if not owner_id:
            return await interaction.response.send_message("❌ You are not in a temporary voice channel.", ephemeral=True)
            
        embed = discord.Embed(
            title="🎮 Temp VC Control Panel",
            description=(
                f"**Channel:** {vc.mention}\n\n"
                "Use the buttons below to manage your channel.\n"
                "It will be **auto-deleted** when everyone leaves."
            ),
            color=0x8A2BE2,
        )
        embed.set_footer(text="GKR Temp VC System")
        await interaction.response.send_message(embed=embed, view=TempVCControlPanel(), ephemeral=True)

    @tempvc_group.command(name="sendpanel", description="Drop the master control panel into the current text channel")
    @app_commands.default_permissions(administrator=True)
    async def sendpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮 Temp VC Control Panel",
            description=(
                "**Manage your temporary voice channel here!**\n\n"
                "If you are the owner of a Temp VC, click the buttons below to lock, unlock, "
                "change limits, or hide your channel.\n\n"
                "*(You must be connected to your voice channel for the buttons to work)*"
            ),
            color=0x8A2BE2,
        )
        embed.set_footer(text="GKR Temp VC System")
        await interaction.channel.send(embed=embed, view=TempVCControlPanel())
        await interaction.response.send_message("✅ Master control panel deployed.", ephemeral=True)


async def setup(bot: commands.Bot):
    _init_db()
    await bot.add_cog(TempVCCog(bot))
    bot.add_view(TempVCControlPanel())
    print("🎮 Temp VC System Loaded")
