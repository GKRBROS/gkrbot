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

        # Ignore admins/mods
        if message.author.guild_permissions.manage_messages:
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

        # Send to configured log channel first, fall back to trap channel
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

    @hp_group.command(name="setchannel", description="Set a channel as the Honeypot/Spam Trap")
    @app_commands.default_permissions(manage_guild=True)
    async def hp_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        trap_embed = discord.Embed(
            title="⚠️ SPAM TRAP ⚠️",
            description="**DO NOT SEND MESSAGES IN THIS CHANNEL**\n\n"
                        "This channel is used to catch spam bots.\n\n"
                        "**Punishment if you message here:**\n"
                        "• 1st offense → 10 min timeout\n"
                        "• 2nd offense → 1 day timeout\n"
                        "• 3rd+ offense → Kicked",
            color=0x2b2d31
        )
        total = self.db.get_total_triggered(interaction.guild.id)
        kicked = self.db.get_total_kicked(interaction.guild.id)
        view = discord.ui.View()
        btn1 = discord.ui.Button(label=f"⚠️ Users Trapped: {total}", style=discord.ButtonStyle.danger, disabled=True)
        btn2 = discord.ui.Button(label=f"🔨 Kicked: {kicked}", style=discord.ButtonStyle.secondary, disabled=True)
        view.add_item(btn1)
        view.add_item(btn2)

        try:
            trap_msg = await channel.send(embed=trap_embed, view=view)
            self.db.set_channel(interaction.guild.id, channel.id, trap_msg.id)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I lack permissions to send messages in that channel.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🚨 Honeypot Channel Set",
            description=f"{channel.mention} is now the Spam Trap channel.\n\n"
                        "Any normal user who types here will be punished:\n"
                        "• **1st Offense:** 10m Timeout\n"
                        "• **2nd Offense:** 1d Timeout\n"
                        "• **3rd+ Offense:** Kicked\n\n"
                        "💡 Use `/honeypot setlog #channel` to send alerts to a mod log instead of the trap channel.",
            color=0xE74C3C
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

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


async def setup(bot: commands.Bot):
    await bot.add_cog(HoneypotCog(bot))
    print("🚨 Honeypot system loaded!")


