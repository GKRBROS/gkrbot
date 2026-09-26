"""
pinger.py — "Pinger": repeatedly pings one or more roles in a chosen channel,
deleting the previous ping before sending the next one (so the channel never
fills up with old pings), with an optional message shown next to the mentions.

Slash commands (all require Manage Server):
    /pinger channel <channel>            set the channel pings are sent to
    /pinger addrole <role>                add a role to the ping rotation
    /pinger removerole <role>             remove a role from the rotation
    /pinger text <text>                   set/replace the message shown with the ping (omit to clear)
    /pinger interval <seconds>            how often to re-ping (minimum 30s)
    /pinger start                         turn pinging on
    /pinger stop                          turn pinging off (also deletes the live ping)
    /pinger status                        show the current configuration

Behaviour:
    Every `interval` seconds, for each enabled guild:
      1. delete the previous ping message (if it still exists)
      2. send a new message mentioning every configured role, plus the
         optional custom text
      3. remember the new message id so the next cycle can delete it

Storage: pinger.sqlite3, next to this file (created automatically).

Add "pinger" to the `extensions` list in main.py to enable this cog.
"""
import os
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinger.sqlite3")

MIN_INTERVAL_SECONDS = 30
DEFAULT_INTERVAL_SECONDS = 300
LOOP_TICK_SECONDS = 15          # how often the background loop checks for due guilds
MAX_ROLES_PER_GUILD = 10
MAX_TEXT_LENGTH = 300


@dataclass
class PingerConfig:
    guild_id: int
    channel_id: Optional[int] = None
    role_ids: List[int] = field(default_factory=list)
    text: str = ""
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    enabled: bool = False
    last_message_id: Optional[int] = None
    next_run_at: int = 0   # unix timestamp; 0 = due immediately once enabled


class PingerDatabase:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pinger_configs (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    role_ids TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL DEFAULT '',
                    interval_seconds INTEGER NOT NULL DEFAULT 300,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    last_message_id INTEGER,
                    next_run_at INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def get(self, guild_id: int) -> PingerConfig:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM pinger_configs WHERE guild_id = ?", (guild_id,)).fetchone()
        if not row:
            return PingerConfig(guild_id=guild_id)
        role_ids = [int(r) for r in row["role_ids"].split(",") if r.strip().isdigit()]
        return PingerConfig(
            guild_id=guild_id,
            channel_id=row["channel_id"],
            role_ids=role_ids,
            text=row["text"] or "",
            interval_seconds=row["interval_seconds"],
            enabled=bool(row["enabled"]),
            last_message_id=row["last_message_id"],
            next_run_at=row["next_run_at"],
        )

    def save(self, cfg: PingerConfig) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pinger_configs
                    (guild_id, channel_id, role_ids, text, interval_seconds, enabled, last_message_id, next_run_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id=excluded.channel_id,
                    role_ids=excluded.role_ids,
                    text=excluded.text,
                    interval_seconds=excluded.interval_seconds,
                    enabled=excluded.enabled,
                    last_message_id=excluded.last_message_id,
                    next_run_at=excluded.next_run_at
                """,
                (
                    cfg.guild_id, cfg.channel_id, ",".join(str(r) for r in cfg.role_ids),
                    cfg.text, cfg.interval_seconds, int(cfg.enabled), cfg.last_message_id, cfg.next_run_at,
                ),
            )
            conn.commit()

    def all_enabled(self) -> List[PingerConfig]:
        with self._connect() as conn:
            rows = conn.execute("SELECT guild_id FROM pinger_configs WHERE enabled = 1").fetchall()
        return [self.get(row["guild_id"]) for row in rows]


def _build_content(cfg: PingerConfig) -> str:
    mentions = " ".join(f"<@&{rid}>" for rid in cfg.role_ids)
    if cfg.text:
        return f"{mentions}\n{cfg.text}" if mentions else cfg.text
    return mentions


class PingerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = PingerDatabase()

    async def cog_load(self):
        self.ping_loop.start()

    async def cog_unload(self):
        if self.ping_loop.is_running():
            self.ping_loop.cancel()

    # ── background loop ──────────────────────────────────────────────
    @tasks.loop(seconds=LOOP_TICK_SECONDS)
    async def ping_loop(self):
        import time
        now = int(time.time())
        for cfg in self.db.all_enabled():
            if cfg.next_run_at > now:
                continue
            await self._fire(cfg)

    @ping_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

    async def _fire(self, cfg: PingerConfig) -> None:
        import time
        if not cfg.channel_id or not cfg.role_ids:
            return
        channel = self.bot.get_channel(cfg.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(cfg.channel_id)
            except Exception:
                return

        # Delete the previous ping before sending the new one
        if cfg.last_message_id:
            try:
                old = await channel.fetch_message(cfg.last_message_id)
                await old.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        allowed = discord.AllowedMentions(roles=[discord.Object(id=r) for r in cfg.role_ids])
        try:
            msg = await channel.send(_build_content(cfg), allowed_mentions=allowed)
            cfg.last_message_id = msg.id
        except discord.Forbidden:
            print(f"[Pinger] Missing permissions in #{getattr(channel, 'name', cfg.channel_id)} (guild {cfg.guild_id})")
            cfg.last_message_id = None
        except discord.HTTPException as e:
            print(f"[Pinger] Failed to send ping in guild {cfg.guild_id}: {e}")
            cfg.last_message_id = None

        cfg.next_run_at = int(time.time()) + cfg.interval_seconds
        self.db.save(cfg)

    # ── slash commands ───────────────────────────────────────────────
    pinger = app_commands.Group(name="pinger", description="Repeating role-ping manager", default_permissions=discord.Permissions(manage_guild=True))

    @pinger.command(name="channel", description="Set the channel Pinger posts to")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def channel_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg = self.db.get(interaction.guild_id)
        cfg.channel_id = channel.id
        cfg.last_message_id = None  # old ping (if any) was in the old channel
        self.db.save(cfg)
        await interaction.response.send_message(f"✅ Pinger will post in {channel.mention}.", ephemeral=True)

    @pinger.command(name="addrole", description="Add a role to the ping rotation")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def addrole_cmd(self, interaction: discord.Interaction, role: discord.Role):
        cfg = self.db.get(interaction.guild_id)
        if role.id in cfg.role_ids:
            return await interaction.response.send_message("That role is already in the rotation.", ephemeral=True)
        if len(cfg.role_ids) >= MAX_ROLES_PER_GUILD:
            return await interaction.response.send_message(f"You can add at most {MAX_ROLES_PER_GUILD} roles.", ephemeral=True)
        if role.is_default():
            return await interaction.response.send_message("Use `/pinger text` for an @everyone-style notice instead — roles only here.", ephemeral=True)

        # THE likely reason a role doesn't actually ping: Discord requires the
        # "Mention @everyone, @here, and All Roles" permission to notify a role
        # that has "Allow anyone to mention this role" turned OFF -- even for a
        # bot using allowed_mentions. Warn up front instead of failing silently.
        warning = ""
        if not role.mentionable:
            me_perms = interaction.channel.permissions_for(interaction.guild.me)
            if not me_perms.mention_everyone:
                warning = (
                    f"\n⚠️ **{role.name} won't actually ping anyone yet** — it isn't mentionable, "
                    f"and I don't have **Mention @everyone, @here, and All Roles** permission. "
                    f"Either turn on 'Allow anyone to mention this role' in the role's settings, "
                    f"or grant me that permission."
                )
        cfg.role_ids.append(role.id)
        self.db.save(cfg)
        await interaction.response.send_message(f"✅ Added {role.mention} to the rotation.{warning}", ephemeral=True)

    @pinger.command(name="removerole", description="Remove a role from the ping rotation")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def removerole_cmd(self, interaction: discord.Interaction, role: discord.Role):
        cfg = self.db.get(interaction.guild_id)
        if role.id not in cfg.role_ids:
            return await interaction.response.send_message("That role isn't in the rotation.", ephemeral=True)
        cfg.role_ids.remove(role.id)
        self.db.save(cfg)
        await interaction.response.send_message(f"✅ Removed {role.mention} from the rotation.", ephemeral=True)

    @pinger.command(name="text", description="Set the message shown next to the ping (leave blank to clear)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def text_cmd(self, interaction: discord.Interaction, text: Optional[str] = None):
        text = (text or "").strip()[:MAX_TEXT_LENGTH]
        cfg = self.db.get(interaction.guild_id)
        cfg.text = text
        self.db.save(cfg)
        if text:
            await interaction.response.send_message(f"✅ Ping text set to:\n> {text}", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Ping text cleared — only the role mentions will be sent.", ephemeral=True)

    @pinger.command(name="interval", description=f"How often to re-ping, in seconds (min {MIN_INTERVAL_SECONDS})")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def interval_cmd(self, interaction: discord.Interaction, seconds: app_commands.Range[int, MIN_INTERVAL_SECONDS, 86400]):
        cfg = self.db.get(interaction.guild_id)
        cfg.interval_seconds = seconds
        self.db.save(cfg)
        await interaction.response.send_message(f"✅ Pinger will now re-ping every {seconds} seconds.", ephemeral=True)

    @pinger.command(name="start", description="Start the repeating ping")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def start_cmd(self, interaction: discord.Interaction):
        cfg = self.db.get(interaction.guild_id)
        if not cfg.channel_id:
            return await interaction.response.send_message("Set a channel first with `/pinger channel`.", ephemeral=True)
        if not cfg.role_ids:
            return await interaction.response.send_message("Add at least one role first with `/pinger addrole`.", ephemeral=True)
        channel = self.bot.get_channel(cfg.channel_id)
        warning = ""
        if channel is not None:
            me_perms = channel.permissions_for(interaction.guild.me)
            if not me_perms.mention_everyone:
                non_mentionable = [
                    r for rid in cfg.role_ids
                    if (r := interaction.guild.get_role(rid)) is not None and not r.mentionable
                ]
                if non_mentionable:
                    names = ", ".join(r.name for r in non_mentionable)
                    warning = (
                        f"\n⚠️ **{names}** won't actually notify anyone — turn on "
                        f"'Allow anyone to mention this role' for them, or grant me **Mention "
                        f"@everyone, @here, and All Roles** permission in {channel.mention}."
                    )
            if not me_perms.send_messages:
                warning += f"\n⚠️ I don't have permission to send messages in {channel.mention}."

        cfg.enabled = True
        cfg.next_run_at = 0  # fire on the next loop tick
        self.db.save(cfg)
        await interaction.response.send_message(f"✅ Pinger started.{warning}", ephemeral=True)

    @pinger.command(name="stop", description="Stop the repeating ping and remove the live message")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def stop_cmd(self, interaction: discord.Interaction):
        cfg = self.db.get(interaction.guild_id)
        cfg.enabled = False
        if cfg.channel_id and cfg.last_message_id:
            channel = self.bot.get_channel(cfg.channel_id)
            if channel:
                try:
                    old = await channel.fetch_message(cfg.last_message_id)
                    await old.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
        cfg.last_message_id = None
        self.db.save(cfg)
        await interaction.response.send_message("🛑 Pinger stopped.", ephemeral=True)

    @pinger.command(name="status", description="Show the current Pinger configuration")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status_cmd(self, interaction: discord.Interaction):
        cfg = self.db.get(interaction.guild_id)
        channel = f"<#{cfg.channel_id}>" if cfg.channel_id else "*not set*"
        roles = ", ".join(f"<@&{r}>" for r in cfg.role_ids) if cfg.role_ids else "*none*"
        embed = discord.Embed(title="📌 Pinger Status", color=0x5865F2 if cfg.enabled else 0x99AAB5)
        embed.add_field(name="State", value="🟢 Running" if cfg.enabled else "🔴 Stopped", inline=True)
        embed.add_field(name="Interval", value=f"{cfg.interval_seconds}s", inline=True)
        embed.add_field(name="Channel", value=channel, inline=False)
        embed.add_field(name="Roles", value=roles, inline=False)
        embed.add_field(name="Text", value=cfg.text or "*none*", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You need **Manage Server** to use Pinger commands.", ephemeral=True)
        else:
            print(f"[Pinger] Command error: {error!r}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Something went wrong running that command.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    # bot.add_cog() already walks the cog's class attributes and registers
    # `pinger` (an app_commands.Group) on the tree — a second, manual
    # bot.tree.add_command(cog.pinger) call here re-adds the same group and
    # raises CommandAlreadyRegistered.
    cog = PingerCog(bot)
    await bot.add_cog(cog)