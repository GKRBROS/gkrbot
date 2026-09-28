"""
blacklist_api.py — dashboard endpoints for the blacklist system.

Every route here is gated by the SAME `_is_admin` check used by admin_api.py
(bot owner + ADMIN_USER_IDS) — there is only one "who is bot staff" identity
in this project. A normal dashboard user, or a normal server Administrator
who isn't on that list, gets 403 from every one of these endpoints even if
they guess the URL directly (server-side enforcement, not just a hidden UI).

    GET    /api/blacklist/servers                 list blacklisted servers
    POST   /api/blacklist/servers                  { guild_id, reason }
    DELETE /api/blacklist/servers/{guild_id}
    POST   /api/blacklist/servers/{guild_id}/leave { reason }  (blacklist + leave)

    GET    /api/blacklist/members                  list blacklisted members
    POST   /api/blacklist/members                  { user_id, reason }
    DELETE /api/blacklist/members/{user_id}

Wire-up (added to dashboard_api.py's cog_load, alongside the other route
registrations):

    from blacklist_api import register_blacklist_routes
    register_blacklist_routes(app, get_user_id)
"""
import re

from aiohttp import web

MAX_REASON_LEN = 300


def _clean_reason(value) -> str:
    if not value:
        return ""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value)).strip()
    return text[:MAX_REASON_LEN]


def _err(message: str, status: int = 400):
    return web.json_response({"error": message}, status=status)


def _row(r) -> dict:
    return {k: r[k] for k in r.keys()}


def register_blacklist_routes(app: web.Application, get_user_id) -> None:
    from admin_api import _is_admin
    from blacklist import STORE, _log_action, is_bot_staff_id  # noqa: F401 (import validates module wiring early)

    async def require_admin(request: web.Request):
        if not await _is_admin(request, get_user_id):
            return None
        return await get_user_id(request)

    # ── servers ──────────────────────────────────────────────────────
    async def list_servers(request: web.Request):
        admin_id = await require_admin(request)
        if admin_id is None:
            return _err("Forbidden", 403)
        bot = request.app["bot"]
        rows = [_row(r) for r in STORE.list_servers()]
        for r in rows:
            guild = bot.get_guild(r["guild_id"])
            r["guild_name"] = guild.name if guild else (r.get("guild_name") or "")
            r["bot_present"] = guild is not None
        return web.json_response({"servers": rows})

    async def add_server(request: web.Request):
        admin_id = await require_admin(request)
        if admin_id is None:
            return _err("Forbidden", 403)
        try:
            data = await request.json()
        except Exception:
            return _err("Invalid request.")
        guild_id = str((data or {}).get("guild_id") or "").strip()
        if not guild_id.isdigit():
            return _err("guild_id must be a numeric Discord server ID.")
        bot = request.app["bot"]
        gid = int(guild_id)
        guild = bot.get_guild(gid)
        STORE.add_server(gid, guild.name if guild else "", _clean_reason((data or {}).get("reason")), admin_id)
        return web.json_response({"success": True})

    async def remove_server(request: web.Request):
        admin_id = await require_admin(request)
        if admin_id is None:
            return _err("Forbidden", 403)
        guild_id = request.match_info.get("guild_id", "")
        if not guild_id.isdigit():
            return _err("Invalid guild id.")
        ok = STORE.remove_server(int(guild_id), admin_id)
        if not ok:
            return _err("That server isn't blacklisted.", 404)
        return web.json_response({"success": True})

    async def leave_server(request: web.Request):
        admin_id = await require_admin(request)
        if admin_id is None:
            return _err("Forbidden", 403)
        guild_id = request.match_info.get("guild_id", "")
        if not guild_id.isdigit():
            return _err("Invalid guild id.")
        try:
            data = await request.json()
        except Exception:
            data = {}
        gid = int(guild_id)
        bot = request.app["bot"]
        guild = bot.get_guild(gid)
        STORE.add_server(gid, guild.name if guild else "", _clean_reason((data or {}).get("reason")), admin_id)
        left = False
        if guild:
            try:
                await guild.leave()
                left = True
            except Exception as e:
                print(f"[BlacklistAPI] Failed to leave guild {gid}: {e}")
        return web.json_response({"success": True, "left": left})

    # ── members ──────────────────────────────────────────────────────
    async def list_members(request: web.Request):
        admin_id = await require_admin(request)
        if admin_id is None:
            return _err("Forbidden", 403)
        return web.json_response({"members": [_row(r) for r in STORE.list_members()]})

    async def add_member(request: web.Request):
        admin_id = await require_admin(request)
        if admin_id is None:
            return _err("Forbidden", 403)
        try:
            data = await request.json()
        except Exception:
            return _err("Invalid request.")
        user_id = str((data or {}).get("user_id") or "").strip()
        if not user_id.isdigit():
            return _err("user_id must be a numeric Discord user ID.")
        bot = request.app["bot"]
        uid = int(user_id)
        user = bot.get_user(uid)
        STORE.add_member(uid, str(user) if user else "", _clean_reason((data or {}).get("reason")), admin_id)
        return web.json_response({"success": True})

    async def remove_member(request: web.Request):
        admin_id = await require_admin(request)
        if admin_id is None:
            return _err("Forbidden", 403)
        user_id = request.match_info.get("user_id", "")
        if not user_id.isdigit():
            return _err("Invalid user id.")
        ok = STORE.remove_member(int(user_id), admin_id)
        if not ok:
            return _err("That user isn't blacklisted.", 404)
        return web.json_response({"success": True})

    app.add_routes([
        web.get("/api/blacklist/servers", list_servers),
        web.post("/api/blacklist/servers", add_server),
        web.delete("/api/blacklist/servers/{guild_id}", remove_server),
        web.post("/api/blacklist/servers/{guild_id}/leave", leave_server),
        web.get("/api/blacklist/members", list_members),
        web.post("/api/blacklist/members", add_member),
        web.delete("/api/blacklist/members/{user_id}", remove_member),
    ])
