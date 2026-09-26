"""
admin_api.py — owner-only endpoints for the dashboard's Admin Panel.

    GET  /api/admin/whoami        { is_admin: bool }
    GET  /api/admin/tickets       recent website support tickets (from support_tickets.jsonl)
    POST /api/admin/bot-banner    { url } -> downloads the image and sets the BOT'S banner

Wire-up (added to dashboard_api.py):

    from admin_api import register_admin_routes
    register_admin_routes(app, get_user_id)

Environment variable:
    ADMIN_USER_IDS   comma-separated Discord user IDs allowed into the admin panel,
                      in ADDITION to the bot application's own owner(s).
                      e.g. ADMIN_USER_IDS=111111111111111111,222222222222222222

IMPORTANT — banner scope: Discord bots only have ONE profile banner, shared across
every server they're in (there is no per-server bot banner in Discord's API today).
Setting it here changes how the bot looks everywhere, not just in one server, and
Discord allows a bot's banner to be changed roughly twice every 10 minutes.
"""
import json
import os
from pathlib import Path

import discord
from aiohttp import web

TICKETS_FILE = Path(__file__).resolve().parent / "support_tickets.jsonl"
MAX_BANNER_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _admin_ids(bot) -> set:
    ids = set()
    owner_id = getattr(bot, "owner_id", None)
    if owner_id:
        ids.add(int(owner_id))
    ids |= {int(i) for i in (getattr(bot, "owner_ids", None) or [])}
    for raw in (os.getenv("ADMIN_USER_IDS") or "").split(","):
        raw = raw.strip()
        if raw.isdigit():
            ids.add(int(raw))
    return ids


async def _is_admin(request: web.Request, get_user_id) -> bool:
    user_id = await get_user_id(request)
    if not user_id:
        return False
    bot = request.app["bot"]
    if not _admin_ids(bot):
        # Nothing configured yet: fall back to Discord's own application-owner check
        try:
            return await bot.is_owner(discord.Object(id=int(user_id)))
        except Exception:
            return False
    return int(user_id) in _admin_ids(bot)


def _err(message: str, status: int = 400):
    return web.json_response({"error": message}, status=status)


def make_whoami_handler(get_user_id):
    async def handle_whoami(request: web.Request):
        return web.json_response({"is_admin": await _is_admin(request, get_user_id)})
    return handle_whoami


def make_tickets_handler(get_user_id):
    async def handle_tickets(request: web.Request):
        if not await _is_admin(request, get_user_id):
            return _err("Forbidden", 403)
        rows = []
        if TICKETS_FILE.exists():
            try:
                lines = TICKETS_FILE.read_text(encoding="utf-8").splitlines()
                for line in lines[-100:]:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except OSError as e:
                return _err(f"Could not read ticket log: {e}", 500)
        rows.reverse()
        return web.json_response({"tickets": rows})
    return handle_tickets


def make_banner_handler(get_user_id):
    async def handle_banner(request: web.Request):
        if not await _is_admin(request, get_user_id):
            return _err("Forbidden", 403)

        try:
            data = await request.json()
        except Exception:
            return _err("Invalid request.")

        url = str((data or {}).get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return _err("Please provide a direct link to an image.")

        bot = request.app["bot"]
        try:
            import aiohttp
            headers = {"User-Agent": "Mozilla/5.0 (compatible; DashboardBannerFetch/1.0)"}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        return _err(f"Could not download that image (HTTP {resp.status}).")
                    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    if ctype not in ALLOWED_IMAGE_TYPES:
                        return _err("That URL is not a supported image (use PNG, JPG, GIF or WebP).")
                    image_bytes = await resp.content.read(MAX_BANNER_BYTES + 1)
                    if len(image_bytes) > MAX_BANNER_BYTES:
                        return _err("That image is too large (10 MB max).")
        except Exception as e:
            return _err(f"Failed to download the image: {e}", 502)

        try:
            await bot.user.edit(banner=image_bytes)
        except discord.HTTPException as e:
            # Common cases: not enough boost level / rate-limited by Discord / bad image
            return _err(f"Discord rejected the banner: {e.text or e}", 502)
        except Exception as e:
            return _err(f"Failed to set the banner: {e}", 500)

        print(f"[AdminPanel] Bot banner updated by user {await get_user_id(request)}")
        return web.json_response({"success": True})

    return handle_banner


def register_admin_routes(app: web.Application, get_user_id) -> None:
    app.add_routes([
        web.get("/api/admin/whoami", make_whoami_handler(get_user_id)),
        web.get("/api/admin/tickets", make_tickets_handler(get_user_id)),
        web.post("/api/admin/bot-banner", make_banner_handler(get_user_id)),
    ])
