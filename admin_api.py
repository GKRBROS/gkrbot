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

        actor_id = await get_user_id(request)
        print(f"[AdminPanel] Bot banner updated by user {actor_id}")
        try:
            from weblog import post_weblog
            await post_weblog("Bot Banner Changed", f"<@{actor_id}>", f"New image: {url}", color=0x5865F2)
        except Exception:
            pass
        return web.json_response({"success": True})

    return handle_banner


def make_status_message_handlers(get_user_id):
    async def handle_get_status_message(request: web.Request):
        from bot_status_msg import get_all_status_info
        return web.json_response(get_all_status_info())

    async def handle_post_status_message(request: web.Request):
        if not await _is_admin(request, get_user_id):
            return _err("Forbidden", 403)
        try:
            data = await request.json()
        except Exception:
            return _err("Invalid JSON.")

        from bot_status_msg import set_status_message, clear_status_message
        msg = str(data.get("message", "")).strip()
        active = bool(data.get("active", True))
        actor_id = await get_user_id(request)

        if not msg:
            res = clear_status_message()
        else:
            res = set_status_message(msg, author=f"WebAdmin({actor_id})", active=active)

        try:
            from weblog import post_weblog
            state_text = "Enabled" if active and msg else "Cleared/Disabled"
            await post_weblog("Bot Status Notice Updated", f"<@{actor_id}>", f"State: {state_text}\nMessage: {msg}", color=0xFEE75C)
        except Exception:
            pass

        return web.json_response({"success": True, "notice": res})

    return handle_get_status_message, handle_post_status_message


def make_send_announcement_handler(get_user_id):
    async def handle_send_announcement(request: web.Request):
        if not await _is_admin(request, get_user_id):
            return _err("Forbidden", 403)
        try:
            data = await request.json()
        except Exception:
            return _err("Invalid JSON.")

        guild_id = str((data or {}).get("guild_id", "")).strip()
        channel_id = str((data or {}).get("channel_id", "")).strip()
        title = str((data or {}).get("title", "")).strip()
        body = str((data or {}).get("body", "")).strip()
        color_hex = str((data or {}).get("color", "#8A2BE2")).strip().lstrip("#")
        ping = str((data or {}).get("ping", "none")).strip()
        sidebar_color = str((data or {}).get("sidebar_color", "")).strip().lstrip("#")

        if not channel_id or not body:
            return _err("channel_id and body are required.")

        try:
            color_int = int(color_hex or "8A2BE2", 16)
        except ValueError:
            color_int = 0x8A2BE2

        # sidebar_color overrides color if provided
        if sidebar_color:
            try:
                color_int = int(sidebar_color, 16)
            except ValueError:
                pass

        bot = request.app["bot"]
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            return _err("Channel not found or bot lacks access.")

        import datetime
        actor_id = await get_user_id(request)

        embed = discord.Embed(
            title=f"📢  {title}" if title else "📢 Announcement",
            description=body,
            color=color_int,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_footer(text="GKR Bot — Official Announcement")

        ping_text = None
        if ping == "everyone":
            ping_text = "@everyone"
        elif ping == "here":
            ping_text = "@here"

        try:
            await channel.send(content=ping_text, embed=embed)
        except discord.Forbidden:
            return _err("Bot lacks permission to send to that channel.")
        except discord.HTTPException as e:
            return _err(f"Discord error: {e}")

        print(f"[AdminPanel] Announcement sent to channel {channel_id} by user {actor_id}")
        try:
            from weblog import post_weblog
            await post_weblog(
                "Announcement Sent",
                f"<@{actor_id}>",
                f"Channel: <#{channel_id}>\nTitle: {title}\n{body[:200]}",
                color=color_int,
            )
        except Exception:
            pass

        return web.json_response({"success": True})
    return handle_send_announcement


def make_list_channels_handler(get_user_id):
    async def handle_list_channels(request: web.Request):
        if not await _is_admin(request, get_user_id):
            return _err("Forbidden", 403)
        bot = request.app["bot"]
        guilds = []
        for guild in bot.guilds:
            channels = [
                {"id": str(c.id), "name": c.name}
                for c in guild.text_channels
                if c.permissions_for(guild.me).send_messages
            ]
            guilds.append({"id": str(guild.id), "name": guild.name, "channels": channels})
        return web.json_response({"guilds": guilds})
    return handle_list_channels


def register_admin_routes(app: web.Application, get_user_id) -> None:
    get_status_msg, post_status_msg = make_status_message_handlers(get_user_id)
    app.add_routes([
        web.get("/api/admin/whoami", make_whoami_handler(get_user_id)),
        web.get("/api/admin/tickets", make_tickets_handler(get_user_id)),
        web.post("/api/admin/bot-banner", make_banner_handler(get_user_id)),
        web.get("/api/admin/status-message", get_status_msg),
        web.post("/api/admin/status-message", post_status_msg),
        web.get("/api/admin/channels", make_list_channels_handler(get_user_id)),
        web.post("/api/admin/send-announcement", make_send_announcement_handler(get_user_id)),
    ])
