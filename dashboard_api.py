import os
import json
import uuid
import aiohttp
from aiohttp import web
from discord.ext import commands
import discord

# Load credentials from environment (they were added to .env by user)
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5173/auth/callback")

# Session store: token -> dict of user data
SESSIONS = {}

# CORS Middleware to allow requests from Vite dev server (localhost:3000)
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
    """Redirects to Discord OAuth2."""
    oauth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds"
    )
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
    
    # Exchange code for token
    token_url = "https://discord.com/api/oauth2/token"
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=payload, headers=headers) as resp:
            if resp.status != 200:
                resp_text = await resp.text()
                print(f"[Dashboard API] Token exchange failed: {resp_text}")
                return web.json_response({"error": "Failed to exchange code"}, status=400)
            token_data = await resp.json()
    
    access_token = token_data.get("access_token")
    
    # Get user profile
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get("https://discord.com/api/users/@me", headers=headers) as resp:
            if resp.status != 200:
                return web.json_response({"error": "Failed to fetch user"}, status=400)
            user_data = await resp.json()

    # Generate session token
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "user_id": user_data.get("id"),
        "username": user_data.get("username"),
        "avatar": user_data.get("avatar"),
        "access_token": access_token
    }

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
        "guilds": mutual_admin_guilds
    })

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
        if platform == "youtube" and hasattr(stream_cog, "yt_notifier") and getattr(stream_cog, "yt_notifier"):
            try:
                stream_cog.yt_notifier.subscribe([creator_id])
                print(f"[DashboardAPI] ytnoti subscribed to {creator_id}")
            except Exception as e:
                print(f"[DashboardAPI] Failed to subscribe ytnoti: {e}")
                
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
        return web.json_response({"success": True})
    return web.json_response({"error": "Alert not found"}, status=404)

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
    ticket_cog = bot.get_cog("TicketCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded"}, status=500)
    cats = ticket_cog.db.get_categories(guild_id)
    log_ch = ticket_cog.db.get_log_channel(guild_id)
    cats_data = [{
        "id": c.id, "name": c.name, "button_label": c.button_label,
        "button_emoji": c.button_emoji, "ping_roles": c.ping_roles,
        "admin_roles": c.admin_roles, "embed_title": c.embed_title,
        "embed_description": c.embed_description, "ticket_counter": c.ticket_counter,
    } for c in cats]
    return web.json_response({"categories": cats_data, "log_channel_id": str(log_ch) if log_ch else None})

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
    ticket_cog = bot.get_cog("TicketCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded"}, status=500)
    cat_id = ticket_cog.db.add_category(
        guild_id=guild_id, name=name,
        button_label=data.get("button_label", name).strip(),
        button_emoji=data.get("button_emoji", "🎫").strip(),
        ping_roles="", admin_roles="",
        embed_title=data.get("embed_title", "New Ticket").strip(),
        embed_desc=data.get("embed_description", "").strip()
    )
    return web.json_response({"success": True, "id": cat_id})

async def handle_tickets_delete(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    category_id = int(request.match_info["category_id"])
    bot: commands.Bot = request.app["bot"]
    ticket_cog = bot.get_cog("TicketCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded"}, status=500)
    deleted = ticket_cog.db.delete_category(guild_id, category_id)
    if deleted:
        return web.json_response({"success": True})
    return web.json_response({"error": "Category not found"}, status=404)

async def handle_tickets_log_channel(request: web.Request):
    user_id = await get_user_id(request)
    if not user_id: return web.json_response({"error": "Unauthorized"}, status=401)
    
    guild_id = int(request.match_info["guild_id"])
    if not await check_guild_permissions(request, guild_id, user_id):
        return web.json_response({"error": "Missing permissions"}, status=403)
        
    data = await request.json()
    channel_id = data.get("channel_id")
    bot: commands.Bot = request.app["bot"]
    ticket_cog = bot.get_cog("TicketCog")
    if not ticket_cog:
        return web.json_response({"error": "Tickets module not loaded"}, status=500)
    ticket_cog.db.set_log_channel(guild_id, int(channel_id) if channel_id else None)
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

# --- Welcome Endpoints ---

async def handle_welcome_get(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    welcome_cog = bot.get_cog("WelcomeCog")
    if not welcome_cog:
        return web.json_response({"error": "Welcome module not loaded"}, status=500)
    cfg = welcome_cog.db.get_config(guild_id)
    if not cfg:
        return web.json_response({"config": None})
    return web.json_response({"config": {
        "enabled": bool(cfg.enabled),
        "channel_id": str(cfg.channel_id) if cfg.channel_id else None,
        "message": cfg.message,
    }})

async def handle_welcome_post(request: web.Request):
    session_data = _get_session(request)
    if not session_data:
        return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    bot: commands.Bot = request.app["bot"]
    welcome_cog = bot.get_cog("WelcomeCog")
    if not welcome_cog:
        return web.json_response({"error": "Welcome module not loaded"}, status=500)
    welcome_cog.db.set_config(
        guild_id=guild_id,
        channel_id=int(data["channel_id"]) if data.get("channel_id") else None,
        message=data.get("message", ""),
        enabled=data.get("enabled", True),
    )
    return web.json_response({"success": True})

class DashboardAPI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner = None

    async def cog_load(self):
        app = web.Application(middlewares=[cors_middleware])
        app["bot"] = self.bot
        
        # Add routes
        app.add_routes([
            web.get("/api/auth/discord", handle_login),
            web.get("/api/auth/callback", handle_callback_redirect),
            web.post("/api/auth/callback", handle_callback),
            web.get("/api/users/@me", handle_me),
            # Stream Alerts
            web.get("/api/guilds/{guild_id}/stream-alerts", handle_stream_alerts_get),
            web.post("/api/guilds/{guild_id}/stream-alerts", handle_stream_alerts_post),
            web.delete("/api/guilds/{guild_id}/stream-alerts/{platform}/{username}", handle_stream_alerts_delete),
            # Channels (shared)
            web.get("/api/guilds/{guild_id}/channels", handle_bot_channels),
            # Tickets
            web.get("/api/guilds/{guild_id}/tickets", handle_tickets_get),
            web.post("/api/guilds/{guild_id}/tickets", handle_tickets_post),
            web.delete("/api/guilds/{guild_id}/tickets/{category_id}", handle_tickets_delete),
            web.post("/api/guilds/{guild_id}/tickets/log-channel", handle_tickets_log_channel),
            # Welcome
            web.get("/api/guilds/{guild_id}/welcome", handle_welcome_get),
            web.post("/api/guilds/{guild_id}/welcome", handle_welcome_post),
            # Music
            web.get("/api/guilds/{guild_id}/music", handle_music_get),
            web.post("/api/guilds/{guild_id}/music/control", handle_music_control),
        ])
        
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        
        # Use port 8085 for API to avoid collisions
        port = int(os.getenv("DASHBOARD_PORT", "8085"))
        site = web.TCPSite(self.runner, "0.0.0.0", port)
        self.bot.loop.create_task(site.start())
        print(f"🌐 Dashboard API running on http://localhost:{port}")

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()

async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardAPI(bot))
