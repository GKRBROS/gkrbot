"""
blacklist.py — global server and member blacklist.

WHAT THIS DOES
    - Server blacklist: bot stays in the guild but ignores everything from it.
    - Member blacklist: that user is ignored everywhere (all guilds + DMs),
      everyone else in the guild is unaffected.
    - Blacklisted parties get ZERO response of any kind — no message, no
      ephemeral reply, no DM. Interactions that require an ack are silently
      deferred (nothing visible happens) so Discord doesn't show its own
      "This interaction failed" toast.
    - Persisted in SQLite (blacklist.sqlite3) — survives restarts, and a
      re-join by a blacklisted guild is blocked immediately.

WHO CAN MANAGE IT
    Reuses the SAME "bot staff" identity as the dashboard's Admin Panel
    (admin_api.py's `_is_admin`): the bot's application owner(s), plus any ID
    listed in the ADMIN_USER_IDS env var. There is deliberately only ONE list
    of trusted people for the whole project, not a second parallel one.

    A guild's own "Administrator" permission means NOTHING here — only the
    identities above can use these commands, anywhere.

STAYING HIDDEN ("developer cmd only, not seen by others")
    Set BLACKLIST_DEV_GUILD_ID in your environment to your own private
    server's ID. The /blacklist and /unblacklist command groups are then
    registered ONLY in that one server, via Discord's per-guild command
    scoping — they will not show up in the command list of any other server,
    for any member, including regular admins. (is_bot_staff() is still
    enforced on top of this, so even people in your dev server can't run it
    unless they're on the approved list.)
    If BLACKLIST_DEV_GUILD_ID is not set, the commands register globally but
    remain fully permission-gated — just less hidden.

COVERAGE / KNOWN LIMITS
    Enforced globally for: prefix commands, slash commands, and context-menu
    commands (via a bot-wide check + the command tree's interaction_check —
    every command in every cog is covered automatically, no per-cog changes
    needed).
    Buttons / selects / modals that belong to a *persistent custom View*
    (not a slash command's own response) are dispatched by discord.py
    outside the command tree, so a single global hook can't block their
    callback from running. Two things are provided for that: `blacklist_gate`
    below (call it as the first line of a view callback to bail out safely),
    and a best-effort `on_interaction` listener that pre-empts the most common
    case by deferring the interaction before your view's own callback runs
    (works when this cog loads before the cog owning that view; not a hard
    guarantee for every possible view in the project).

Add "blacklist" to the `extensions` list in main.py — early is best.
"""
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = Path(__file__).resolve().parent / "blacklist.sqlite3"
DEV_GUILD_ID = os.getenv("BLACKLIST_DEV_GUILD_ID", "").strip()
_DEV_GUILD = int(DEV_GUILD_ID) if DEV_GUILD_ID.isdigit() else None

MAX_REASON_LEN = 300


# ──────────────────────────────────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────────────────────────────────
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blacklisted_servers (
                guild_id INTEGER PRIMARY KEY,
                guild_name TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                blacklisted_by INTEGER,
                blacklisted_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blacklisted_members (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                blacklisted_by INTEGER,
                blacklisted_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blacklist_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                target_label TEXT NOT NULL DEFAULT '',
                performed_by INTEGER,
                reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bl_servers_guild ON blacklisted_servers(guild_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bl_members_user ON blacklisted_members(user_id)")
        conn.commit()


_init_db()


def _log_action(action: str, target_id: int, target_label: str, performed_by: Optional[int], reason: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO blacklist_audit_log (action, target_id, target_label, performed_by, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (action, target_id, target_label, performed_by, reason, int(time.time())),
        )
        conn.commit()


class BlacklistStore:
    """In-memory sets mirrored from SQLite, so the hot-path check (every
    single command/interaction) never touches disk. Reloaded at cog_load and
    kept in sync on every add/remove."""

    def __init__(self):
        self.server_ids: set[int] = set()
        self.member_ids: set[int] = set()
        self.reload()

    def reload(self) -> None:
        with _connect() as conn:
            self.server_ids = {r["guild_id"] for r in conn.execute("SELECT guild_id FROM blacklisted_servers")}
            self.member_ids = {r["user_id"] for r in conn.execute("SELECT user_id FROM blacklisted_members")}

    # -- servers --
    def add_server(self, guild_id: int, guild_name: str, reason: str, by_id: Optional[int]) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO blacklisted_servers (guild_id, guild_name, reason, blacklisted_by, blacklisted_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET guild_name=excluded.guild_name, reason=excluded.reason, "
                "blacklisted_by=excluded.blacklisted_by, blacklisted_at=excluded.blacklisted_at",
                (guild_id, guild_name, reason, by_id, int(time.time())),
            )
            conn.commit()
        self.server_ids.add(guild_id)
        _log_action("SERVER_BLACKLIST", guild_id, guild_name, by_id, reason)

    def remove_server(self, guild_id: int, by_id: Optional[int]) -> bool:
        with _connect() as conn:
            row = conn.execute("SELECT guild_name FROM blacklisted_servers WHERE guild_id = ?", (guild_id,)).fetchone()
            cur = conn.execute("DELETE FROM blacklisted_servers WHERE guild_id = ?", (guild_id,))
            conn.commit()
        self.server_ids.discard(guild_id)
        if cur.rowcount:
            _log_action("SERVER_UNBLACKLIST", guild_id, row["guild_name"] if row else "", by_id, "")
            return True
        return False

    def get_server(self, guild_id: int) -> Optional[sqlite3.Row]:
        with _connect() as conn:
            return conn.execute("SELECT * FROM blacklisted_servers WHERE guild_id = ?", (guild_id,)).fetchone()

    def list_servers(self):
        with _connect() as conn:
            return conn.execute("SELECT * FROM blacklisted_servers ORDER BY blacklisted_at DESC").fetchall()

    # -- members --
    def add_member(self, user_id: int, username: str, reason: str, by_id: Optional[int]) -> None:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO blacklisted_members (user_id, username, reason, blacklisted_by, blacklisted_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, reason=excluded.reason, "
                "blacklisted_by=excluded.blacklisted_by, blacklisted_at=excluded.blacklisted_at",
                (user_id, username, reason, by_id, int(time.time())),
            )
            conn.commit()
        self.member_ids.add(user_id)
        _log_action("MEMBER_BLACKLIST", user_id, username, by_id, reason)

    def remove_member(self, user_id: int, by_id: Optional[int]) -> bool:
        with _connect() as conn:
            row = conn.execute("SELECT username FROM blacklisted_members WHERE user_id = ?", (user_id,)).fetchone()
            cur = conn.execute("DELETE FROM blacklisted_members WHERE user_id = ?", (user_id,))
            conn.commit()
        self.member_ids.discard(user_id)
        if cur.rowcount:
            _log_action("MEMBER_UNBLACKLIST", user_id, row["username"] if row else "", by_id, "")
            return True
        return False

    def get_member(self, user_id: int) -> Optional[sqlite3.Row]:
        with _connect() as conn:
            return conn.execute("SELECT * FROM blacklisted_members WHERE user_id = ?", (user_id,)).fetchone()

    def list_members(self):
        with _connect() as conn:
            return conn.execute("SELECT * FROM blacklisted_members ORDER BY blacklisted_at DESC").fetchall()


STORE = BlacklistStore()


# ──────────────────────────────────────────────────────────────────────────
# Public helpers — importable from any other cog / the dashboard
# ──────────────────────────────────────────────────────────────────────────
async def is_server_blacklisted(guild_id: Optional[int]) -> bool:
    return bool(guild_id) and guild_id in STORE.server_ids


async def is_member_blacklisted(user_id: Optional[int]) -> bool:
    return bool(user_id) and user_id in STORE.member_ids


def is_bot_staff_id(user_id: int, bot: commands.Bot) -> bool:
    """The single source of truth for 'who can touch global bot controls' —
    the same identity used by the dashboard's Admin Panel (admin_api.py)."""
    owner_id = getattr(bot, "owner_id", None)
    if owner_id and int(owner_id) == int(user_id):
        return True
    if int(user_id) in {int(i) for i in (getattr(bot, "owner_ids", None) or [])}:
        return True
    for raw in (os.getenv("ADMIN_USER_IDS") or "").split(","):
        raw = raw.strip()
        if raw.isdigit() and int(raw) == int(user_id):
            return True
    return False


async def is_bot_staff(interaction_or_ctx, bot: commands.Bot) -> bool:
    user = getattr(interaction_or_ctx, "user", None) or getattr(interaction_or_ctx, "author", None)
    if user is None:
        return False
    if is_bot_staff_id(user.id, bot):
        return True
    # Fall back to Discord's own "who owns this application" check, in case
    # ADMIN_USER_IDS isn't set and owner_id/owner_ids haven't been cached yet.
    try:
        return await bot.is_owner(user)
    except Exception:
        return False


async def blacklist_gate(interaction: discord.Interaction) -> bool:
    """Call as the FIRST line of any button/select/modal callback that isn't
    reached through the command tree:

        async def on_click(self, interaction, button):
            if not await blacklist_gate(interaction):
                return
            ...

    Returns False (and silently acks the interaction) if the guild or the
    user is blacklisted; True otherwise."""
    guild_id = interaction.guild_id
    user_id = interaction.user.id if interaction.user else None
    if await is_server_blacklisted(guild_id) or await is_member_blacklisted(user_id):
        await _silent_ack(interaction)
        return False
    return True


async def _silent_ack(interaction: discord.Interaction) -> None:
    """Acknowledge without showing the user anything, so Discord doesn't
    surface its own 'This interaction failed' toast. Best-effort: if the
    interaction was already responded to elsewhere, this just no-ops."""
    try:
        if not interaction.response.is_done():
            await interaction.response.defer()
    except (discord.InteractionResponded, discord.HTTPException, discord.NotFound):
        pass


def _clean_reason(reason: Optional[str]) -> str:
    if not reason:
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", reason).strip()[:MAX_REASON_LEN]


def _fmt_time(ts: Optional[int]) -> str:
    return f"<t:{ts}:f>" if ts else "unknown"


# ──────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────
class BlacklistCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Global gate for prefix commands.
        self.bot.add_check(self._prefix_check)
        # Global gate for slash + context-menu commands. This intentionally
        # OVERWRITES bot.tree.interaction_check; if another cog in this
        # project also sets one, only the last cog loaded wins, so keep
        # "blacklist" near the top of main.py's extensions list.
        self.bot.tree.interaction_check = self._tree_check

    async def cog_unload(self):
        try:
            self.bot.remove_check(self._prefix_check)
        except Exception:
            pass

    async def _prefix_check(self, ctx: commands.Context) -> bool:
        if ctx.guild and await is_server_blacklisted(ctx.guild.id):
            return False
        if await is_member_blacklisted(ctx.author.id):
            return False
        return True

    async def _tree_check(self, interaction: discord.Interaction) -> bool:
        blocked = False
        if interaction.guild_id and await is_server_blacklisted(interaction.guild_id):
            blocked = True
        elif interaction.user and await is_member_blacklisted(interaction.user.id):
            blocked = True
        if blocked:
            await _silent_ack(interaction)
            return False
        return True

    # Best-effort coverage for standalone component interactions that don't
    # go through the command tree at all (see module docstring's Known Limits).
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type not in (discord.InteractionType.component, discord.InteractionType.modal_submit):
            return
        if interaction.guild_id and await is_server_blacklisted(interaction.guild_id):
            await _silent_ack(interaction)
        elif interaction.user and await is_member_blacklisted(interaction.user.id):
            await _silent_ack(interaction)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # Re-joining a blacklisted server does NOT lift the blacklist —
        # the check above already covers it going forward, this just logs it.
        if await is_server_blacklisted(guild.id):
            print(f"[Blacklist] Blacklisted guild {guild.id} ({guild.name}) re-added the bot — remains inactive there.")

    # ── command groups ───────────────────────────────────────────────
    blacklist_group = app_commands.Group(
        name="blacklist", description="[Bot staff only] Manage the global server/member blacklist",
        guild_ids=[_DEV_GUILD] if _DEV_GUILD else None,
    )
    unblacklist_group = app_commands.Group(
        name="unblacklist", description="[Bot staff only] Remove a server/member from the blacklist",
        guild_ids=[_DEV_GUILD] if _DEV_GUILD else None,
    )

    async def _require_staff(self, interaction: discord.Interaction) -> bool:
        if await is_bot_staff(interaction, self.bot):
            return True
        # Deliberately looks like a normal "command not found" to anyone who
        # somehow reaches it — never confirms this command exists to non-staff.
        await interaction.response.send_message("Unknown command.", ephemeral=True)
        return False

    # ── server blacklist ─────────────────────────────────────────────
    @blacklist_group.command(name="server", description="Blacklist a server by ID")
    @app_commands.describe(server_id="The guild/server ID to blacklist", reason="Optional reason")
    async def blacklist_server(self, interaction: discord.Interaction, server_id: str, reason: Optional[str] = None):
        if not await self._require_staff(interaction):
            return
        if not server_id.isdigit():
            return await interaction.response.send_message("That doesn't look like a valid server ID.", ephemeral=True)
        gid = int(server_id)
        guild = self.bot.get_guild(gid)
        STORE.add_server(gid, guild.name if guild else "", _clean_reason(reason), interaction.user.id)
        await interaction.response.send_message(
            f"✅ Server `{gid}`{f' ({guild.name})' if guild else ''} is now blacklisted.", ephemeral=True
        )

    @unblacklist_group.command(name="server", description="Remove a server from the blacklist")
    @app_commands.describe(server_id="The guild/server ID to unblacklist")
    async def unblacklist_server(self, interaction: discord.Interaction, server_id: str):
        if not await self._require_staff(interaction):
            return
        if not server_id.isdigit():
            return await interaction.response.send_message("That doesn't look like a valid server ID.", ephemeral=True)
        ok = STORE.remove_server(int(server_id), interaction.user.id)
        msg = f"✅ Server `{server_id}` removed from the blacklist." if ok else "That server isn't blacklisted."
        await interaction.response.send_message(msg, ephemeral=True)

    @blacklist_group.command(name="servers", description="List blacklisted servers")
    async def blacklist_servers(self, interaction: discord.Interaction):
        if not await self._require_staff(interaction):
            return
        rows = STORE.list_servers()
        if not rows:
            return await interaction.response.send_message("No servers are blacklisted.", ephemeral=True)
        embed = discord.Embed(title="🚫 Blacklisted Servers", color=0xED4245)
        for r in rows[:25]:
            embed.add_field(
                name=f"{r['guild_name'] or 'Unknown'} ({r['guild_id']})",
                value=f"By <@{r['blacklisted_by']}> · {_fmt_time(r['blacklisted_at'])}\n{r['reason'] or '*no reason*'}",
                inline=False,
            )
        if len(rows) > 25:
            embed.set_footer(text=f"+{len(rows) - 25} more not shown")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @blacklist_group.command(name="serverinfo", description="Show details for a blacklisted server")
    @app_commands.describe(server_id="The guild/server ID")
    async def blacklist_serverinfo(self, interaction: discord.Interaction, server_id: str):
        if not await self._require_staff(interaction):
            return
        if not server_id.isdigit():
            return await interaction.response.send_message("That doesn't look like a valid server ID.", ephemeral=True)
        row = STORE.get_server(int(server_id))
        if not row:
            return await interaction.response.send_message("That server isn't blacklisted.", ephemeral=True)
        embed = discord.Embed(title=f"Server {row['guild_id']}", color=0xED4245)
        embed.add_field(name="Name", value=row["guild_name"] or "Unknown", inline=True)
        embed.add_field(name="Status", value="🔴 Blacklisted", inline=True)
        embed.add_field(name="Blacklisted by", value=f"<@{row['blacklisted_by']}>", inline=True)
        embed.add_field(name="Date", value=_fmt_time(row["blacklisted_at"]), inline=True)
        embed.add_field(name="Reason", value=row["reason"] or "*no reason given*", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @blacklist_group.command(name="server-leave", description="Blacklist a server and make the bot leave it")
    @app_commands.describe(server_id="The guild/server ID", reason="Optional reason")
    async def blacklist_server_leave(self, interaction: discord.Interaction, server_id: str, reason: Optional[str] = None):
        if not await self._require_staff(interaction):
            return
        if not server_id.isdigit():
            return await interaction.response.send_message("That doesn't look like a valid server ID.", ephemeral=True)
        gid = int(server_id)
        guild = self.bot.get_guild(gid)
        # Blacklist FIRST (so even if leaving fails/is slow, the guild is
        # already inert), then attempt to leave.
        STORE.add_server(gid, guild.name if guild else "", _clean_reason(reason), interaction.user.id)
        left = False
        if guild:
            try:
                await guild.leave()
                left = True
            except discord.HTTPException as e:
                print(f"[Blacklist] Failed to leave guild {gid}: {e}")
        await interaction.response.send_message(
            f"✅ Server `{gid}` blacklisted"
            + (" and left." if left else ", but I wasn't in it (or couldn't leave) — it stays blocked if I'm ever added back."),
            ephemeral=True,
        )

    # ── member blacklist ─────────────────────────────────────────────
    @blacklist_group.command(name="member", description="Blacklist a user by ID")
    @app_commands.describe(user_id="The user ID to blacklist", reason="Optional reason")
    async def blacklist_member(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = None):
        if not await self._require_staff(interaction):
            return
        if not user_id.isdigit():
            return await interaction.response.send_message("That doesn't look like a valid user ID.", ephemeral=True)
        uid = int(user_id)
        user = self.bot.get_user(uid)
        STORE.add_member(uid, str(user) if user else "", _clean_reason(reason), interaction.user.id)
        await interaction.response.send_message(f"✅ User `{uid}`{f' ({user})' if user else ''} is now blacklisted.", ephemeral=True)

    @unblacklist_group.command(name="member", description="Remove a user from the blacklist")
    @app_commands.describe(user_id="The user ID to unblacklist")
    async def unblacklist_member(self, interaction: discord.Interaction, user_id: str):
        if not await self._require_staff(interaction):
            return
        if not user_id.isdigit():
            return await interaction.response.send_message("That doesn't look like a valid user ID.", ephemeral=True)
        ok = STORE.remove_member(int(user_id), interaction.user.id)
        msg = f"✅ User `{user_id}` removed from the blacklist." if ok else "That user isn't blacklisted."
        await interaction.response.send_message(msg, ephemeral=True)

    @blacklist_group.command(name="members", description="List blacklisted users")
    async def blacklist_members(self, interaction: discord.Interaction):
        if not await self._require_staff(interaction):
            return
        rows = STORE.list_members()
        if not rows:
            return await interaction.response.send_message("No users are blacklisted.", ephemeral=True)
        embed = discord.Embed(title="🚫 Blacklisted Members", color=0xED4245)
        for r in rows[:25]:
            embed.add_field(
                name=f"{r['username'] or 'Unknown'} ({r['user_id']})",
                value=f"By <@{r['blacklisted_by']}> · {_fmt_time(r['blacklisted_at'])}\n{r['reason'] or '*no reason*'}",
                inline=False,
            )
        if len(rows) > 25:
            embed.set_footer(text=f"+{len(rows) - 25} more not shown")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @blacklist_group.command(name="memberinfo", description="Show details for a blacklisted user")
    @app_commands.describe(user_id="The user ID")
    async def blacklist_memberinfo(self, interaction: discord.Interaction, user_id: str):
        if not await self._require_staff(interaction):
            return
        if not user_id.isdigit():
            return await interaction.response.send_message("That doesn't look like a valid user ID.", ephemeral=True)
        row = STORE.get_member(int(user_id))
        if not row:
            return await interaction.response.send_message("That user isn't blacklisted.", ephemeral=True)
        embed = discord.Embed(title=f"User {row['user_id']}", color=0xED4245)
        embed.add_field(name="Username", value=row["username"] or "Unknown", inline=True)
        embed.add_field(name="Status", value="🔴 Blacklisted", inline=True)
        embed.add_field(name="Blacklisted by", value=f"<@{row['blacklisted_by']}>", inline=True)
        embed.add_field(name="Date", value=_fmt_time(row["blacklisted_at"]), inline=True)
        embed.add_field(name="Reason", value=row["reason"] or "*no reason given*", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        print(f"[Blacklist] Command error: {error!r}")
        if not interaction.response.is_done():
            try:
                await interaction.response.send_message("Something went wrong running that command.", ephemeral=True)
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot) -> None:
    cog = BlacklistCog(bot)
    # NOTE: do NOT also call bot.tree.add_command() for the groups — Groups
    # declared as Cog class attributes are registered automatically by add_cog.
    await bot.add_cog(cog)
    if _DEV_GUILD:
        print(f"[Blacklist] Commands restricted to dev guild {DEV_GUILD_ID} — invisible everywhere else.")
    else:
        print("[Blacklist] BLACKLIST_DEV_GUILD_ID not set — commands are global. Set it to hide them from other servers.")