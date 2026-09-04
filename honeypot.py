"""
honeypot.py – Spam Trap Channel System
Creates a honeypot channel where any user who sends a message gets escalating punishments:
1st Offense: 10 minute timeout
2nd Offense: 1 day timeout
3rd+ Offense: Kick from server
"""

import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
import datetime

from gkr_ui import C

DB_PATH = os.path.join(os.path.dirname(__file__), "honeypot.sqlite3")


class HoneypotDB:
    def __init__(self):
        self._init()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    message_id TEXT,
                    log_channel_id TEXT
                )
            """)
            # Migration logic
            cursor = conn.execute("PRAGMA table_info(channels)")
            columns = [info["name"] for info in cursor.fetchall()]
            if "message_id" not in columns:
                conn.execute("ALTER TABLE channels ADD COLUMN message_id TEXT")
            if "log_channel_id" not in columns:
                conn.execute("ALTER TABLE channels ADD COLUMN log_channel_id TEXT")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS offenses (
                    guild_id TEXT,
                    user_id TEXT,
                    count INTEGER DEFAULT 0,
                    PRIMARY KEY(guild_id, user_id)
                )
            """)
            conn.commit()

    def set_channel(self, guild_id: int, channel_id: int, message_id: int = None):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO channels (guild_id, channel_id, message_id) VALUES (?, ?, ?)",
                (str(guild_id), str(channel_id), str(message_id) if message_id else None)
            )
            conn.commit()

    def set_log_channel(self, guild_id: int, log_channel_id: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE channels SET log_channel_id = ? WHERE guild_id = ?",
                (str(log_channel_id), str(guild_id))
            )
            conn.commit()

    def get_trap_info(self, guild_id: int):
        with self._conn() as conn:
            row = conn.execute("SELECT channel_id, message_id, log_channel_id FROM channels WHERE guild_id = ?", (str(guild_id),)).fetchone()
            if row:
                cid = int(row["channel_id"])
                mid = int(row["message_id"]) if row["message_id"] else None
                lid = int(row["log_channel_id"]) if row["log_channel_id"] else None
                return cid, mid, lid
        return None, None, None

    def get_channel(self, guild_id: int) -> int:
        cid, _, _ = self.get_trap_info(guild_id)
        return cid

    def get_total_triggered(self, guild_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as total FROM offenses WHERE guild_id = ?", (str(guild_id),)).fetchone()
            return row["total"] if row else 0

    def get_total_kicked(self, guild_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as total FROM offenses WHERE guild_id = ? AND count >= 3", (str(guild_id),)).fetchone()
            return row["total"] if row else 0

    def add_offense(self, guild_id: int, user_id: int) -> int:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO offenses (guild_id, user_id, count) VALUES (?, ?, 1) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET count = count + 1",
                (str(guild_id), str(user_id))
            )
            row = conn.execute("SELECT count FROM offenses WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id))).fetchone()
            conn.commit()
            return row["count"]

    def clear_offenses(self, guild_id: int, user_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM offenses WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
            conn.commit()

    def get_user_offenses(self, guild_id: int, user_id: int) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT count FROM offenses WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id))).fetchone()
            return row["count"] if row else 0


class HoneypotCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = HoneypotDB()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        trap_channel_id = self.db.get_channel(message.guild.id)
        if not trap_channel_id or message.channel.id != trap_channel_id:
            return



        # Delete the triggering message immediately
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        offense_count = self.db.add_offense(message.guild.id, message.author.id)

        action_taken = ""
        timeout_until = None
        try:
            if offense_count == 1:
                timeout_until = discord.utils.utcnow() + datetime.timedelta(minutes=10)
                await message.author.timeout(datetime.timedelta(minutes=10), reason="Spam Trap: 1st Offense")
                action_taken = "⏳ Timed out for **10 minutes**"
            elif offense_count == 2:
                timeout_until = discord.utils.utcnow() + datetime.timedelta(days=1)
                await message.author.timeout(datetime.timedelta(days=1), reason="Spam Trap: 2nd Offense")
                action_taken = "⏳ Timed out for **1 day (24 hours)**"
            else:
                await message.author.kick(reason=f"Spam Trap: {offense_count} Offenses")
                action_taken = "🔨 **Kicked from the server**"
        except discord.Forbidden:
            action_taken = "❌ Bot lacks permissions (check role hierarchy)"
            print(f"[Honeypot] Missing perms to punish {message.author} for offense #{offense_count}")
        except Exception as e:
            action_taken = f"❌ Error: {e}"
            print(f"[Honeypot] Error punishing {message.author}: {e}")

        # DM the user so they know what happened
        try:
            dm_embed = discord.Embed(
                title="⚠️ You triggered a Spam Trap",
                description=f"You sent a message in a **Spam Trap** channel in **{message.guild.name}**.\n\n"
                            f"**Action Applied:** {action_taken}\n"
                            f"**Your Offense Count:** #{offense_count}\n\n"
                            "Do NOT send messages in that channel.",
                color=0xFF4444
            )
            await message.author.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass  # DMs disabled

        # Build detailed alert embed
        now = discord.utils.utcnow()
        alert_embed = discord.Embed(
            title="🚨 Spam Trap Triggered!",
            color=0xFF0000,
            timestamp=now
        )
        alert_embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        alert_embed.add_field(name="👤 User", value=f"{message.author.mention}\n`{message.author.id}`", inline=True)
        alert_embed.add_field(name="📊 Offense #", value=f"**#{offense_count}**", inline=True)
        alert_embed.add_field(name="⚖️ Action Taken", value=action_taken, inline=False)
        if timeout_until:
            alert_embed.add_field(
                name="⏰ Timeout Expires",
                value=f"{discord.utils.format_dt(timeout_until, 'F')}\n{discord.utils.format_dt(timeout_until, 'R')}",
                inline=False
            )
        msg_content = message.content[:500] if message.content else "*No text content*"
        alert_embed.add_field(name="📨 Message Sent", value=f"||{msg_content}||", inline=False)
        alert_embed.set_footer(text=f"#{message.channel.name} • {message.guild.name}")

        # Send to configured log channel first, or fallback to ServerLogs security channel, then trap channel
        _, _, log_channel_id = self.db.get_trap_info(message.guild.id)
        sent_to_log = False

        if log_channel_id:
            log_ch = message.guild.get_channel(log_channel_id)
            if log_ch:
                try:
                    await log_ch.send(embed=alert_embed)
                    sent_to_log = True
                except (discord.Forbidden, discord.HTTPException):
                    pass

        # Dispatch automatically to server_logs security channel
        try:
            server_logs_cog = self.bot.get_cog("ServerLogsCog")
            if server_logs_cog and hasattr(server_logs_cog, "logger"):
                desc = (
                    f"**User:** {message.author.mention} (`{message.author.id}`)\n"
                    f"**Offense:** #{offense_count}\n"
                    f"**Action:** {action_taken}\n"
                    f"**Message:** ||{msg_content}||\n"
                    f"**Channel:** {message.channel.mention}"
                )
                await server_logs_cog.logger.dispatch_security(
                    message.guild,
                    "security_honeypot",
                    "🚨 Spam Trap / Honeypot Triggered",
                    desc,
                    color=0xFF0000,
                    thumbnail_url=message.author.display_avatar.url
                )
                sent_to_log = True
        except Exception as e:
            print(f"[Honeypot] server_logs dispatch failed: {e}")

        if not sent_to_log:
            try:
                await message.channel.send(embed=alert_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Update trap message counter on every trigger
        await self.update_trap_message(message.guild)

    async def update_trap_message(self, guild: discord.Guild):
        trap_channel_id, trap_msg_id, _ = self.db.get_trap_info(guild.id)
        if not trap_channel_id or not trap_msg_id:
            return

        channel = guild.get_channel(trap_channel_id)
        if not channel:
            return

        try:
            msg = await channel.fetch_message(trap_msg_id)
            total = self.db.get_total_triggered(guild.id)
            kicked = self.db.get_total_kicked(guild.id)

            view = discord.ui.View()
            btn1 = discord.ui.Button(label=f"⚠️ Users Trapped: {total}", style=discord.ButtonStyle.danger, disabled=True)
            btn2 = discord.ui.Button(label=f"🔨 Kicked: {kicked}", style=discord.ButtonStyle.secondary, disabled=True)
            view.add_item(btn1)
            view.add_item(btn2)

            await msg.edit(view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    # ── Slash Commands ────────────────────────────────────────────────────────

    hp_group = app_commands.Group(
        name="honeypot",
        description="Manage the Honeypot (Spam Trap) Channel system"
    )

    @hp_group.command(name="setup", description="Auto-create a Honeypot/Spam Trap channel with the bait message")
    @app_commands.describe(
        name="Name for the honeypot channel (default: 🚨 ꜱᴘᴀᴍ ᴄʜᴇᴄᴋ)",
        category="Category to place the channel in (optional)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def hp_setup(
        self,
        interaction: discord.Interaction,
        name: str = "🚨・ꜱᴘᴀᴍ-ᴄʜᴇᴄᴋ",
        category: discord.CategoryChannel = None
    ):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        bot_member = guild.get_member(self.bot.user.id)

        # ── Check if a honeypot already exists ──────────────────────────────
        existing_id = self.db.get_channel(guild.id)
        if existing_id:
            existing_ch = guild.get_channel(existing_id)
            if existing_ch:
                embed = discord.Embed(
                    title="⚠️ Honeypot Already Active",
                    description=(
                        f"A honeypot is already set up at {existing_ch.mention}.\n\n"
                        "Run `/honeypot remove` first if you want to reset it."
                    ),
                    color=0xFF9900
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

        # ── Build permission overwrites ──────────────────────────────────────
        # @everyone: can VIEW + SEND (so bots/raiders are lured in)
        # Bot itself: full permissions to manage messages
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                add_reactions=False,
                attach_files=False,
                embed_links=False,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True,
                manage_channels=True,
            ),
        }

        # ── Create the channel ───────────────────────────────────────────────
        try:
            trap_channel = await guild.create_text_channel(
                name=name,
                topic="🚨 Spam Trap — Any message sent here will result in automatic punishment.",
                overwrites=overwrites,
                category=category,
                reason=f"Honeypot setup by {interaction.user}"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to create channels. Please give me **Manage Channels** permission.",
                ephemeral=True
            )
            return
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to create channel: `{e}`", ephemeral=True)
            return

        # ── Post the bait embed ──────────────────────────────────────────────
        total = self.db.get_total_triggered(guild.id)
        kicked = self.db.get_total_kicked(guild.id)

        trap_embed = discord.Embed(
            title=f"🛡️  {guild.name} — Security Verification",
            description=(
                f"**Welcome to {guild.name}**\n\n"
                "> 🔒 **Do NOT send any messages here.**\n"
                "> This channel is an automated security trap for spam bots.\n\n"
                "**Automated violation ladder:**\n"
                "• 1st message → 10 minute timeout\n"
                "• 2nd message → 24 hour timeout\n"
                "• 3rd message → Server kick"
            ),
            color=C.NEUTRAL
        )
        trap_embed.set_footer(text=f"🛡️ {guild.name} Security  •  ꜱᴘᴀᴍ ᴄʜᴇᴄᴋ ᴀᴄᴛɪᴠᴇ")

        view = discord.ui.View()
        btn1 = discord.ui.Button(
            label=f"⚠️ Users Trapped: {total}",
            style=discord.ButtonStyle.danger,
            disabled=True
        )
        btn2 = discord.ui.Button(
            label=f"🔨 Kicked: {kicked}",
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        view.add_item(btn1)
        view.add_item(btn2)

        try:
            trap_msg = await trap_channel.send(embed=trap_embed, view=view)
        except discord.Forbidden:
            await trap_channel.delete(reason="Honeypot setup failed — no send permission")
            await interaction.followup.send(
                "❌ Channel was created but I couldn't send a message in it. Channel removed. Check my permissions.",
                ephemeral=True
            )
            return

        # ── Save to DB ───────────────────────────────────────────────────────
        self.db.set_channel(guild.id, trap_channel.id, trap_msg.id)

        # ── Confirmation to admin ────────────────────────────────────────────
        confirm_embed = discord.Embed(
            title="✅  Honeypot Channel Created!",
            description=(
                f"🪤 **Trap channel:** {trap_channel.mention}\n\n"
                "**What happens when someone types there:**\n"
                "• **1st Offense:** 10 min timeout\n"
                "• **2nd Offense:** 1 day timeout\n"
                "• **3rd+ Offense:** Kicked\n\n"
                "The trap embed + counter are now live in that channel.\n\n"
                "💡 **Next step:** Run `/honeypot setlog #mod-logs` to redirect "
                "alert notifications to your mod log channel."
            ),
            color=0x00CC66
        )
        confirm_embed.add_field(
            name="📋 Channel Details",
            value=(
                f"**Name:** `{trap_channel.name}`\n"
                f"**ID:** `{trap_channel.id}`\n"
                f"**Category:** {category.name if category else 'None (root)'}"
            ),
            inline=False
        )
        confirm_embed.set_footer(text="GKR Security  •  Honeypot System")
        await interaction.followup.send(embed=confirm_embed, ephemeral=True)


    @hp_group.command(name="setlog", description="Set a channel to receive honeypot alert logs")
    @app_commands.default_permissions(manage_guild=True)
    async def hp_setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.db.set_log_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"✅ Honeypot alerts will now be sent to {channel.mention}.",
            ephemeral=True
        )

    @hp_group.command(name="clearoffenses", description="Forgive a user and reset their honeypot offense count to 0")
    @app_commands.default_permissions(manage_guild=True)
    async def hp_clear(self, interaction: discord.Interaction, user: discord.User):
        self.db.clear_offenses(interaction.guild.id, user.id)
        await interaction.response.send_message(f"✅ Reset all spam trap offenses for {user.mention}.", ephemeral=True)

    @hp_group.command(name="checkuser", description="Check how many offenses a user has in the spam trap")
    @app_commands.default_permissions(manage_guild=True)
    async def hp_checkuser(self, interaction: discord.Interaction, user: discord.User):
        count = self.db.get_user_offenses(interaction.guild.id, user.id)
        if count == 0:
            next_action = "10 min timeout"
        elif count == 1:
            next_action = "1 day timeout"
        else:
            next_action = "Kicked"
        embed = discord.Embed(title="🔍 Honeypot User Check", color=0xE74C3C)
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="Offense Count", value=f"**#{count}**", inline=True)
        embed.add_field(name="Next Punishment if triggered again", value=next_action, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @hp_group.command(name="remove", description="Delete the honeypot channel and remove it from the system")
    @app_commands.default_permissions(administrator=True)
    async def hp_remove(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        channel_id = self.db.get_channel(guild.id)
        if not channel_id:
            try:
                await interaction.followup.send(
                    "❌ No honeypot channel is set up for this server.",
                    ephemeral=True
                )
            except discord.HTTPException:
                pass
            return

        channel = guild.get_channel(channel_id)
        deleted_name = f"`#{channel.name}`" if channel else f"`(ID: {channel_id})`"

        # 1. Clear from DB first
        with self.db._conn() as conn:
            conn.execute("DELETE FROM channels WHERE guild_id = ?", (str(guild.id),))
            conn.commit()

        # 2. Send confirmation to user FIRST before deleting the channel
        embed = discord.Embed(
            title="🗑️  Honeypot Removed",
            description=(
                f"The honeypot channel {deleted_name} has been **deleted** and removed from the system.\n\n"
                "Run `/honeypot setup` to create a new one."
            ),
            color=0xFF4444
        )
        embed.set_footer(text="GKR Security  •  Honeypot System")
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            try:
                await interaction.user.send(embed=embed)
            except discord.HTTPException:
                pass

        # 3. Delete the Discord channel if it exists
        if channel:
            try:
                await channel.delete(reason=f"Honeypot removed by {interaction.user}")
            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                print(f"[Honeypot] Could not delete channel {channel_id}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(HoneypotCog(bot))
    print("🚨 Honeypot system loaded!")
