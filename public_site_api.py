"""
public_site_api.py — public endpoints for the marketing website.

    GET  /api/public/stats      servers / members / commands / latency / uptime
    GET  /api/public/commands   live slash-command list (from the running bot)
    GET  /api/public/config     support-server invite + docs link
    POST /api/support/tickets   website support ticket  ->  posted to a Discord channel

Wire-up (already added to dashboard_api.py's cog_load):

    from public_site_api import register_public_routes
    register_public_routes(app, _get_session)

Environment variables (Pterodactyl -> Startup tab):
    SUPPORT_TICKET_CHANNEL_ID   REQUIRED  channel (text or forum) where tickets are posted
    SUPPORT_PING_ROLE_ID        optional  role pinged on every new ticket
    SUPPORT_SERVER_URL          optional  invite link of your support server
    DOCS_URL                    optional  external docs link
    SUPPORT_TICKET_PREFIX       optional  ticket id prefix (default: first letters of BOT_NAME)
"""
import json
import math
import os
import re
import secrets
import time
from collections import defaultdict, deque

import discord
from aiohttp import web
from discord import app_commands

try:
    from bot_config import BOT_NAME
except Exception:  # pragma: no cover
    BOT_NAME = "Support"

STARTED_AT = time.time()
TICKETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "support_tickets.jsonl")

CATEGORIES = {
    "setup": ("🛠️ Setup help", 0x5865F2),
    "bug": ("🐞 Bug report", 0xED4245),
    "feature": ("💡 Feature request", 0x57F287),
    "account": ("👤 Dashboard / login", 0xFEE75C),
    "other": ("💬 Other", 0x99AAB5),
}

HIDDEN_COMMANDS = {"clearcache"}          # owner-only commands are not shown publicly
MAX_PER_HOUR = 3                          # tickets per IP / user per hour
MIN_GAP_SECONDS = 20                      # min seconds between two tickets

_rate = defaultdict(deque)
_cmd_cache = {"t": 0.0, "data": []}


# ───────────────────────────── helpers ─────────────────────────────
def _prefix() -> str:
    env = (os.getenv("SUPPORT_TICKET_PREFIX") or "").strip()
    if env:
        return re.sub(r"[^A-Za-z0-9]", "", env).upper()[:6] or "SUP"
    letters = re.sub(r"[^A-Za-z0-9]", "", str(BOT_NAME)).upper()[:3]
    return letters or "SUP"


def _clean(value, limit: int) -> str:
    """Trim, drop control characters, cap blank lines, neutralise @mentions."""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace("@", "@\u200b")
    return text[:limit]


def _client_ip(request: web.Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote or "unknown"


def _rate_limited(key: str) -> str:
    """Return an error message if `key` is over the limit, else '' (and record the hit)."""
    now = time.time()
    hits = _rate[key]
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if hits and now - hits[-1] < MIN_GAP_SECONDS:
        return "Please wait a few seconds before sending another ticket."
    if len(hits) >= MAX_PER_HOUR:
        return "You have sent several tickets recently. Please wait a while before sending another."
    hits.append(now)
    return ""


def _pretty_cog(name: str) -> str:
    name = re.sub(r"Cog$", "", name or "")
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).replace("_", " ").strip()
    return name.title() if name else "General"


def _collect_commands(bot) -> list:
    now = time.time()
    if _cmd_cache["data"] and now - _cmd_cache["t"] < 60:
        return _cmd_cache["data"]
    out = []
    try:
        for cmd in bot.tree.walk_commands():
            if isinstance(cmd, app_commands.Group):
                continue
            name = cmd.qualified_name
            if name.split(" ")[0] in HIDDEN_COMMANDS:
                continue
            binding = getattr(cmd, "binding", None)
            category = _pretty_cog(getattr(binding, "qualified_name", None) or type(binding).__name__
                                   if binding is not None else
                                   (cmd.root_parent.name if getattr(cmd, "root_parent", None) else "General"))
            out.append({
                "name": name,
                "description": (cmd.description or "").strip()[:140],
                "category": category,
            })
    except Exception as e:  # never break the site because of the command list
        print(f"[PublicSite] Failed to collect commands: {e}")
    out.sort(key=lambda c: (c["category"], c["name"]))
    _cmd_cache["t"] = now
    _cmd_cache["data"] = out
    return out


async def _resolve_ticket_channel(bot):
    raw = (os.getenv("SUPPORT_TICKET_CHANNEL_ID") or "").strip()
    if not raw.isdigit():
        print("[PublicSite] SUPPORT_TICKET_CHANNEL_ID is not set (or not numeric) — tickets will 503.")
        return None
    cid = int(raw)
    ch = bot.get_channel(cid)
    if ch is None:
        try:
            ch = await bot.fetch_channel(cid)
        except Exception as e:
            # Distinguish "wrong ID" / "bot not in that server" / "no permission"
            # from "not configured" so this doesn't have to be guessed from a 503 alone.
            print(f"[PublicSite] Could not resolve SUPPORT_TICKET_CHANNEL_ID={cid}: {e!r}")
            return None
    return ch


def _log_ticket(record: dict) -> None:
    try:
        with open(TICKETS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[PublicSite] Could not write ticket log: {e}")


def _err(message: str, status: int = 400):
    return web.json_response({"error": message}, status=status)


# ───────────────────────────── handlers ─────────────────────────────
async def handle_public_stats(request: web.Request):
    bot = request.app["bot"]
    guilds = list(bot.guilds)
    latency = bot.latency
    return web.json_response({
        "online": bool(bot.is_ready()),
        "servers": len(guilds),
        "members": sum((g.member_count or 0) for g in guilds),
        "commands": len(_collect_commands(bot)),
        "latency_ms": int(latency * 1000) if isinstance(latency, (int, float)) and math.isfinite(latency) else None,
        "uptime_seconds": int(time.time() - STARTED_AT),
    })


async def handle_public_commands(request: web.Request):
    return web.json_response({"commands": _collect_commands(request.app["bot"])})


async def handle_public_config(request: web.Request):
    return web.json_response({
        "support_invite": (os.getenv("SUPPORT_SERVER_URL") or "").strip(),
        "docs_url": (os.getenv("DOCS_URL") or "").strip(),
        "tickets_enabled": (os.getenv("SUPPORT_TICKET_CHANNEL_ID") or "").strip().isdigit(),
        "categories": [{"id": k, "label": v[0]} for k, v in CATEGORIES.items()],
    })


def make_ticket_handler(get_session):
    async def handle_ticket_create(request: web.Request):
        bot = request.app["bot"]
        try:
            data = await request.json()
        except Exception:
            return _err("Invalid request.")
        if not isinstance(data, dict):
            return _err("Invalid request.")

        # Honeypot: real people never fill this hidden field
        if str(data.get("website", "")).strip():
            return web.json_response({"success": True, "ticket_id": f"{_prefix()}-000000"})

        category = data.get("category") if data.get("category") in CATEGORIES else "other"
        subject = _clean(data.get("subject"), 100)
        message = _clean(data.get("message"), 1500)
        name = _clean(data.get("name"), 60)
        contact = _clean(data.get("contact"), 100)
        guild_id = re.sub(r"\D", "", str(data.get("guild_id") or ""))[:20]

        sess = get_session(request)
        if len(subject) < 4:
            return _err("Please add a short subject (at least 4 characters).")
        if len(message) < 15:
            return _err("Please describe the problem in a bit more detail (at least 15 characters).")
        if not sess and not name:
            return _err("Please tell us your Discord username or name.")

        who_key = f"user:{sess['user_id']}" if sess and sess.get("user_id") else f"ip:{_client_ip(request)}"
        limited = _rate_limited(who_key)
        if limited:
            return _err(limited, 429)

        channel = await _resolve_ticket_channel(bot)
        if channel is None:
            return _err("Tickets are not set up yet. Please join our support server instead.", 503)

        label, color = CATEGORIES[category]
        ticket_id = f"{_prefix()}-{secrets.token_hex(3).upper()}"

        embed = discord.Embed(
            title=f"🎫 {label}",
            description=message,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Subject", value=subject, inline=False)
        if sess:
            uid = sess.get("user_id")
            embed.add_field(name="Discord user", value=f"<@{uid}> (`{uid}`)\n{_clean(sess.get('username'), 40)}", inline=True)
            if sess.get("avatar"):
                embed.set_author(
                    name=_clean(sess.get("username"), 40) or "Website user",
                    icon_url=f"https://cdn.discordapp.com/avatars/{uid}/{sess['avatar']}.png",
                )
        else:
            embed.add_field(name="Guest", value=name or "—", inline=True)
        if contact:
            embed.add_field(name="Contact", value=contact, inline=True)
        if guild_id:
            g = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
            embed.add_field(
                name="Server",
                value=f"{g.name} (`{guild_id}`)" if g else f"`{guild_id}` (bot not in this server)",
                inline=True,
            )
        embed.set_footer(text=f"Ticket {ticket_id} • via website")

        ping_role = (os.getenv("SUPPORT_PING_ROLE_ID") or "").strip()
        content, mentions = None, discord.AllowedMentions.none()
        if ping_role.isdigit():
            content = f"<@&{ping_role}> new website ticket `{ticket_id}`"
            mentions = discord.AllowedMentions(roles=[discord.Object(id=int(ping_role))])

        thread_name = f"{ticket_id} · {subject}"[:90]
        message_id = thread_id = None
        try:
            if isinstance(channel, discord.ForumChannel):
                created = await channel.create_thread(
                    name=thread_name, content=content, embed=embed, allowed_mentions=mentions,
                )
                thread_id = created.thread.id
                message_id = created.message.id
            else:
                sent = await channel.send(content=content, embed=embed, allowed_mentions=mentions)
                message_id = sent.id
                try:
                    thread = await sent.create_thread(name=thread_name, auto_archive_duration=1440)
                    thread_id = thread.id
                except Exception:
                    pass  # threads are a bonus; the ticket is already posted
        except discord.Forbidden:
            print("[PublicSite] Missing permissions in the support ticket channel")
            return _err("Could not deliver your ticket right now. Please join our support server.", 502)
        except Exception as e:
            print(f"[PublicSite] Failed to post ticket: {e!r}")
            return _err("Could not deliver your ticket right now. Please try again later.", 502)

        _log_ticket({
            "id": ticket_id,
            "ts": int(time.time()),
            "category": category,
            "subject": subject,
            "user_id": sess.get("user_id") if sess else None,
            "guest": name if not sess else None,
            "guild_id": guild_id or None,
            "message_id": message_id,
            "thread_id": thread_id,
        })
        print(f"[PublicSite] Ticket {ticket_id} posted ({category})")
        return web.json_response({"success": True, "ticket_id": ticket_id})

    return handle_ticket_create


def register_public_routes(app: web.Application, get_session) -> None:
    app.add_routes([
        web.get("/api/public/stats", handle_public_stats),
        web.get("/api/public/commands", handle_public_commands),
        web.get("/api/public/config", handle_public_config),
        web.post("/api/support/tickets", make_ticket_handler(get_session)),
    ])