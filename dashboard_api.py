import os
import json
import uuid
import sqlite3
import aiohttp
from aiohttp import web
from discord.ext import commands
import discord
from gkr_ui import embed_success, embed_error, embed_info, C
from bot_config import BOT_NAME

import urllib.parse

# Load credentials from environment (DISCORD_CLIENT_ID / CLIENT_ID / APPLICATION_ID)
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID") or os.getenv("APPLICATION_ID") or os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5173/auth/callback")

def _resolve_client_id(bot: commands.Bot = None) -> str:
    """Gets client ID from environment or active bot instance."""
    cid = os.getenv("DISCORD_CLIENT_ID") or os.getenv("APPLICATION_ID") or os.getenv("CLIENT_ID")
    if cid:
        return str(cid).strip()
    if bot and bot.user:
        return str(bot.user.id)
    return ""

def _resolve_client_secret() -> str:
    return (os.getenv("DISCORD_CLIENT_SECRET") or os.getenv("CLIENT_SECRET") or "").strip()

# Session store: token -> dict of user data
SESSIONS = {}
SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "dashboard_sessions.json")

def _load_sessions():
    """Restore dashboard sessions from disk so logins survive bot restarts."""
    global SESSIONS
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                SESSIONS = json.load(f)
            print(f"[DashboardAPI] Restored {len(SESSIONS)} dashboard session(s) from disk")
    except Exception as e:
        print(f"[DashboardAPI] Failed to load sessions: {e}")

def _save_sessions():
    """Persist dashboard sessions to disk (atomic write)."""
    try:
        tmp = SESSIONS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(SESSIONS, f)
        os.replace(tmp, SESSIONS_FILE)
    except Exception as e:
        print(f"[DashboardAPI] Failed to save sessions: {e}")

# CORS Middleware to allow requests from Vite dev server or separate origins
@web.middleware
async def cors_middleware(request: web.Request, handler):
    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        response = web.Response(status=204)
        response.headers['Access-Control-Allow-Origin'] = request.headers.get("Origin", "*")
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    try:
        response = await handler(request)
    except web.HTTPException as ex:
        response = ex

    response.headers['Access-Control-Allow-Origin'] = request.headers.get("Origin", "*")
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

async def handle_login(request: web.Request):
    """Redirects to Discord OAuth2 with dynamic redirect_uri."""
    bot: commands.Bot = request.app.get("bot")
    client_id = _resolve_client_id(bot)
    
    if not client_id:
        return web.json_response({
            "error": "Missing DISCORD_CLIENT_ID. Please set DISCORD_CLIENT_ID in your .env file."
        }, status=500)

    # Dynamic redirect URI from query param or fallback
    redirect_uri = request.query.get("redirect_uri") or os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5173/auth/callback")
    
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
        "prompt": "consent"
    }
    oauth_url = f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"
    return web.json_response({"url": oauth_url})

async def handle_callback_redirect(request: web.Request):
    # If the user's discord redirect_uri accidentally includes /api/, redirect them to the React frontend route
    params = request.query_string
    return web.HTTPFound(f"/auth/callback?{params}")

async def handle_callback(request: web.Request):
    """Exchanges code for access token and generates a session."""
    data = await request.json()
    code = data.get("code")
    if not code:
        return web.json_response({"error": "No code provided"}, status=400)

    bot: commands.Bot = request.app.get("bot")
    client_id = _resolve_client_id(bot)
    client_secret = _resolve_client_secret()
    
    if not client_id or not client_secret:
        return web.json_response({
            "error": "Missing DISCORD_CLIENT_ID or DISCORD_CLIENT_SECRET in .env"
        }, status=500)

    # Must exactly match the redirect_uri used during the authorization request
    redirect_uri = data.get("redirect_uri") or os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5173/auth/callback")
    
    # Exchange code for token
    token_url = "https://discord.com/api/oauth2/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=payload, headers=headers) as resp:
            if resp.status != 200:
                resp_text = await resp.text()
                print(f"[Dashboard API] Token exchange failed ({resp.status}): {resp_text}")
                try:
                    err_data = json.loads(resp_text)
                    err_msg = err_data.get("error_description", err_data.get("error", "Failed to exchange code"))
                except Exception:
                    err_msg = f"Discord rejected authorization code (HTTP {resp.status})"
                return web.json_response({"error": err_msg}, status=400)
            token_data = await resp.json()
    
    access_token = token_data.get("access_token")
    if not access_token:
        return web.json_response({"error": "No access token received from Discord"}, status=400)
    
    # Get user profile
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get("https://discord.com/api/users/@me", headers=headers) as resp:
            if resp.status != 200:
                return web.json_response({"error": "Failed to fetch Discord user profile"}, status=400)
            user_data = await resp.json()

    # Generate session token
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "user_id": user_data.get("id"),
        "username": user_data.get("username"),
        "avatar": user_data.get("avatar"),
        "access_token": access_token
    }
    _save_sessions()

    return web.json_response({"token": session_id, "user": SESSIONS[session_id]})

def _get_session(request: web.Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    return SESSIONS.get(token)

async def handle_me(request: web.Request):
    """Returns the current user and their mutual guilds where they have admin access."""
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    # Fetch user's guilds from Discord API
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {session_data['access_token']}"}
        async with session.get("https://discord.com/api/users/@me/guilds", headers=headers) as resp:
            if resp.status == 401:
                # Discord token expired - kill the session so the UI re-authenticates
                token = request.headers.get("Authorization", "").split(" ")[-1]
                SESSIONS.pop(token, None)
                _save_sessions()
                return web.json_response({"error": "Session expired, please log in again"}, status=401)
            if resp.status != 200:
                return web.json_response({"error": "Failed to fetch guilds"}, status=400)
            user_guilds = await resp.json()
    
    bot: commands.Bot = request.app["bot"]
    bot_guild_ids = {g.id for g in bot.guilds}
    
    # Filter to guilds where bot is present AND user has Administrator (0x8) permission
    mutual_admin_guilds = []
    for g in user_guilds:
        if int(g["id"]) in bot_guild_ids:
            # Check for Admin permission (bit 3)
            perms = int(g.get("permissions", "0"))
            is_admin = (perms & 0x8) == 0x8
            is_owner = g.get("owner", False)
            if is_admin or is_owner:
                mutual_admin_guilds.append({
                    "id": g["id"],
                    "name": g["name"],
                    "icon": f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png" if g.get("icon") else None
                })

    return web.json_response({
        "user": {
            "id": session_data["user_id"],
            "username": session_data["username"],
            "avatar": f"https://cdn.discordapp.com/avatars/{session_data['user_id']}/{session_data['avatar']}.png" if session_data["avatar"] else None,
        },
        "bot_name": BOT_NAME,
        "bot_client_id": _resolve_client_id(bot),
        "guilds": mutual_admin_guilds
    })

async def handle_bot_info(request: web.Request):
    """Public endpoint providing non-sensitive bot metadata including BOT_NAME."""
    bot = request.app.get("bot")
    return web.json_response({
        "bot_name": BOT_NAME,
        "bot_client_id": _resolve_client_id(bot),
        "version": "3.0"
    })

# --- Auto-Sync Engine: replicate dashboard edits to ALL other servers ---

def _auto_sync_requested(data, request=None):
    """True when the dashboard asks for an edit to be replicated to all other servers."""
    if isinstance(data, dict) and data.get("sync_all"):
        return True
    if request is not None and request.query.get("sync_all") in ("1", "true"):
        return True
    return False

def _target_guilds(bot, source_guild_id):
    """Every server the bot is in, except the source server."""
    return [g for g in bot.guilds if g.id != int(source_guild_id)]

def _match_channel(source_guild, target_guild, channel_id):
    """Find the channel on target_guild matching the source channel by name."""
    if not source_guild or not target_guild or channel_id in (None, ""):
        return None
    try:
        src_ch = source_guild.get_channel(int(channel_id))
    except (ValueError, TypeError):
        return None
    if not src_ch:
        return None
    return discord.utils.get(target_guild.text_channels, name=src_ch.name)

def _replicate_welcome(bot, source_guild_id):
    try:
        from welcome import WelcomeDatabase
        w_db = WelcomeDatabase()
        src_cfg = w_db.get_config(int(source_guild_id))
        if not src_cfg:
            return 0
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            try:
                tgt_cfg = w_db.get_config(g.id)
                tgt_cfg.enabled = src_cfg.enabled
                tgt_cfg.welcome_message = src_cfg.welcome_message
                tgt_cfg.leave_enabled = src_cfg.leave_enabled
                tgt_cfg.leave_message = src_cfg.leave_message
                tgt_cfg.leave_image_url = src_cfg.leave_image_url
                w_db.save_config(tgt_cfg)
                count += 1
            except Exception as e:
                print(f"[AutoSync] welcome -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] welcome failed: {e}")
        return 0

def _replicate_security(bot, source_guild_id):
    try:
        import security
        s_db = security.SecurityDatabase()
        s_db.initialize()
        count = 0
        with s_db._conn() as conn:
            s_row = conn.execute("SELECT * FROM security_config WHERE guild_id = ?", (str(source_guild_id),)).fetchone()
            if not s_row:
                return 0
            for g in _target_guilds(bot, source_guild_id):
                try:
                    t_row = conn.execute("SELECT log_channel_id FROM security_config WHERE guild_id = ?", (str(g.id),)).fetchone()
                    conn.execute("""
                        INSERT OR REPLACE INTO security_config
                        (guild_id, anti_spam_enabled, spam_msg_limit, spam_time_sec, mass_mention_limit, log_channel_id, image_scan_enabled)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(g.id), s_row["anti_spam_enabled"], s_row["spam_msg_limit"],
                        s_row["spam_time_sec"], s_row["mass_mention_limit"],
                        t_row["log_channel_id"] if t_row else None,
                        s_row["image_scan_enabled"],
                    ))
                    count += 1
                except Exception as e:
                    print(f"[AutoSync] security -> {g.name}: {e}")
            conn.commit()
        return count
    except Exception as e:
        print(f"[AutoSync] security failed: {e}")
        return 0

def _replicate_sticky_set(bot, source_guild_id, channel_id, content):
    try:
        import sticky_messages
        db = sticky_messages.StickyDB()
        src_guild = bot.get_guild(int(source_guild_id))
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            ch = _match_channel(src_guild, g, channel_id)
            if ch:
                try:
                    db.set_sticky(ch.id, g.id, content)
                    count += 1
                except Exception as e:
                    print(f"[AutoSync] sticky -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] sticky failed: {e}")
        return 0

def _replicate_sticky_remove(bot, source_guild_id, channel_id):
    try:
        import sticky_messages
        db = sticky_messages.StickyDB()
        src_guild = bot.get_guild(int(source_guild_id))
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            ch = _match_channel(src_guild, g, channel_id)
            if ch:
                try:
                    db.remove_sticky(ch.id)
                    count += 1
                except Exception as e:
                    print(f"[AutoSync] sticky remove -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] sticky remove failed: {e}")
        return 0

def _replicate_autoreact_add(bot, source_guild_id, channel_id, emoji):
    try:
        import auto_reactions
        db = auto_reactions.AutoReactDB()
        src_guild = bot.get_guild(int(source_guild_id))
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            ch = _match_channel(src_guild, g, channel_id)
            if ch:
                try:
                    if db.add_reaction(g.id, ch.id, emoji):
                        count += 1
                except Exception as e:
                    print(f"[AutoSync] autoreact -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] autoreact failed: {e}")
        return 0

def _replicate_autoreact_remove(bot, source_guild_id, channel_id):
    try:
        import auto_reactions
        db = auto_reactions.AutoReactDB()
        src_guild = bot.get_guild(int(source_guild_id))
        count = 0
        with db._conn() as conn:
            for g in _target_guilds(bot, source_guild_id):
                ch = _match_channel(src_guild, g, channel_id)
                if ch:
                    cur = conn.execute(
                        "DELETE FROM auto_reactions WHERE guild_id = ? AND channel_id = ?",
                        (str(g.id), str(ch.id)),
                    )
                    count += cur.rowcount
            conn.commit()
        return count
    except Exception as e:
        print(f"[AutoSync] autoreact remove failed: {e}")
        return 0

def _replicate_staff_role_add(bot, source_guild_id, role_id):
    try:
        import moderation
        db = moderation.ModerationDatabase()
        db.initialize()
        src_guild = bot.get_guild(int(source_guild_id))
        src_role = src_guild.get_role(int(role_id)) if src_guild else None
        if not src_role:
            return 0
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            tgt_role = discord.utils.get(g.roles, name=src_role.name)
            if tgt_role:
                try:
                    if db.add_staff_role(g.id, tgt_role.id):
                        count += 1
                except Exception as e:
                    print(f"[AutoSync] staff role -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] staff role add failed: {e}")
        return 0

def _replicate_staff_role_remove(bot, source_guild_id, role_id):
    try:
        import moderation
        db = moderation.ModerationDatabase()
        db.initialize()
        src_guild = bot.get_guild(int(source_guild_id))
        src_role = src_guild.get_role(int(role_id)) if src_guild else None
        if not src_role:
            return 0
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            tgt_role = discord.utils.get(g.roles, name=src_role.name)
            if tgt_role:
                try:
                    if db.remove_staff_role(g.id, tgt_role.id):
                        count += 1
                except Exception as e:
                    print(f"[AutoSync] staff role remove -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] staff role remove failed: {e}")
        return 0

def _replicate_tickets_log_channel(bot, source_guild_id, channel_id):
    try:
        cog = bot.get_cog("TicketsCog")
        if not cog:
            return 0
        src_guild = bot.get_guild(int(source_guild_id))
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            ch = _match_channel(src_guild, g, channel_id) if channel_id else None
            try:
                cog.db.set_log_channel(g.id, ch.id if ch else None)
                count += 1
            except Exception as e:
                print(f"[AutoSync] tickets log -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] tickets log failed: {e}")
        return 0

def _replicate_ticket_category_upsert(bot, source_guild_id, name, fields):
    """Create or update a ticket category (matched by name) on every other server."""
    try:
        cog = bot.get_cog("TicketsCog")
        if not cog or not name:
            return 0
        # Role IDs are guild-specific, so never copy them to other servers
        safe_fields = dict(fields)
        safe_fields["ping_roles"] = ""
        safe_fields["admin_roles"] = ""
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            try:
                existing = next((c for c in cog.db.get_categories(g.id) if c.name == name), None)
                if existing:
                    cog.db.update_category(g.id, existing.id, **safe_fields)
                else:
                    cog.db.add_category(
                        guild_id=g.id, name=name,
                        button_label=safe_fields.get("button_label", name),
                        button_emoji=safe_fields.get("button_emoji", "\U0001F3AB"),
                        ping_roles="", admin_roles="",
                        embed_title=safe_fields.get("embed_title", "New Ticket"),
                        embed_desc=safe_fields.get("embed_description", ""),
                    )
                count += 1
            except Exception as e:
                print(f"[AutoSync] ticket category -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] ticket category failed: {e}")
        return 0

def _replicate_ticket_category_delete(bot, source_guild_id, name):
    try:
        cog = bot.get_cog("TicketsCog")
        if not cog or not name:
            return 0
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            try:
                existing = next((c for c in cog.db.get_categories(g.id) if c.name == name), None)
                if existing and cog.db.delete_category(g.id, existing.id):
                    count += 1
            except Exception as e:
                print(f"[AutoSync] ticket category delete -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] ticket category delete failed: {e}")
        return 0

def _replicate_stream_alert_add(bot, source_guild_id, platform, username, creator_id, channel_id):
    try:
        import stream_alerts
        db = stream_alerts.StreamAlertsDatabase()
        db.initialize()
        src_guild = bot.get_guild(int(source_guild_id))
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            ch = _match_channel(src_guild, g, channel_id)
            if ch:
                try:
                    if db.add_alert(guild_id=g.id, platform=platform, creator_username=username,
                                    creator_id=creator_id, notification_channel_id=ch.id):
                        count += 1
                except Exception as e:
                    print(f"[AutoSync] stream alert -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] stream alert add failed: {e}")
        return 0

def _replicate_stream_alert_update(bot, source_guild_id, platform, username, channel_id,
                                   notify_live, notify_videos, live_msg, video_msg):
    try:
        import stream_alerts
        db = stream_alerts.StreamAlertsDatabase()
        db.initialize()
        src_guild = bot.get_guild(int(source_guild_id))
        count = 0
        with db._conn() as conn:
            for g in _target_guilds(bot, source_guild_id):
                ch = _match_channel(src_guild, g, channel_id)
                if not ch:
                    continue
                row = conn.execute(
                    "SELECT id FROM stream_alerts WHERE guild_id = ? AND platform = ? AND creator_username = ?",
                    (str(g.id), platform, username.lower()),
                ).fetchone()
                if not row:
                    continue
                conn.execute(
                    """UPDATE stream_alerts SET notification_channel_id = ?, notify_live = ?,
                       notify_videos = ?, custom_live_message = ?, custom_video_message = ? WHERE id = ?""",
                    (str(ch.id), 1 if notify_live else 0, 1 if notify_videos else 0,
                     live_msg, video_msg, row["id"]),
                )
                count += 1
            conn.commit()
        return count
    except Exception as e:
        print(f"[AutoSync] stream alert update failed: {e}")
        return 0

def _replicate_stream_alert_remove(bot, source_guild_id, platform, username):
    try:
        import stream_alerts
        db = stream_alerts.StreamAlertsDatabase()
        count = 0
        for g in _target_guilds(bot, source_guild_id):
            try:
                if db.remove_alert(g.id, platform, username.lower()):
                    count += 1
            except Exception as e:
                print(f"[AutoSync] stream alert remove -> {g.name}: {e}")
        return count
    except Exception as e:
        print(f"[AutoSync] stream alert remove failed: {e}")
        return 0

# --- Feature Specific Endpoints ---

async def handle_stream_alerts_get(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = request.match_info["guild_id"]
    
    bot: commands.Bot = request.app["bot"]
    stream_cog = bot.get_cog("StreamAlertsCog")
    if not stream_cog:
        return web.json_response({"error": "Stream Alerts module not loaded"}, status=500)
    
    alerts = stream_cog.db.get_alerts_for_guild(int(guild_id))
    alerts_data = []
    for a in alerts:
        alerts_data.append({
            "id": a.id,
            "platform": a.platform,
            "creator_username": a.creator_username,
            "notification_channel_id": str(a.notification_channel_id),
            "custom_live_message": a.custom_live_message,
            "custom_video_message": a.custom_video_message,
            "notify_live": a.notify_live,
            "notify_videos": a.notify_videos,
        })
    return web.json_response({"alerts": alerts_data})

async def handle_stream_alerts_post(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    platform = data.get("platform")
    username = data.get("creator_username", "").strip()
    channel_id = data.get("notification_channel_id")
    
    if not platform or not username or not channel_id:
        return web.json_response({"error": "Missing fields"}, status=400)
    
    bot: commands.Bot = request.app["bot"]
    stream_cog = bot.get_cog("StreamAlertsCog")
    if not stream_cog:
        return web.json_response({"error": "Stream Alerts module not loaded"}, status=500)
    
    # Import resolvers dynamically to avoid circular import if any
    import stream_alerts
    
    if platform == "youtube":
        if not stream_alerts.YOUTUBE_API_KEY:
            return web.json_response({"error": "YouTube API key not configured on the bot."}, status=400)
        creator_id = await stream_alerts.resolve_youtube_channel_id(stream_cog.session, username)
        if not creator_id:
            return web.json_response({"error": f"Could not find YouTube channel for {username}"}, status=404)
    elif platform == "twitch":
        if not stream_alerts.TWITCH_CLIENT_ID:
            return web.json_response({"error": "Twitch credentials not configured on the bot."}, status=400)
        creator_id = await stream_alerts.resolve_twitch_user_id(stream_cog.session, username)
        if not creator_id:
            return web.json_response({"error": f"Could not find Twitch user {username}"}, status=404)
    elif platform == "kick":
        creator_id = username.lower()
    else:
        return web.json_response({"error": "Invalid platform"}, status=400)
    
    try:
        stream_cog.db.add_alert(
            guild_id=guild_id,
            platform=platform,
            creator_username=username, # store the username for display
            creator_id=creator_id,
            notification_channel_id=int(channel_id),
        )
        if platform == "youtube" and hasattr(stream_cog, "yt_notifier") and stream_cog.yt_notifier is not None:
            try:
                import asyncio
                asyncio.create_task(stream_cog.yt_notifier.subscribe([creator_id]))
                print(f"[DashboardAPI] ytnoti subscribe task created for {creator_id}")
            except Exception as e:
                print(f"[DashboardAPI] Failed to subscribe ytnoti: {e}")
                
        if _auto_sync_requested(data, request):
            synced = _replicate_stream_alert_add(bot, guild_id, platform, username.lower(), creator_id, int(channel_id))
            print(f"[AutoSync] Stream alert replicated to {synced} other server(s)")

        return web.json_response({"success": True})
    except sqlite3.IntegrityError:
        return web.json_response({"error": "Alert already exists for this creator on this platform."}, status=400)

async def handle_stream_alerts_delete(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = int(request.match_info["guild_id"])
    platform = request.match_info["platform"]
    username = request.match_info["username"]
    
    bot: commands.Bot = request.app["bot"]
    stream_cog = bot.get_cog("StreamAlertsCog")
    if not stream_cog:
        return web.json_response({"error": "Stream Alerts module not loaded"}, status=500)
    
    deleted = stream_cog.db.remove_alert(guild_id, platform, username)
    if deleted:
        if _auto_sync_requested(None, request):
            _replicate_stream_alert_remove(bot, guild_id, platform, username.lower())
        return web.json_response({"success": True})
    return web.json_response({"error": "Alert not found"}, status=404)

async def handle_stream_alerts_put(request: web.Request):
    """Edit an existing stream alert (notification channel, notify toggles, custom messages)."""
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    platform = request.match_info["platform"]
    username = request.match_info["username"].lower()
    data = await request.json()

    import stream_alerts
    db = stream_alerts.StreamAlertsDatabase()
    db.initialize()
    with db._conn() as conn:
        row = conn.execute(
            "SELECT id FROM stream_alerts WHERE guild_id = ? AND platform = ? AND creator_username = ?",
            (str(guild_id), platform, username),
        ).fetchone()
        if not row:
            return web.json_response({"error": "Alert not found"}, status=404)
        conn.execute(
            """UPDATE stream_alerts SET notification_channel_id = ?, notify_live = ?,
               notify_videos = ?, custom_live_message = ?, custom_video_message = ? WHERE id = ?""",
            (
                str(data.get("notification_channel_id", "")),
                1 if data.get("notify_live", True) else 0,
                1 if data.get("notify_videos", True) else 0,
                data.get("custom_live_message", ""),
                data.get("custom_video_message", ""),
                row["id"],
            ),
        )
        conn.commit()

    if _auto_sync_requested(data, request):
        bot: commands.Bot = request.app["bot"]
        synced = _replicate_stream_alert_update(
            bot, guild_id, platform, username,
            data.get("notification_channel_id", ""),
            bool(data.get("notify_live", True)),
            bool(data.get("notify_videos", True)),
            data.get("custom_live_message", ""),
            data.get("custom_video_message", ""),
        )
        print(f"[AutoSync] Stream alert update replicated to {synced} other server(s)")

    return web.json_response({"success": True})

async def handle_bot_channels(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = request.match_info["guild_id"]
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return web.json_response({"error": "Guild not found"}, status=404)
    
    channels = []
    for ch in guild.text_channels:
        channels.append({"id": str(ch.id), "name": ch.name})
    return web.json_response({"channels": channels})

# --- Tickets Endpoints ---

async def handle_tickets_get(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    ticket_cog = bot.get_cog("TicketsCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded (check bot console)"}, status=500)
    try:
        cats = ticket_cog.db.get_categories(guild_id)
        log_ch = ticket_cog.db.get_log_channel(guild_id)
        cats_data = [{
            "id": c.id, "name": c.name or "", "button_label": c.button_label or "",
            "button_emoji": c.button_emoji or "\U0001F3AB", "ping_roles": c.ping_roles or "",
            "admin_roles": c.admin_roles or "", "embed_title": c.embed_title or "",
            "embed_description": c.embed_description or "", "ticket_counter": c.ticket_counter or 0,
        } for c in cats]
        return web.json_response({"categories": cats_data, "log_channel_id": str(log_ch) if log_ch else None})
    except Exception as e:
        print(f"[DashboardAPI] Tickets GET error: {e}")
        return web.json_response({"error": f"Failed to read ticket config: {e}"}, status=500)

async def handle_tickets_post(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    name = data.get("name", "").strip()
    if not name:
        return web.json_response({"error": "Category name is required"}, status=400)
    bot: commands.Bot = request.app["bot"]
    ticket_cog = bot.get_cog("TicketsCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded"}, status=500)
    cat_fields = {
        "button_label": data.get("button_label", name).strip(),
        "button_emoji": data.get("button_emoji", "🎫").strip(),
        "ping_roles": data.get("ping_roles", ""),
        "admin_roles": data.get("admin_roles", ""),
        "embed_title": data.get("embed_title", "New Ticket").strip(),
        "embed_description": data.get("embed_description", "").strip(),
    }
    cat_id = ticket_cog.db.add_category(
        guild_id=guild_id, name=name,
        button_label=cat_fields["button_label"],
        button_emoji=cat_fields["button_emoji"],
        ping_roles=cat_fields["ping_roles"],
        admin_roles=cat_fields["admin_roles"],
        embed_title=cat_fields["embed_title"],
        embed_desc=cat_fields["embed_description"],
    )

    if _auto_sync_requested(data, request):
        synced = _replicate_ticket_category_upsert(bot, guild_id, name, cat_fields)
        print(f"[AutoSync] Ticket category replicated to {synced} other server(s)")

    return web.json_response({"success": True, "id": cat_id})

async def handle_tickets_category_put(request: web.Request):
    """Edit an existing ticket category."""
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    category_id = int(request.match_info["category_id"])
    data = await request.json()

    bot: commands.Bot = request.app["bot"]
    ticket_cog = bot.get_cog("TicketsCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded"}, status=500)

    fields = {}
    for key in ("name", "button_label", "button_emoji", "embed_title", "embed_description", "ping_roles", "admin_roles"):
        if key in data:
            fields[key] = str(data[key]).strip()
    if not fields:
        return web.json_response({"error": "No fields to update"}, status=400)

    old_cat = ticket_cog.db.get_category(category_id)
    if not old_cat:
        return web.json_response({"error": "Category not found"}, status=404)

    updated = ticket_cog.db.update_category(guild_id, category_id, **fields)
    if not updated:
        return web.json_response({"error": "Category not found"}, status=404)

    if _auto_sync_requested(data, request):
        new_name = fields.get("name", old_cat.name)
        all_fields = {
            "button_label": fields.get("button_label", old_cat.button_label),
            "button_emoji": fields.get("button_emoji", old_cat.button_emoji),
            "embed_title": fields.get("embed_title", old_cat.embed_title),
            "embed_description": fields.get("embed_description", old_cat.embed_description),
        }
        synced = _replicate_ticket_category_upsert(bot, guild_id, new_name, all_fields)
        print(f"[AutoSync] Ticket category update replicated to {synced} other server(s)")

    return web.json_response({"success": True})

async def handle_tickets_delete(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    category_id = int(request.match_info["category_id"])
    bot: commands.Bot = request.app["bot"]
    ticket_cog = bot.get_cog("TicketsCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded"}, status=500)
    old_cat = ticket_cog.db.get_category(category_id)
    deleted = ticket_cog.db.delete_category(guild_id, category_id)
    if deleted:
        if _auto_sync_requested(None, request):
            synced = _replicate_ticket_category_delete(bot, guild_id, old_cat.name if old_cat else "")
            print(f"[AutoSync] Ticket category delete replicated to {synced} other server(s)")
        return web.json_response({"success": True})
    return web.json_response({"error": "Category not found"}, status=404)

async def get_user_id(request: web.Request):
    sess = _get_session(request)
    return sess.get("user_id") if sess else None

async def check_guild_permissions(request: web.Request, guild_id, user_id):
    sess = _get_session(request)
    return sess is not None

async def handle_tickets_log_channel(request: web.Request):
    user_id = await get_user_id(request)
    if not user_id: return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = int(request.match_info["guild_id"])
    if not await check_guild_permissions(request, guild_id, user_id):
        return web.json_response({"error": "Missing permissions"}, status=403)
        
    data = await request.json()
    channel_id = data.get("channel_id")
    bot: commands.Bot = request.app["bot"]
    ticket_cog = bot.get_cog("TicketsCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded"}, status=500)
    ticket_cog.db.set_log_channel(guild_id, int(channel_id) if channel_id else None)

    if _auto_sync_requested(data, request):
        synced = _replicate_tickets_log_channel(bot, guild_id, int(channel_id) if channel_id else None)
        print(f"[AutoSync] Ticket log channel replicated to {synced} other server(s)")

    return web.json_response({"success": True})

# --- Welcome Endpoints ---
async def handle_welcome_get(request: web.Request):
    user_id = await get_user_id(request)
    if not user_id: return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = request.match_info['guild_id']
    if not await check_guild_permissions(request, guild_id, user_id):
        return web.json_response({"error": "Missing permissions"}, status=403)
        
    from welcome import WelcomeDatabase
    db = WelcomeDatabase()
    config = db.get_config(int(guild_id))
    
    return web.json_response({
        "config": {
            "enabled": config.enabled,
            "channel_id": str(config.channel_id) if config.channel_id else "",
            "message": config.welcome_message,
            "leave_enabled": config.leave_enabled,
            "leave_channel_id": str(config.leave_channel_id) if config.leave_channel_id else "",
            "leave_message": config.leave_message,
            "leave_image_url": config.leave_image_url or ""
        }
    })

async def handle_welcome_post(request: web.Request):
    user_id = await get_user_id(request)
    if not user_id: return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = request.match_info['guild_id']
    if not await check_guild_permissions(request, guild_id, user_id):
        return web.json_response({"error": "Missing permissions"}, status=403)
        
    data = await request.json()
    
    from welcome import WelcomeDatabase
    db = WelcomeDatabase()
    config = db.get_config(int(guild_id))
    
    config.enabled = bool(data.get("enabled", config.enabled))
    channel_id = data.get("channel_id")
    if channel_id is not None:
        config.channel_id = int(channel_id) if channel_id else None
    config.welcome_message = data.get("message", config.welcome_message)
    
    config.leave_enabled = bool(data.get("leave_enabled", config.leave_enabled))
    leave_channel_id = data.get("leave_channel_id")
    if leave_channel_id is not None:
        config.leave_channel_id = int(leave_channel_id) if leave_channel_id else None
    config.leave_message = data.get("leave_message", config.leave_message)
    
    leave_image_url = data.get("leave_image_url")
    if leave_image_url is not None:
        config.leave_image_url = leave_image_url if leave_image_url else None
        
    db.save_config(config)

    if _auto_sync_requested(data, request):
        bot: commands.Bot = request.app["bot"]
        synced = _replicate_welcome(bot, int(guild_id))
        print(f"[AutoSync] Welcome config replicated to {synced} other server(s)")

    return web.json_response({"success": True})

# --- Music ---

async def handle_music_get(request: web.Request):
    user_id = await get_user_id(request)
    if not user_id: return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = int(request.match_info['guild_id'])
    if not await check_guild_permissions(request, guild_id, user_id):
        return web.json_response({"error": "Missing permissions"}, status=403)
        
    bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild or not guild.voice_client:
        return web.json_response({"is_playing": False})
        
    player = guild.voice_client
    if not hasattr(player, 'current') or not player.current:
        return web.json_response({"is_playing": False})
        
    track = player.current
    queue_list = []
    if hasattr(player, 'queue'):
        for q_track in list(player.queue):
            queue_list.append({
                "title": q_track.title,
                "author": q_track.author,
                "length": q_track.length,
            })
            
    return web.json_response({
        "is_playing": True,
        "paused": player.paused,
        "volume": player.volume,
        "loop_mode": getattr(player, "loop_mode", None),
        "current": {
            "title": track.title,
            "author": track.author,
            "length": track.length,
            "position": player.position,
            "thumbnail": track.artwork if hasattr(track, "artwork") else None
        },
        "queue": queue_list
    })

async def handle_music_control(request: web.Request):
    user_id = await get_user_id(request)
    if not user_id: return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = int(request.match_info['guild_id'])
    if not await check_guild_permissions(request, guild_id, user_id):
        return web.json_response({"error": "Missing permissions"}, status=403)
        
    data = await request.json()
    action = data.get("action")
    
    bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild or not guild.voice_client:
        return web.json_response({"error": "Not playing"}, status=400)
        
    player = guild.voice_client
    
    if action == "pause":
        await player.pause(True)
    elif action == "resume":
        await player.pause(False)
    elif action == "skip":
        await player.skip(force=True)
    elif action == "stop":
        await player.disconnect()
    elif action == "loop":
        modes = [None, "single", "queue"]
        current = getattr(player, "loop_mode", None)
        next_mode = modes[(modes.index(current) + 1) % len(modes)] if current in modes else "single"
        player.loop_mode = next_mode
    elif action == "volume" and data.get("volume") is not None:
        await player.set_volume(max(0, min(100, int(data.get("volume")))))
        

    return web.json_response({"success": True})

# --- Server Roles Endpoint ---

async def handle_bot_roles(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild: return web.json_response({"error": "Guild not found"}, status=404)
    roles = []
    for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
        if r.is_default(): continue
        roles.append({
            "id": str(r.id),
            "name": r.name,
            "color": f"#{r.color.value:06x}" if r.color.value else "#99aab5"
        })
    return web.json_response({"roles": roles})

# --- Security & Anti-Nuke Endpoints ---

async def handle_security_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import security
    db = security.SecurityDatabase()
    db.initialize()
    with db._conn() as conn:
        row = conn.execute("SELECT * FROM security_config WHERE guild_id = ?", (str(guild_id),)).fetchone()
    if not row:
        cfg = {
            "anti_spam_enabled": True,
            "spam_msg_limit": 5,
            "spam_time_sec": 5,
            "mass_mention_limit": 5,
            "log_channel_id": "",
            "image_scan_enabled": True
        }
    else:
        cfg = {
            "anti_spam_enabled": bool(row["anti_spam_enabled"]),
            "spam_msg_limit": row["spam_msg_limit"],
            "spam_time_sec": row["spam_time_sec"],
            "mass_mention_limit": row["mass_mention_limit"],
            "log_channel_id": str(row["log_channel_id"]) if row["log_channel_id"] else "",
            "image_scan_enabled": bool(row["image_scan_enabled"])
        }
    return web.json_response({"config": cfg})

async def handle_security_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    import security
    db = security.SecurityDatabase()
    db.initialize()
    with db._conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO security_config 
            (guild_id, anti_spam_enabled, spam_msg_limit, spam_time_sec, mass_mention_limit, log_channel_id, image_scan_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(guild_id),
            1 if data.get("anti_spam_enabled", True) else 0,
            int(data.get("spam_msg_limit", 5)),
            int(data.get("spam_time_sec", 5)),
            int(data.get("mass_mention_limit", 5)),
            str(data.get("log_channel_id")) if data.get("log_channel_id") else None,
            1 if data.get("image_scan_enabled", True) else 0
        ))
        conn.commit()

    if _auto_sync_requested(data, request):
        bot: commands.Bot = request.app["bot"]
        synced = _replicate_security(bot, guild_id)
        print(f"[AutoSync] Security config replicated to {synced} other server(s)")

    return web.json_response({"success": True})

# --- Sticky Messages Endpoints ---

async def handle_sticky_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import sticky_messages
    db = sticky_messages.StickyDB()
    rows = db.get_all_for_guild(guild_id)
    items = [{"channel_id": str(r["channel_id"]), "content": r["content"]} for r in rows]
    return web.json_response({"stickies": items})

async def handle_sticky_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    channel_id = data.get("channel_id")
    content = data.get("content", "").strip()
    if not channel_id or not content:
        return web.json_response({"error": "Channel and message content are required"}, status=400)
    import sticky_messages
    db = sticky_messages.StickyDB()
    db.set_sticky(int(channel_id), guild_id, content)

    if _auto_sync_requested(data, request):
        bot: commands.Bot = request.app["bot"]
        synced = _replicate_sticky_set(bot, guild_id, int(channel_id), content)
        print(f"[AutoSync] Sticky message replicated to {synced} other server(s)")

    return web.json_response({"success": True})

async def handle_sticky_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    channel_id = int(request.match_info["channel_id"])
    import sticky_messages
    db = sticky_messages.StickyDB()
    db.remove_sticky(channel_id)

    if _auto_sync_requested(None, request):
        bot: commands.Bot = request.app["bot"]
        synced = _replicate_sticky_remove(bot, guild_id, channel_id)
        print(f"[AutoSync] Sticky removal replicated to {synced} other server(s)")

    return web.json_response({"success": True})

# --- Auto Reactions Endpoints ---

async def handle_autoreact_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import auto_reactions
    db = auto_reactions.AutoReactDB()
    with db._conn() as conn:
        rows = conn.execute("SELECT * FROM auto_reactions WHERE guild_id = ?", (str(guild_id),)).fetchall()
    items = [{"id": r["id"], "channel_id": str(r["channel_id"]), "emoji": r["emoji"]} for r in rows]
    return web.json_response({"reactions": items})

async def handle_autoreact_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    channel_id = data.get("channel_id")
    emoji = data.get("emoji", "").strip()
    if not channel_id or not emoji:
        return web.json_response({"error": "Channel and emoji are required"}, status=400)
    import auto_reactions
    db = auto_reactions.AutoReactDB()
    ok = db.add_reaction(guild_id, int(channel_id), emoji)
    if not ok:
        return web.json_response({"error": "Reaction already exists for this channel"}, status=400)

    if _auto_sync_requested(data, request):
        bot: commands.Bot = request.app["bot"]
        synced = _replicate_autoreact_add(bot, guild_id, int(channel_id), emoji)
        print(f"[AutoSync] Auto reaction replicated to {synced} other server(s)")

    return web.json_response({"success": True})

async def handle_autoreact_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    rx_id = int(request.match_info["id"])
    import auto_reactions
    db = auto_reactions.AutoReactDB()
    with db._conn() as conn:
        row = conn.execute("SELECT channel_id FROM auto_reactions WHERE id = ?", (rx_id,)).fetchone()
        conn.execute("DELETE FROM auto_reactions WHERE id = ?", (rx_id,))
        conn.commit()

    if row and _auto_sync_requested(None, request):
        bot: commands.Bot = request.app["bot"]
        try:
            synced = _replicate_autoreact_remove(bot, guild_id, int(row["channel_id"]))
            print(f"[AutoSync] Auto reaction removal replicated to {synced} other server(s)")
        except (ValueError, TypeError):
            pass

    return web.json_response({"success": True})

# --- Moderation & Staff Roles Endpoints ---

async def handle_moderation_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import moderation
    db = moderation.ModerationDatabase()
    db.initialize()
    with db._conn() as conn:
        rows = conn.execute("SELECT role_id FROM staff_roles WHERE guild_id = ?", (str(guild_id),)).fetchall()
    staff_roles = [str(r["role_id"]) for r in rows]
    return web.json_response({"staff_roles": staff_roles})

async def handle_moderation_staff_add(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    role_id = data.get("role_id")
    if not role_id: return web.json_response({"error": "Role ID required"}, status=400)
    import moderation
    db = moderation.ModerationDatabase()
    db.initialize()
    db.add_staff_role(guild_id, int(role_id))

    if _auto_sync_requested(data, request):
        bot: commands.Bot = request.app["bot"]
        synced = _replicate_staff_role_add(bot, guild_id, int(role_id))
        print(f"[AutoSync] Staff role replicated to {synced} other server(s)")

    return web.json_response({"success": True})

async def handle_moderation_staff_del(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    role_id = int(request.match_info["role_id"])
    import moderation
    db = moderation.ModerationDatabase()
    db.initialize()
    db.remove_staff_role(guild_id, role_id)

    if _auto_sync_requested(None, request):
        bot: commands.Bot = request.app["bot"]
        synced = _replicate_staff_role_remove(bot, guild_id, role_id)
        print(f"[AutoSync] Staff role removal replicated to {synced} other server(s)")

    return web.json_response({"success": True})

# --- Voice Channels Endpoint (for Temp VC etc.) ---

async def handle_bot_voice_channels(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = request.match_info["guild_id"]
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return web.json_response({"error": "Guild not found"}, status=404)

    channels = []
    categories = []
    for ch in guild.voice_channels:
        channels.append({"id": str(ch.id), "name": ch.name})
    for cat in guild.categories:
        categories.append({"id": str(cat.id), "name": cat.name})
    return web.json_response({"channels": channels, "categories": categories})

# --- Custom Commands Endpoints ---

async def handle_custom_commands_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import custom_commands
    db = custom_commands.CustomCommandDatabase()
    db.initialize()
    cmds = db.list_all(guild_id)
    return web.json_response({"commands": [
        {"id": c["id"], "name": c["name"], "response": c["response"], "uses": c.get("uses", 0)}
        for c in cmds
    ]})

async def handle_custom_commands_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    name = data.get("name", "").strip().lower().lstrip("!")
    response = data.get("response", "").strip()
    if not name or not response:
        return web.json_response({"error": "Command name and response are required"}, status=400)
    if len(name) > 30:
        return web.json_response({"error": "Command name must be 30 characters or fewer"}, status=400)
    if len(response) > 2000:
        return web.json_response({"error": "Response must be 2000 characters or fewer"}, status=400)
    import custom_commands
    db = custom_commands.CustomCommandDatabase()
    db.initialize()
    ok = db.create(guild_id, name, response, created_by=0)
    if not ok:
        return web.json_response({"error": f"A command named !{name} already exists"}, status=400)
    return web.json_response({"success": True})

async def handle_custom_commands_put(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    name = request.match_info["name"].lower()
    data = await request.json()
    response = data.get("response", "").strip()
    if not response:
        return web.json_response({"error": "Response is required"}, status=400)
    if len(response) > 2000:
        return web.json_response({"error": "Response must be 2000 characters or fewer"}, status=400)
    import custom_commands
    db = custom_commands.CustomCommandDatabase()
    ok = db.edit(guild_id, name, response)
    if not ok:
        return web.json_response({"error": "Command not found"}, status=404)
    return web.json_response({"success": True})

async def handle_custom_commands_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    name = request.match_info["name"].lower()
    import custom_commands
    db = custom_commands.CustomCommandDatabase()
    ok = db.delete(guild_id, name)
    if not ok:
        return web.json_response({"error": "Command not found"}, status=404)
    return web.json_response({"success": True})

# --- Economy Endpoints ---

async def handle_economy_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import economy
    db = economy.EconomyDatabase()
    db.initialize()
    items = db.get_shop_items(guild_id)
    with db._conn() as conn:
        row = conn.execute("SELECT rob_enabled, crime_enabled FROM eco_settings WHERE guild_id = ?", (str(guild_id),)).fetchone()
    return web.json_response({
        "shop_items": [
            {"id": i["id"], "name": i["name"], "description": i["description"],
             "price": i["price"], "role_id": i["role_id"]}
            for i in items
        ],
        "settings": {
            "rob_enabled": bool(row["rob_enabled"]) if row else True,
            "crime_enabled": bool(row["crime_enabled"]) if row else True,
        }
    })

async def handle_economy_shop_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    try:
        price = int(data.get("price", 0))
    except (ValueError, TypeError):
        return web.json_response({"error": "Price must be a number"}, status=400)
    role_id = data.get("role_id") or None
    if not name or price < 0:
        return web.json_response({"error": "Item name and a valid price are required"}, status=400)
    import economy
    db = economy.EconomyDatabase()
    db.initialize()
    item_id = db.add_shop_item(guild_id, name, description, price, int(role_id) if role_id else None)
    return web.json_response({"success": True, "id": item_id})

async def handle_economy_shop_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    item_id = int(request.match_info["item_id"])
    import economy
    db = economy.EconomyDatabase()
    ok = db.remove_shop_item(guild_id, item_id)
    if not ok:
        return web.json_response({"error": "Item not found"}, status=404)
    return web.json_response({"success": True})

async def handle_economy_settings_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    import economy
    db = economy.EconomyDatabase()
    db.initialize()
    with db._conn() as conn:
        conn.execute("""
            INSERT INTO eco_settings (guild_id, rob_enabled, crime_enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                rob_enabled = excluded.rob_enabled,
                crime_enabled = excluded.crime_enabled
        """, (
            str(guild_id),
            1 if data.get("rob_enabled", True) else 0,
            1 if data.get("crime_enabled", True) else 0,
        ))
        conn.commit()
    return web.json_response({"success": True})

# --- Temp VC Endpoints ---

async def handle_tempvc_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import temp_vc
    hub_ids = temp_vc.get_hubs(guild_id)
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    hubs = []
    for cid in hub_ids:
        cat_id = None
        with temp_vc._db() as conn:
            row = conn.execute("SELECT category_id FROM tempvc_hubs WHERE channel_id = ?", (cid,)).fetchone()
            if row:
                cat_id = row["category_id"]
        ch = guild.get_channel(int(cid)) if guild else None
        hubs.append({
            "channel_id": str(cid),
            "channel_name": ch.name if ch else f"Channel {cid}",
            "category_id": str(cat_id) if cat_id else None,
        })
    return web.json_response({"hubs": hubs})

async def handle_tempvc_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    channel_id = data.get("channel_id")
    if not channel_id:
        return web.json_response({"error": "A voice channel is required"}, status=400)
    category_id = data.get("category_id") or None
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    ch = guild.get_channel(int(channel_id)) if guild else None
    if not ch:
        return web.json_response({"error": "Voice channel not found on this server"}, status=404)
    import temp_vc
    temp_vc.add_hub(guild_id, ch.id, int(category_id) if category_id else None)
    return web.json_response({"success": True})

async def handle_tempvc_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    channel_id = int(request.match_info["channel_id"])
    import temp_vc
    temp_vc.remove_hub(guild_id, channel_id)
    return web.json_response({"success": True})

# --- Multi-Server Sync Engine ---

async def handle_guild_sync(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    source_guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    target_guild_ids = data.get("target_guild_ids", [])
    modules = data.get("modules", [])
    if not target_guild_ids:
        return web.json_response({"error": "Please select at least one target server"}, status=400)
    if not modules:
        return web.json_response({"error": "Please select at least one module to sync"}, status=400)

    bot: commands.Bot = request.app["bot"]
    synced_count = 0

    for tgt_id in target_guild_ids:
        tgt_int = int(tgt_id)
        if tgt_int == source_guild_id:
            continue

        # 1. Sync Welcome
        if "welcome" in modules or "all" in modules:
            try:
                from welcome import WelcomeDatabase
                w_db = WelcomeDatabase()
                src_cfg = w_db.get_config(source_guild_id)
                if src_cfg:
                    tgt_cfg = w_db.get_config(tgt_int)
                    tgt_cfg.enabled = src_cfg.enabled
                    tgt_cfg.welcome_message = src_cfg.welcome_message
                    tgt_cfg.leave_enabled = src_cfg.leave_enabled
                    tgt_cfg.leave_message = src_cfg.leave_message
                    tgt_cfg.leave_image_url = src_cfg.leave_image_url
                    w_db.save_config(tgt_cfg)
            except Exception as e:
                print(f"[Sync] Welcome sync error for {tgt_int}: {e}")

        # 2. Sync Security
        if "security" in modules or "all" in modules:
            try:
                import security
                s_db = security.SecurityDatabase()
                s_db.initialize()
                with s_db._conn() as conn:
                    s_row = conn.execute("SELECT * FROM security_config WHERE guild_id = ?", (str(source_guild_id),)).fetchone()
                    if s_row:
                        conn.execute("""
                            INSERT OR REPLACE INTO security_config
                            (guild_id, anti_spam_enabled, spam_msg_limit, spam_time_sec, mass_mention_limit, log_channel_id, image_scan_enabled)
                            VALUES (?, ?, ?, ?, ?, (SELECT log_channel_id FROM security_config WHERE guild_id = ?), ?)
                        """, (
                            str(tgt_int),
                            s_row["anti_spam_enabled"],
                            s_row["spam_msg_limit"],
                            s_row["spam_time_sec"],
                            s_row["mass_mention_limit"],
                            str(tgt_int),
                            s_row["image_scan_enabled"]
                        ))
                        conn.commit()
            except Exception as e:
                print(f"[Sync] Security sync error for {tgt_int}: {e}")

        # 3. Sync Sticky Messages
        if "sticky" in modules or "all" in modules:
            try:
                import sticky_messages
                st_db = sticky_messages.StickyDB()
                src_stickies = st_db.get_all_for_guild(source_guild_id)
                src_guild = bot.get_guild(source_guild_id)
                tgt_guild = bot.get_guild(tgt_int)
                if src_guild and tgt_guild and src_stickies:
                    for st in src_stickies:
                        src_ch = src_guild.get_channel(int(st["channel_id"]))
                        if src_ch:
                            match_ch = discord.utils.get(tgt_guild.text_channels, name=src_ch.name)
                            if match_ch:
                                st_db.set_sticky(match_ch.id, tgt_int, st["content"])
            except Exception as e:
                print(f"[Sync] Sticky sync error for {tgt_int}: {e}")

        # 4. Sync Auto Reactions
        if "autoreact" in modules or "all" in modules:
            try:
                import auto_reactions
                ar_db = auto_reactions.AutoReactDB()
                src_guild = bot.get_guild(source_guild_id)
                tgt_guild = bot.get_guild(tgt_int)
                with ar_db._conn() as conn:
                    rows = conn.execute("SELECT * FROM auto_reactions WHERE guild_id = ?", (str(source_guild_id),)).fetchall()
                    if src_guild and tgt_guild and rows:
                        for r in rows:
                            src_ch = src_guild.get_channel(int(r["channel_id"]))
                            if src_ch:
                                match_ch = discord.utils.get(tgt_guild.text_channels, name=src_ch.name)
                                if match_ch:
                                    ar_db.add_reaction(tgt_int, match_ch.id, r["emoji"])
            except Exception as e:
                print(f"[Sync] AutoReact sync error for {tgt_int}: {e}")

        # 5. Sync Tickets (categories + log channel; role pings are not copied as role IDs differ per server)
        if "tickets" in modules or "all" in modules:
            try:
                cog = bot.get_cog("TicketsCog")
                if cog:
                    src_guild = bot.get_guild(source_guild_id)
                    tgt_guild = bot.get_guild(tgt_int)
                    src_log = cog.db.get_log_channel(source_guild_id)
                    tgt_log = None
                    if src_log and src_guild and tgt_guild:
                        src_ch = src_guild.get_channel(int(src_log))
                        if src_ch:
                            tgt_log = discord.utils.get(tgt_guild.text_channels, name=src_ch.name)
                    cog.db.set_log_channel(tgt_int, tgt_log.id if tgt_log else None)
                    for c in cog.db.get_categories(source_guild_id):
                        fields = {
                            "button_label": c.button_label, "button_emoji": c.button_emoji,
                            "ping_roles": "", "admin_roles": "",
                            "embed_title": c.embed_title, "embed_description": c.embed_description,
                        }
                        existing = next((tc for tc in cog.db.get_categories(tgt_int) if tc.name == c.name), None)
                        if existing:
                            cog.db.update_category(tgt_int, existing.id, **fields)
                        else:
                            cog.db.add_category(guild_id=tgt_int, name=c.name, **fields)
            except Exception as e:
                print(f"[Sync] Tickets sync error for {tgt_int}: {e}")

        # 6. Sync Stream Alerts (matches notification channels by name)
        if "streamalerts" in modules or "all" in modules:
            try:
                import stream_alerts as sa_mod
                sa_db = sa_mod.StreamAlertsDatabase()
                sa_db.initialize()
                src_guild = bot.get_guild(source_guild_id)
                tgt_guild = bot.get_guild(tgt_int)
                with sa_db._conn() as conn:
                    for a in conn.execute("SELECT * FROM stream_alerts WHERE guild_id = ?", (str(source_guild_id),)).fetchall():
                        src_ch = src_guild.get_channel(int(a["notification_channel_id"])) if src_guild else None
                        tgt_ch = discord.utils.get(tgt_guild.text_channels, name=src_ch.name) if (src_ch and tgt_guild) else None
                        if not tgt_ch:
                            continue
                        existing = conn.execute(
                            "SELECT id FROM stream_alerts WHERE guild_id = ? AND platform = ? AND creator_username = ?",
                            (str(tgt_int), a["platform"], a["creator_username"]),
                        ).fetchone()
                        if existing:
                            conn.execute(
                                "UPDATE stream_alerts SET notification_channel_id = ? WHERE id = ?",
                                (str(tgt_ch.id), existing["id"]),
                            )
                        else:
                            conn.execute(
                                """INSERT INTO stream_alerts
                                   (guild_id, platform, creator_username, creator_id, notification_channel_id)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (str(tgt_int), a["platform"], a["creator_username"], a["creator_id"], str(tgt_ch.id)),
                            )
                    conn.commit()
            except Exception as e:
                print(f"[Sync] StreamAlerts sync error for {tgt_int}: {e}")

        # 7. Sync Staff Roles (matches roles by name)
        if "moderation" in modules or "all" in modules:
            try:
                import moderation as mod_mod
                m_db = mod_mod.ModerationDatabase()
                m_db.initialize()
                src_guild = bot.get_guild(source_guild_id)
                tgt_guild = bot.get_guild(tgt_int)
                if src_guild and tgt_guild:
                    for rid in m_db.get_staff_roles(source_guild_id):
                        src_role = src_guild.get_role(int(rid))
                        if src_role:
                            tgt_role = discord.utils.get(tgt_guild.roles, name=src_role.name)
                            if tgt_role:
                                m_db.add_staff_role(tgt_int, tgt_role.id)
            except Exception as e:
                print(f"[Sync] Moderation sync error for {tgt_int}: {e}")

        synced_count += 1


# --- Dynamic Registration & Application Endpoints ---

async def handle_registration_list_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = str(request.match_info["guild_id"])
    import registration
    db = registration.db
    forms = db.get_guild_forms(guild_id)
    items = []
    for f in forms:
        q_count = len(db.get_questions(f["id"]))
        subs = db.get_submissions(f["id"])
        pending_count = sum(1 for s in subs if s["status"] == "pending")
        items.append({
            "id": f["id"],
            "guild_id": f["guild_id"],
            "name": f["name"],
            "description": f["description"],
            "channel_id": f["channel_id"],
            "panel_message_id": f["panel_message_id"],
            "button_label": f["button_label"],
            "button_emoji": f["button_emoji"],
            "button_style": f["button_style"],
            "enabled": bool(f["enabled"]),
            "approval_mode": f["approval_mode"],
            "review_channel_id": f["review_channel_id"],
            "log_channel_id": f["log_channel_id"],
            "auto_role_enabled": bool(f["auto_role_enabled"]),
            "add_role_ids": json.loads(f["add_role_ids"] or "[]"),
            "remove_role_enabled": bool(f["remove_role_enabled"]),
            "remove_role_ids": json.loads(f["remove_role_ids"] or "[]"),
            "change_nickname_enabled": bool(f["change_nickname_enabled"]),
            "nickname_question_id": f["nickname_question_id"],
            "nickname_format": f["nickname_format"],
            "question_count": q_count,
            "submission_count": len(subs),
            "pending_count": pending_count,
            "created_at": f["created_at"],
            "updated_at": f["updated_at"]
        })
    return web.json_response({"forms": items})

async def handle_registration_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = str(request.match_info["guild_id"])
    data = await request.json()
    name = (data.get("name") or "Server Registration").strip()
    desc = (data.get("description") or "").strip()
    import registration
    db = registration.db
    form_id = db.create_form(guild_id, name=name, description=desc, created_by=str(sess.get("user_id")))
    return web.json_response({"success": True, "id": form_id})

async def handle_registration_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    form_id = int(request.match_info["form_id"])
    import registration
    db = registration.db
    form = db.get_form(form_id)
    if not form:
        return web.json_response({"error": "Form not found"}, status=404)
    questions = db.get_questions(form_id)
    q_items = []
    for q in questions:
        opts = []
        try:
            opts = json.loads(q["options"] or "[]")
        except Exception:
            opts = []
        q_items.append({
            "id": q["id"],
            "registration_id": q["registration_id"],
            "question": q["question"],
            "field_type": q["field_type"],
            "required": bool(q["required"]),
            "placeholder": q["placeholder"],
            "options": opts,
            "min_length": q["min_length"],
            "max_length": q["max_length"],
            "min_value": q["min_value"],
            "max_value": q["max_value"],
            "position": q["position"]
        })
    return web.json_response({
        "form": {
            "id": form["id"],
            "guild_id": form["guild_id"],
            "name": form["name"],
            "description": form["description"],
            "channel_id": form["channel_id"],
            "panel_message_id": form["panel_message_id"],
            "button_label": form["button_label"],
            "button_emoji": form["button_emoji"],
            "button_style": form["button_style"],
            "enabled": bool(form["enabled"]),
            "approval_mode": form["approval_mode"],
            "review_channel_id": form["review_channel_id"],
            "log_channel_id": form["log_channel_id"],
            "auto_role_enabled": bool(form["auto_role_enabled"]),
            "add_role_ids": json.loads(form["add_role_ids"] or "[]"),
            "remove_role_enabled": bool(form["remove_role_enabled"]),
            "remove_role_ids": json.loads(form["remove_role_ids"] or "[]"),
            "change_nickname_enabled": bool(form["change_nickname_enabled"]),
            "nickname_question_id": form["nickname_question_id"],
            "nickname_format": form["nickname_format"],
            "single_submission": bool(form["single_submission"]),
            "success_message": form["success_message"],
            "questions": q_items
        }
    })

async def handle_registration_put(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    form_id = int(request.match_info["form_id"])
    data = await request.json()
    import registration
    db = registration.db
    form = db.get_form(form_id)
    if not form:
        return web.json_response({"error": "Form not found"}, status=404)
    upd = {}
    for key in ("name", "description", "channel_id", "button_label", "button_emoji", "button_style",
                "enabled", "approval_mode", "review_channel_id", "log_channel_id",
                "auto_role_enabled", "remove_role_enabled", "change_nickname_enabled",
                "nickname_question_id", "nickname_format", "single_submission", "success_message"):
        if key in data:
            upd[key] = data[key]
    if "add_role_ids" in data:
        upd["add_role_ids"] = json.dumps(data["add_role_ids"])
    if "remove_role_ids" in data:
        upd["remove_role_ids"] = json.dumps(data["remove_role_ids"])
    db.update_form(form_id, **upd)
    return web.json_response({"success": True})

async def handle_registration_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    form_id = int(request.match_info["form_id"])
    import registration
    db = registration.db
    success = db.delete_form(form_id)
    return web.json_response({"success": success})

async def handle_registration_publish(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    form_id = int(request.match_info["form_id"])
    data = await request.json()
    channel_id = data.get("channel_id")
    import registration
    db = registration.db
    form = db.get_form(form_id)
    if not form:
        return web.json_response({"error": "Form not found"}, status=404)
    target_chan_id = int(channel_id or form["channel_id"] or 0)
    if not target_chan_id:
        return web.json_response({"error": "No target channel selected"}, status=400)
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild:
        return web.json_response({"error": "Guild not found"}, status=404)
    channel = guild.get_channel(target_chan_id)
    if not channel:
        return web.json_response({"error": "Channel not found"}, status=404)

    embed = discord.Embed(
        title=f"📝 {form['name']}",
        description=form["description"] or "Welcome to our registration system.\nClick the button below to begin your registration.",
        color=0x5865F2
    )
    if form["thumbnail_url"]: embed.set_thumbnail(url=form["thumbnail_url"])
    if form["image_url"]: embed.set_image(url=form["image_url"])
    embed.set_footer(text=form["footer_text"] or f"{BOT_NAME} Dynamic Registration System")

    view = registration.build_panel_view(form)
    msg = await channel.send(embed=embed, view=view)
    db.update_form(form_id, channel_id=str(channel.id), panel_message_id=str(msg.id))
    bot.add_view(view)
    return web.json_response({"success": True, "message_id": str(msg.id), "channel_id": str(channel.id)})

async def handle_registration_questions_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    form_id = int(request.match_info["form_id"])
    data = await request.json()
    import registration
    db = registration.db
    q_id = db.add_question(
        form_id,
        question=data.get("question", "Question"),
        field_type=data.get("field_type", "short_text"),
        required=bool(data.get("required", True)),
        placeholder=data.get("placeholder", ""),
        options=data.get("options", []),
        min_length=data.get("min_length"),
        max_length=data.get("max_length"),
        min_value=data.get("min_value"),
        max_value=data.get("max_value")
    )
    return web.json_response({"success": True, "id": q_id})

async def handle_registration_question_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    q_id = int(request.match_info["question_id"])
    import registration
    db = registration.db
    success = db.delete_question(q_id)
    return web.json_response({"success": success})

async def handle_registration_submissions_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    form_id = int(request.match_info["form_id"])
    status_filter = request.query.get("status")
    import registration
    db = registration.db
    subs = db.get_submissions(form_id, status=status_filter)
    res = []
    for s in subs:
        answers = db.get_answers(s["id"])
        ans_list = [{"question_text": a["question_text"], "field_type": a["field_type"], "answer": a["answer"]} for a in answers]
        res.append({
            "id": s["id"],
            "registration_id": s["registration_id"],
            "guild_id": s["guild_id"],
            "user_id": s["user_id"],
            "status": s["status"],
            "submitted_at": s["submitted_at"],
            "reviewed_at": s["reviewed_at"],
            "reviewed_by": s["reviewed_by"],
            "rejection_reason": s["rejection_reason"],
            "answers": ans_list
        })
    return web.json_response({"submissions": res})

async def handle_registration_submission_review(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    sub_id = int(request.match_info["sub_id"])
    data = await request.json()
    action = data.get("action")
    reason = data.get("reason", "")
    import registration
    db = registration.db
    sub = db.get_submission(sub_id)
    if not sub:
        return web.json_response({"error": "Submission not found"}, status=404)
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(int(sub["guild_id"]))
    member = guild.get_member(int(sub["user_id"])) if guild else None
    config = db.get_form(sub["registration_id"])

    if action == "approve":
        db.update_submission_status(sub_id, "approved", reviewed_by=str(sess.get("user_id")))
        answers_dict = {a["question_id"]: a["answer"] for a in db.get_answers(sub_id)}
        if member and config:
            await registration.execute_post_registration_actions(bot, guild, member, config, answers_dict)
            try:
                dm_embed = discord.Embed(
                    title=f"🎉 Registration Approved — {guild.name}",
                    description=f"Your registration for **{config['name']}** has been accepted by our staff team!",
                    color=0x57F287
                )
                await member.send(embed=dm_embed)
            except Exception:
                pass
        return web.json_response({"success": True, "status": "approved"})

    elif action == "reject":
        db.update_submission_status(sub_id, "rejected", reviewed_by=str(sess.get("user_id")), rejection_reason=reason)
        if member and config:
            try:
                dm_embed = discord.Embed(
                    title=f"❌ Registration Update — {guild.name}",
                    description=f"Your registration for **{config['name']}** was not approved.\n\n**Reason:**\n> {reason or 'No reason provided.'}",
                    color=0xED4245
                )
                await member.send(embed=dm_embed)
            except Exception:
                pass
        return web.json_response({"success": True, "status": "rejected"})

    return web.json_response({"error": "Invalid action"}, status=400)

async def handle_registration_logs_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = str(request.match_info["guild_id"])
    import registration
    db = registration.db
    logs = db.get_logs(guild_id, limit=50)
    items = [{
        "id": l["id"],
        "event_type": l["event_type"],
        "actor_id": l["actor_id"],
        "target_user_id": l["target_user_id"],
        "details": l["details"],
        "created_at": l["created_at"]
    } for l in logs]
    return web.json_response({"logs": items})


class DashboardAPI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner = None

    async def cog_load(self):
        _load_sessions()
        app = web.Application(middlewares=[cors_middleware])
        app["bot"] = self.bot
        
        # Add routes
        app.add_routes([
            web.get("/api/auth/discord", handle_login),
            web.get("/api/auth/callback", handle_callback_redirect),
            web.post("/api/auth/callback", handle_callback),
            web.get("/api/users/@me", handle_me),
            web.get("/api/bot-info", handle_bot_info),
            web.get("/api/config", handle_bot_info),
            # Channels & Roles (shared)
            web.get("/api/guilds/{guild_id}/channels", handle_bot_channels),
            web.get("/api/guilds/{guild_id}/roles", handle_bot_roles),
            web.get("/api/guilds/{guild_id}/voice-channels", handle_bot_voice_channels),
            # Custom Commands
            web.get("/api/guilds/{guild_id}/custom-commands", handle_custom_commands_get),
            web.post("/api/guilds/{guild_id}/custom-commands", handle_custom_commands_post),
            web.put("/api/guilds/{guild_id}/custom-commands/{name}", handle_custom_commands_put),
            web.delete("/api/guilds/{guild_id}/custom-commands/{name}", handle_custom_commands_delete),
            # Economy
            web.get("/api/guilds/{guild_id}/economy", handle_economy_get),
            web.post("/api/guilds/{guild_id}/economy/shop", handle_economy_shop_post),
            web.delete("/api/guilds/{guild_id}/economy/shop/{item_id}", handle_economy_shop_delete),
            web.post("/api/guilds/{guild_id}/economy/settings", handle_economy_settings_post),
            # Temp VC
            web.get("/api/guilds/{guild_id}/tempvc", handle_tempvc_get),
            web.post("/api/guilds/{guild_id}/tempvc", handle_tempvc_post),
            web.delete("/api/guilds/{guild_id}/tempvc/{channel_id}", handle_tempvc_delete),
            # Stream Alerts
            web.get("/api/guilds/{guild_id}/stream-alerts", handle_stream_alerts_get),
            web.post("/api/guilds/{guild_id}/stream-alerts", handle_stream_alerts_post),
            web.delete("/api/guilds/{guild_id}/stream-alerts/{platform}/{username}", handle_stream_alerts_delete),
            web.put("/api/guilds/{guild_id}/stream-alerts/{platform}/{username}", handle_stream_alerts_put),
            # Tickets
            web.get("/api/guilds/{guild_id}/tickets", handle_tickets_get),
            web.post("/api/guilds/{guild_id}/tickets", handle_tickets_post),
            web.delete("/api/guilds/{guild_id}/tickets/{category_id}", handle_tickets_delete),
            web.put("/api/guilds/{guild_id}/tickets/categories/{category_id}", handle_tickets_category_put),
            web.post("/api/guilds/{guild_id}/tickets/log-channel", handle_tickets_log_channel),
            # Welcome
            web.get("/api/guilds/{guild_id}/welcome", handle_welcome_get),
            web.post("/api/guilds/{guild_id}/welcome", handle_welcome_post),
            # Security & Anti-Nuke
            web.get("/api/guilds/{guild_id}/security", handle_security_get),
            web.post("/api/guilds/{guild_id}/security", handle_security_post),
            # Sticky Messages
            web.get("/api/guilds/{guild_id}/sticky", handle_sticky_get),
            web.post("/api/guilds/{guild_id}/sticky", handle_sticky_post),
            web.delete("/api/guilds/{guild_id}/sticky/{channel_id}", handle_sticky_delete),
            # Auto Reactions
            web.get("/api/guilds/{guild_id}/auto-reactions", handle_autoreact_get),
            web.post("/api/guilds/{guild_id}/auto-reactions", handle_autoreact_post),
            web.delete("/api/guilds/{guild_id}/auto-reactions/{id}", handle_autoreact_delete),
            # Moderation & Staff
            web.get("/api/guilds/{guild_id}/moderation", handle_moderation_get),
            web.post("/api/guilds/{guild_id}/moderation/staff-roles", handle_moderation_staff_add),
            web.delete("/api/guilds/{guild_id}/moderation/staff-roles/{role_id}", handle_moderation_staff_del),
            # Multi-Server Sync
            web.post("/api/guilds/{guild_id}/sync", handle_guild_sync),
            # Music
            web.get("/api/guilds/{guild_id}/music", handle_music_get),
            web.post("/api/guilds/{guild_id}/music/control", handle_music_control),
            # Registration & Applications
            web.get("/api/guilds/{guild_id}/registration", handle_registration_list_get),
            web.post("/api/guilds/{guild_id}/registration", handle_registration_post),
            web.get("/api/guilds/{guild_id}/registration/logs", handle_registration_logs_get),
            web.get("/api/guilds/{guild_id}/registration/{form_id}", handle_registration_get),
            web.put("/api/guilds/{guild_id}/registration/{form_id}", handle_registration_put),
            web.delete("/api/guilds/{guild_id}/registration/{form_id}", handle_registration_delete),
            web.post("/api/guilds/{guild_id}/registration/{form_id}/publish", handle_registration_publish),
            web.post("/api/guilds/{guild_id}/registration/{form_id}/questions", handle_registration_questions_post),
            web.delete("/api/guilds/{guild_id}/registration/{form_id}/questions/{question_id}", handle_registration_question_delete),
            web.get("/api/guilds/{guild_id}/registration/{form_id}/submissions", handle_registration_submissions_get),
            web.post("/api/guilds/{guild_id}/registration/submissions/{sub_id}/review", handle_registration_submission_review),
        ])
        
        # Static file serving if dashboard-ui/dist exists
        dist_path = os.path.join(os.path.dirname(__file__), "dashboard-ui", "dist")
        if os.path.exists(dist_path):
            assets_path = os.path.join(dist_path, "assets")
            if os.path.exists(assets_path):
                app.router.add_static("/assets", assets_path, name="assets")

            async def spa_handler(request: web.Request):
                if request.path.startswith("/api"):
                    raise web.HTTPNotFound()
                rel = request.match_info.get("tail", "").lstrip("/")
                target = os.path.normpath(os.path.join(dist_path, rel))
                # Prevent directory traversal
                if rel and os.path.isfile(target) and target.startswith(dist_path):
                    return web.FileResponse(target)
                index_path = os.path.join(dist_path, "index.html")
                if os.path.exists(index_path):
                    return web.FileResponse(index_path)
                return web.Response(text="Dashboard UI index.html not found.", status=404)

            app.router.add_get("/{tail:.*}", spa_handler)
            print(f"📦 Dashboard website enabled! Serving build from: {dist_path}")
        else:
            print(f"[DashboardAPI] Checked for UI build at: {dist_path} (exists={os.path.exists(dist_path)})")
            async def dev_index(request: web.Request):
                if request.path.startswith("/api"):
                    raise web.HTTPNotFound()
                return web.Response(
                    text=f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{BOT_NAME} Bot Dashboard</title>
<style>body{{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}
.card{{background:#1e293b;padding:32px;border-radius:16px;border:1px solid #334155;max-width:480px;text-align:center;}}
h1{{margin-top:0;color:#60a5fa;font-size:22px;}}p{{color:#94a3b8;font-size:14px;line-height:1.6;}}
code{{background:#090d16;padding:2px 6px;border-radius:4px;color:#38bdf8;}}
</style></head>
<body><div class="card">
<h1>🤖 {BOT_NAME} Bot Dashboard API Running</h1>
<p>To serve the full website directly from this port, run:<br><code>npm run build</code> inside the <code>dashboard-ui</code> directory and restart the bot.</p>
<p>For development with hot reload, run <code>npm run dev</code> inside <code>dashboard-ui</code> (port 5173).</p>
</div></body></html>""",
                    content_type="text/html"
                )
            app.router.add_get("/", dev_index)
            print(f"💡 Dashboard UI 'dist' not found. Run 'npm run build' in dashboard-ui to enable unified web hosting.")

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        
        # Auto-detect port (Pterodactyl uses SERVER_PORT, cloud hosts use PORT, fallback to DASHBOARD_PORT or 8085)
        port = int(os.getenv("SERVER_PORT") or os.getenv("DASHBOARD_PORT") or os.getenv("PORT", "8085"))
        site = web.TCPSite(self.runner, "0.0.0.0", port)
        self.bot.loop.create_task(site.start())
        print(f"🌐 {BOT_NAME} Dashboard & API running on 0.0.0.0:{port}")

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()

async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardAPI(bot))
