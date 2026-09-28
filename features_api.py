"""
features_api.py — dashboard endpoints for bot features that previously had
commands but no website setup page.

    GET/POST /api/guilds/{guild_id}/protection            anti-link / anti-spam / anti-raid + log channel
    GET/POST /api/guilds/{guild_id}/anti-hacked           anti-hacked-account protection
    GET/POST /api/guilds/{guild_id}/verification          verified role / log channel / min account age
    POST     /api/guilds/{guild_id}/verification/panel    post the "Verify Me" button panel to a channel

ALSO INCLUDED: guild_access_middleware
    The dashboard's existing `check_guild_permissions()` only checks "is the
    caller logged in" — it does NOT check that the caller manages the guild in
    the URL. That means any logged-in Discord user could read or change any
    server's settings by editing the guild id in the URL. This middleware
    closes that hole for EVERY /api/guilds/{guild_id}/... route (existing and
    new): the caller must be the owner or hold Administrator in that guild,
    which is the exact same rule /api/users/@me already uses to decide which
    servers to show in the server picker, so nothing legitimate is blocked.
    Bot staff (owner / ADMIN_USER_IDS) are exempt so support can help.

Wire-up (dashboard_api.py cog_load):

    from features_api import register_feature_routes, guild_access_middleware
    app = web.Application(middlewares=[cors_middleware, guild_access_middleware])
    ...
    register_feature_routes(app, _get_session)
"""
import asyncio
import re
import time

import aiohttp
import discord
from aiohttp import web

_GUILD_PATH = re.compile(r"^/api/guilds/(\d+)(?:/|$)")
_CACHE_TTL = 60  # seconds a user's guild list is cached (protects Discord's rate limit)
_guild_cache: dict = {}   # token -> (expires_at, {guild_id: can_manage})
_locks: dict = {}         # token -> asyncio.Lock (one Discord call per user at a time)


def _json_error(message: str, status: int):
    return web.json_response({"error": message}, status=status)


async def _managed_guild_ids(session_data: dict, token: str):
    """Guild ids the user owns or holds Administrator in. Cached briefly."""
    now = time.time()
    hit = _guild_cache.get(token)
    if hit and hit[0] > now:
        return hit[1]

    lock = _locks.setdefault(token, asyncio.Lock())
    async with lock:
        hit = _guild_cache.get(token)  # another request may have filled it while we waited
        if hit and hit[0] > time.time():
            return hit[1]
        headers = {"Authorization": f"Bearer {session_data['access_token']}"}
        async with aiohttp.ClientSession() as http:
            async with http.get("https://discord.com/api/users/@me/guilds", headers=headers) as resp:
                if resp.status != 200:
                    return None
                guilds = await resp.json()
        allowed = set()
        for g in guilds:
            perms = int(g.get("permissions", "0"))
            if (perms & 0x8) == 0x8 or g.get("owner"):
                allowed.add(int(g["id"]))
        _guild_cache[token] = (time.time() + _CACHE_TTL, allowed)
        return allowed


def _is_bot_staff(bot, user_id) -> bool:
    try:
        from blacklist import is_bot_staff_id
        return is_bot_staff_id(int(user_id), bot)
    except Exception:
        return False


@web.middleware
async def guild_access_middleware(request: web.Request, handler):
    m = _GUILD_PATH.match(request.path)
    if not m or request.method == "OPTIONS":
        return await handler(request)

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return _json_error("Unauthorized", 401)
    token = auth.split(" ", 1)[1]

    from dashboard_api import SESSIONS  # imported lazily: dashboard_api imports this module
    sess = SESSIONS.get(token)
    if not sess:
        return _json_error("Unauthorized", 401)

    # A blacklisted server or a blacklisted caller gets a plain 404, as if the
    # server simply doesn't exist -- no "you're blacklisted" message, no 403
    # that would confirm the server exists but is off-limits. Checked BEFORE
    # the bot-staff bypass below, so even staff testing the flow see the same
    # 404 a real blacklisted user would (staff can still use /unblacklist).
    try:
        from blacklist import is_server_blacklisted, is_member_blacklisted
        guild_id = int(m.group(1))
        if await is_server_blacklisted(guild_id) or await is_member_blacklisted(int(sess.get("user_id", 0))):
            return _json_error("Not Found", 404)
    except ImportError:
        pass  # blacklist.py not installed -- nothing to enforce

    if _is_bot_staff(request.app["bot"], sess.get("user_id")):
        return await handler(request)

    try:
        allowed = await _managed_guild_ids(sess, token)
    except Exception as e:
        print(f"[GuildAccess] Could not verify guild access: {e!r}")
        return _json_error("Could not verify your server permissions. Try again.", 503)
    if allowed is None:
        return _json_error("Session expired, please log in again", 401)
    if int(m.group(1)) not in allowed:
        return _json_error("You don't have permission to manage this server.", 403)
    return await handler(request)


# ─────────────────────────────────────────────────────────────────────────────
def _snowflake_or_none(value):
    v = str(value).strip() if value not in (None, "") else ""
    return v if v.isdigit() else None


def register_feature_routes(app: web.Application, get_session) -> None:
    def guild_of(request: web.Request):
        bot = request.app["bot"]
        guild = bot.get_guild(int(request.match_info["guild_id"]))
        return bot, guild

    def need_login(request: web.Request):
        return get_session(request) is None

    # ── Protection (anti-link / anti-spam / anti-raid) ───────────────
    async def protection_get(request: web.Request):
        if need_login(request):
            return _json_error("Unauthorized", 401)
        import protection
        db = protection.ProtectionDB()
        db.initialize()
        cfg = db.get_config(int(request.match_info["guild_id"]))
        return web.json_response({"config": {
            "anti_link": bool(cfg.get("anti_link")),
            "anti_spam": bool(cfg.get("anti_spam")),
            "anti_raid": bool(cfg.get("anti_raid")),
            "log_channel_id": cfg.get("log_channel_id") or "",
        }})

    async def protection_post(request: web.Request):
        if need_login(request):
            return _json_error("Unauthorized", 401)
        try:
            data = await request.json()
        except Exception:
            return _json_error("Invalid request.")
        bot, guild = guild_of(request)
        if guild is None:
            return _json_error("Guild not found", 404)
        import protection
        db = protection.ProtectionDB()
        db.initialize()
        gid = guild.id
        for key in ("anti_link", "anti_spam", "anti_raid"):
            if key in data:
                db.set_config(gid, key, 1 if data[key] else 0)
        if "log_channel_id" in data:
            chan = _snowflake_or_none(data["log_channel_id"])
            if chan and guild.get_channel(int(chan)) is None:
                return _json_error("That log channel isn't in this server.")
            db.set_config(gid, "log_channel_id", chan)
        return web.json_response({"success": True})

    # ── Anti-Hacked ──────────────────────────────────────────────────
    async def antihacked_get(request: web.Request):
        if need_login(request):
            return _json_error("Unauthorized", 401)
        import anti_hacked
        cfg = anti_hacked.AntiHackedDB().get_config(int(request.match_info["guild_id"]))
        return web.json_response({"config": {
            "enabled": bool(cfg.get("enabled")),
            "log_channel_id": cfg.get("log_channel_id") or "",
        }})

    async def antihacked_post(request: web.Request):
        if need_login(request):
            return _json_error("Unauthorized", 401)
        try:
            data = await request.json()
        except Exception:
            return _json_error("Invalid request.")
        bot, guild = guild_of(request)
        if guild is None:
            return _json_error("Guild not found", 404)
        import anti_hacked
        db = anti_hacked.AntiHackedDB()
        if "enabled" in data:
            db.set_config(guild.id, "enabled", 1 if data["enabled"] else 0)
        if "log_channel_id" in data:
            chan = _snowflake_or_none(data["log_channel_id"])
            if chan and guild.get_channel(int(chan)) is None:
                return _json_error("That log channel isn't in this server.")
            db.set_config(guild.id, "log_channel_id", chan)
        return web.json_response({"success": True})

    # ── Verification ─────────────────────────────────────────────────
    async def verification_get(request: web.Request):
        if need_login(request):
            return _json_error("Unauthorized", 401)
        import community
        db = community.CommunityDatabase()
        db.initialize()
        cfg = db.get_verify_config(int(request.match_info["guild_id"]))
        return web.json_response({"config": {
            "verified_role_id": cfg.get("verified_role_id") or "",
            "log_channel_id": cfg.get("log_channel_id") or "",
            "min_account_days": int(cfg.get("min_account_days") or 0),
        }})

    async def verification_post(request: web.Request):
        if need_login(request):
            return _json_error("Unauthorized", 401)
        try:
            data = await request.json()
        except Exception:
            return _json_error("Invalid request.")
        bot, guild = guild_of(request)
        if guild is None:
            return _json_error("Guild not found", 404)

        role_id = _snowflake_or_none(data.get("verified_role_id"))
        if role_id:
            role = guild.get_role(int(role_id))
            if role is None:
                return _json_error("That role isn't in this server.")
            if role.is_default() or role.managed:
                return _json_error("Pick a normal role (not @everyone or a bot/integration role).")
            if role >= guild.me.top_role:
                return _json_error(f"I can't assign “{role.name}” — move my role above it in Server Settings → Roles.")
            if role.permissions.administrator:
                return _json_error("For safety, the verified role can't have Administrator permission.")
        chan = _snowflake_or_none(data.get("log_channel_id"))
        if chan and guild.get_channel(int(chan)) is None:
            return _json_error("That log channel isn't in this server.")
        try:
            days = max(0, min(365, int(data.get("min_account_days") or 0)))
        except (TypeError, ValueError):
            return _json_error("Minimum account age must be a number of days.")

        import community
        db = community.CommunityDatabase()
        db.initialize()
        db.set_verify_config(guild.id, verified_role_id=role_id, log_channel_id=chan, min_account_days=days)
        return web.json_response({"success": True})

    async def verification_panel(request: web.Request):
        if need_login(request):
            return _json_error("Unauthorized", 401)
        try:
            data = await request.json()
        except Exception:
            return _json_error("Invalid request.")
        bot, guild = guild_of(request)
        if guild is None:
            return _json_error("Guild not found", 404)

        import community
        from gkr_ui import C
        db = community.CommunityDatabase()
        db.initialize()
        cfg = db.get_verify_config(guild.id)
        if not cfg.get("verified_role_id"):
            return _json_error("Set and save a verified role first.")
        role = guild.get_role(int(cfg["verified_role_id"]))
        if role is None:
            return _json_error("The saved verified role no longer exists — pick a new one and save.")

        chan_id = _snowflake_or_none(data.get("channel_id"))
        channel = guild.get_channel(int(chan_id)) if chan_id else None
        if not isinstance(channel, discord.TextChannel):
            return _json_error("Choose a text channel to post the panel in.")
        perms = channel.permissions_for(guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            return _json_error(f"I need View Channel, Send Messages and Embed Links in #{channel.name}.")

        title = str(data.get("title") or "✅  Member Verification").strip()[:100]
        default_desc = (
            f"Welcome to **{guild.name}**!\n\n"
            f"Click the button below to verify yourself and gain access to the server.\n"
            f"You will receive the **{role.mention}** role."
        )
        desc = str(data.get("description") or "").strip()[:1500] or default_desc

        cog = bot.get_cog("CommunityCog")
        if cog is None:
            return _json_error("The verification module isn't loaded on the bot.", 503)
        embed = discord.Embed(title=title, description=desc, color=C.BRAND)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        try:
            msg = await channel.send(embed=embed, view=community.VerifyView(cog))
        except discord.Forbidden:
            return _json_error("Discord refused — check my permissions in that channel.", 403)
        except discord.HTTPException as e:
            return _json_error(f"Discord error: {e.text or e}", 502)
        return web.json_response({"success": True, "message_url": msg.jump_url})

    app.add_routes([
        web.get("/api/guilds/{guild_id}/protection", protection_get),
        web.post("/api/guilds/{guild_id}/protection", protection_post),
        web.get("/api/guilds/{guild_id}/anti-hacked", antihacked_get),
        web.post("/api/guilds/{guild_id}/anti-hacked", antihacked_post),
        web.get("/api/guilds/{guild_id}/verification", verification_get),
        web.post("/api/guilds/{guild_id}/verification", verification_post),
        web.post("/api/guilds/{guild_id}/verification/panel", verification_panel),
    ])
