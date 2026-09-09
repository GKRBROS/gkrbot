"""
stream_alerts.py — YouTube, Twitch & Kick live/video notification system.

• All configuration is per-guild and stored in stream_alerts.sqlite3.
• Every setup command requires the "Manage Server" (manage_guild) permission.
• Background polling runs globally across ALL servers the bot is in.

Supported platforms:
  YouTube  – polls YouTube Data API v3 for latest video + live status
  Twitch   – uses Twitch Helix API (app access token) for stream status
  Kick     – unofficial Kick API endpoint (no auth required)
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import datetime
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from gkr_ui import C, embed_error, embed_success, embed_info

try:
    import ytnoti
    from ytnoti import AsyncYouTubeNotifier
    has_ytnoti = True
except ImportError:
    has_ytnoti = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "stream_alerts.sqlite3")

YOUTUBE_API_KEY    = os.getenv("YOUTUBE_API_KEY", "")
TWITCH_CLIENT_ID   = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")

YOUTUBE_SEARCH_URL  = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_CHANNEL_URL = "https://www.googleapis.com/youtube/v3/channels"
TWITCH_TOKEN_URL    = "https://id.twitch.tv/oauth2/token"
TWITCH_STREAMS_URL  = "https://api.twitch.tv/helix/streams"
TWITCH_USERS_URL    = "https://api.twitch.tv/helix/users"
KICK_CHANNEL_URL    = "https://kick.com/api/v2/channels/{}"

STREAM_POLL_SECONDS = 30  # check live every 30 seconds — very fast detection
VIDEO_POLL_MINUTES  = 10  # how often to check for new video uploads

# Require 1 consecutive live poll before firing (no extra delay, but prevents race conditions)
YOUTUBE_LIVE_CONFIRM_COUNT = 1


# ---------------------------------------------------------------------------
# Colours and emojis per platform
# ---------------------------------------------------------------------------

PLATFORM_META = {
    "youtube": {"emoji": "🎬", "color": 0xFF0000, "name": "YouTube"},
    "twitch":  {"emoji": "🟣", "color": 0x9146FF, "name": "Twitch"},
    "kick":    {"emoji": "🟢", "color": 0x53FC18, "name": "Kick"},
}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

@dataclass
class AlertConfig:
    id: int
    guild_id: int
    platform: str          # "youtube" | "twitch" | "kick"
    creator_username: str  # the channel/user handle
    creator_id: str        # resolved platform-specific ID
    notification_channel_id: int
    custom_live_message: str = ""
    custom_video_message: str = ""
    notify_live: bool = True
    notify_videos: bool = True
    last_live: bool = False          # was the creator live last check?
    last_video_id: str = ""          # ID of the last announced video
    added_by: str = ""               # user ID who added the alert


class StreamAlertsDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stream_alerts (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id                TEXT NOT NULL,
                    platform                TEXT NOT NULL,
                    creator_username        TEXT NOT NULL,
                    creator_id              TEXT NOT NULL DEFAULT '',
                    notification_channel_id TEXT NOT NULL,
                    custom_live_message     TEXT NOT NULL DEFAULT '',
                    custom_video_message    TEXT NOT NULL DEFAULT '',
                    notify_live             INTEGER NOT NULL DEFAULT 1,
                    notify_videos           INTEGER NOT NULL DEFAULT 1,
                    last_live               INTEGER NOT NULL DEFAULT 0,
                    last_video_id           TEXT NOT NULL DEFAULT '',
                    added_by                TEXT NOT NULL DEFAULT '',
                    UNIQUE(guild_id, platform, creator_username)
                )
            """)
            
            # DB Migration for existing tables
            try:
                conn.execute("ALTER TABLE stream_alerts ADD COLUMN added_by TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass
                
            conn.commit()

    def add_alert(self, guild_id: int, platform: str, creator_username: str,
                  creator_id: str, notification_channel_id: int, added_by: str = "") -> bool:
        """Add a new alert subscription. Returns True on success, False if already exists."""
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO stream_alerts
                        (guild_id, platform, creator_username, creator_id, notification_channel_id, added_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (str(guild_id), platform, creator_username.lower(), creator_id,
                      str(notification_channel_id), added_by))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_alert(self, guild_id: int, platform: str, creator_username: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("""
                DELETE FROM stream_alerts
                WHERE guild_id = ? AND platform = ? AND creator_username = ?
            """, (str(guild_id), platform, creator_username.lower()))
            conn.commit()
        return cur.rowcount > 0

    def get_alerts_for_guild(self, guild_id: int) -> list[AlertConfig]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM stream_alerts WHERE guild_id = ?", (str(guild_id),)
            ).fetchall()
        return [self._row_to_config(r) for r in rows]

    def get_all_alerts(self) -> list[AlertConfig]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM stream_alerts").fetchall()
        return [self._row_to_config(r) for r in rows]

    def update_live_state(self, alert_id: int, is_live: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE stream_alerts SET last_live = ? WHERE id = ?",
                (1 if is_live else 0, alert_id)
            )
            conn.commit()

    def reset_all_live_states(self) -> None:
        """Reset all last_live flags to 0 on startup so every restart re-detects live status."""
        with self._conn() as conn:
            conn.execute("UPDATE stream_alerts SET last_live = 0")
            conn.commit()
        print("[StreamAlerts] All live states reset for fresh detection.")

    def update_last_video(self, alert_id: int, video_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE stream_alerts SET last_video_id = ? WHERE id = ?",
                (video_id, alert_id)
            )
            conn.commit()

    def update_messages(self, alert_id: int, live_msg: str, video_msg: str) -> None:
        with self._conn() as conn:
            conn.execute("""
                UPDATE stream_alerts
                SET custom_live_message = ?, custom_video_message = ?
                WHERE id = ?
            """, (live_msg, video_msg, alert_id))
            conn.commit()

    def toggle_notify(self, alert_id: int, notify_live: bool, notify_videos: bool) -> None:
        with self._conn() as conn:
            conn.execute("""
                UPDATE stream_alerts
                SET notify_live = ?, notify_videos = ?
                WHERE id = ?
            """, (1 if notify_live else 0, 1 if notify_videos else 0, alert_id))
            conn.commit()

    def _row_to_config(self, row: sqlite3.Row) -> AlertConfig:
        return AlertConfig(
            id=row["id"],
            guild_id=int(row["guild_id"]),
            platform=row["platform"],
            creator_username=row["creator_username"],
            creator_id=row["creator_id"],
            notification_channel_id=int(row["notification_channel_id"]),
            custom_live_message=row["custom_live_message"],
            custom_video_message=row["custom_video_message"],
            notify_live=bool(row["notify_live"]),
            notify_videos=bool(row["notify_videos"]),
            last_live=bool(row["last_live"]),
            last_video_id=row["last_video_id"],
            added_by=row["added_by"],
        )


# ---------------------------------------------------------------------------
# Platform API helpers
# ---------------------------------------------------------------------------

class TwitchAuth:
    """Manages a Twitch App Access Token, auto-refreshing when needed."""

    def __init__(self):
        self._token: str = ""
        self._expires_at: float = 0.0

    async def get_token(self, session: aiohttp.ClientSession) -> str:
        import time
        if self._token and time.time() < self._expires_at - 60:
            return self._token

        data = {
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        async with session.post(TWITCH_TOKEN_URL, data=data) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Twitch token request failed: {resp.status}")
            payload = await resp.json()
        self._token = payload["access_token"]
        import time
        self._expires_at = time.time() + payload.get("expires_in", 3600)
        return self._token


_twitch_auth = TwitchAuth()


async def resolve_youtube_channel_id(session: aiohttp.ClientSession, username: str) -> Optional[str]:
    """Given a handle/@username, resolve to a YouTube channelId."""
    if not YOUTUBE_API_KEY:
        return None
    # Try handle first (@ form)
    handle = username.lstrip("@")
    params = {"part": "id", "forHandle": handle, "key": YOUTUBE_API_KEY}
    async with session.get(YOUTUBE_CHANNEL_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        if resp.status == 200:
            data = await resp.json()
            items = data.get("items", [])
            if items:
                return items[0]["id"]
    # Fallback: search by name
    params = {"part": "snippet", "q": handle, "type": "channel", "maxResults": 1, "key": YOUTUBE_API_KEY}
    async with session.get(YOUTUBE_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        if resp.status == 200:
            data = await resp.json()
            items = data.get("items", [])
            if items:
                return items[0]["snippet"]["channelId"]
    return None


async def get_youtube_latest(session: aiohttp.ClientSession, channel_id: str) -> Optional[dict]:
    """Return dict with keys: is_live, video_id, title, thumbnail, url, description, channel_title."""
    results = await get_youtube_batch(session, [channel_id])
    return results.get(channel_id)


async def _fetch_rss(session: aiohttp.ClientSession, channel_id: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Fetch the top-5 latest video IDs from a channel's RSS feed.
    Returns (channel_id, [(vid_id, title, author), ...])
    Checking top-5 ensures we catch a live stream even if RSS lags.
    """
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        async with session.get(rss_url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                text = await resp.text()
                root = ET.fromstring(text)
                ns = {'yt': 'http://www.youtube.com/xml/schemas/2015', 'ns': 'http://www.w3.org/2005/Atom'}
                author = root.find('ns:author/ns:name', ns)
                author_name = author.text if author is not None else "YouTube Creator"
                entries = root.findall('ns:entry', ns)[:5]  # top 5 recent entries
                videos = []
                for entry in entries:
                    vid_elem = entry.find('yt:videoId', ns)
                    title_elem = entry.find('ns:title', ns)
                    if vid_elem is not None:
                        videos.append((
                            vid_elem.text,
                            title_elem.text if title_elem is not None else "",
                            author_name,
                        ))
                if videos:
                    return (channel_id, videos)
    except Exception as e:
        print(f"[StreamAlerts] RSS error for {channel_id}: {e}")
    return (channel_id, [])


async def get_youtube_batch(
    session: aiohttp.ClientSession,
    channel_ids: list[str],
) -> dict[str, Optional[dict]]:
    """Fetch live/video status for multiple YouTube channels in ONE API call.

    Step 1: Fetch top-5 RSS entries concurrently for all channels (0 quota).
    Step 2: ONE batch Videos API call for all collected video IDs (1 quota point).
    Step 3: Per channel — if ANY video is live, return that. Else return the latest.
    Returns a dict mapping channel_id -> result dict (or None).
    """
    if not channel_ids:
        return {}

    # Step 1: Fetch RSS feeds concurrently — zero quota cost
    rss_tasks = [_fetch_rss(session, cid) for cid in channel_ids]
    rss_results = await asyncio.gather(*rss_tasks)

    # Build maps:
    # vid_id -> (channel_id, title, author)
    # channel_id -> [vid_ids in order]
    vid_to_meta: dict[str, tuple[str, str, str]] = {}
    channel_to_vids: dict[str, list[str]] = {}

    for channel_id, videos in rss_results:
        vids_for_channel = []
        for vid_id, title, author in videos:
            if vid_id not in vid_to_meta:  # don't overwrite if same vid appears in multiple channels
                vid_to_meta[vid_id] = (channel_id, title, author)
            vids_for_channel.append(vid_id)
        channel_to_vids[channel_id] = vids_for_channel

    results: dict[str, Optional[dict]] = {cid: None for cid in channel_ids}

    if not vid_to_meta or not YOUTUBE_API_KEY:
        return results

    # Step 2: ONE batch Videos API call for ALL collected video IDs (max 50 per call)
    # We ask for 5 per channel, so 50 channels = 250 IDs → 5 API calls, still very efficient
    all_vid_ids = list(vid_to_meta.keys())
    api_results: dict[str, dict] = {}  # vid_id -> API result dict

    for i in range(0, len(all_vid_ids), 50):
        chunk = all_vid_ids[i:i + 50]
        params = {
            "part": "snippet",
            "id": ",".join(chunk),
            "key": YOUTUBE_API_KEY,
        }
        try:
            async with session.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params=params,
                timeout=10,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("items", []):
                        vid_id = item["id"]
                        snip = item.get("snippet", {})
                        channel_id, fallback_title, fallback_author = vid_to_meta.get(vid_id, (None, "", ""))
                        if not channel_id:
                            continue
                        api_results[vid_id] = {
                            "is_live": snip.get("liveBroadcastContent") == "live",
                            "is_upcoming": snip.get("liveBroadcastContent") == "upcoming",
                            "video_id": vid_id,
                            "title": snip.get("title", fallback_title),
                            "thumbnail": snip.get("thumbnails", {}).get("high", {}).get("url", ""),
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "description": snip.get("description", ""),
                            "channel_title": snip.get("channelTitle", fallback_author),
                        }
                elif resp.status == 429:
                    print("[StreamAlerts] ⚠️ YouTube API quota exceeded!")
                    return results
                else:
                    print(f"[StreamAlerts] YouTube Videos API error: {resp.status}")
        except Exception as e:
            print(f"[StreamAlerts] Batch Videos API error: {e}")

        # Step 3: For each channel, find the best result:
        # Priority: LIVE > latest video
        for channel_id in channel_ids:
            vids = channel_to_vids.get(channel_id, [])
            if not vids:
                continue

            # First: look for any video that is currently LIVE
            live_result = None
            for vid_id in vids:
                r = api_results.get(vid_id)
                if r and r.get("is_live"):
                    live_result = r
                    break

            if live_result:
                results[channel_id] = live_result
            else:
                # Fall back to the latest (first in RSS order)
                for vid_id in vids:
                    r = api_results.get(vid_id)
                    if r and not r.get("is_upcoming"):  # skip scheduled streams
                        results[channel_id] = r
                        break

        return results



async def check_youtube_live_direct(
    session: aiohttp.ClientSession,
    channel_ids: list[str],
) -> dict[str, Optional[dict]]:
    """Directly check which channels are live using yt-dlp on the /streams page.
    This is extremely reliable and costs ZERO API quota.
    Returns dict: channel_id -> live info dict if live, else None.
    """
    if not channel_ids:
        return {}

    results: dict[str, Optional[dict]] = {cid: None for cid in channel_ids}

    # We run yt-dlp in a thread pool so it doesn't block the async event loop
    def _run_ytdlp(cid: str) -> Optional[dict]:
        import yt_dlp
        url = f"https://www.youtube.com/channel/{cid}/streams"
        cookie_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'extract_flat': True,
            'force_generic_extractor': False,
            'playlist_items': '1', # Just get the first item
            'retries': 0,
            'ignoreerrors': True,
        }
        if os.path.exists(cookie_path):
            ydl_opts['cookiefile'] = cookie_path

        class _SilentLogger:
            def debug(self, msg): pass
            def warning(self, msg): pass
            def error(self, msg): pass

        ydl_opts['logger'] = _SilentLogger()

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info or 'entries' not in info or not info['entries']:
                    return None

                entry = info['entries'][0]
                if entry and entry.get('live_status') == 'is_live':
                    vid_id = entry.get('id', '')
                    title = entry.get('title', 'YouTube Live Stream')
                    thumbnail = entry.get('thumbnail') or (f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg" if vid_id else "")

                    print(f"[StreamAlerts] 🔴 YT-DLP LIVE DETECTED: {cid} -> {title}")
                    return {
                        "is_live": True,
                        "video_id": vid_id,
                        "title": title,
                        "thumbnail": thumbnail,
                        "url": entry.get('url', f"https://www.youtube.com/watch?v={vid_id}"),
                        "description": entry.get('description', ''),
                        "channel_title": entry.get('uploader', ''),
                    }
        except Exception:
            pass
        return None

    # Run concurrently in the executor
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, _run_ytdlp, cid)
        for cid in channel_ids
    ]

    ytdlp_results = await asyncio.gather(*tasks)

    for cid, info in zip(channel_ids, ytdlp_results):
        results[cid] = info

    return results


async def resolve_twitch_user_id(session: aiohttp.ClientSession, login: str) -> Optional[str]:
    if not TWITCH_CLIENT_ID:
        return None
    token = await _twitch_auth.get_token(session)
    headers = {"Client-Id": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"}
    async with session.get(TWITCH_USERS_URL, params={"login": login}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        if resp.status == 200:
            data = await resp.json()
            users = data.get("data", [])
            if users:
                return users[0]["id"]
    return None


async def get_twitch_stream(session: aiohttp.ClientSession, user_id: str) -> Optional[dict]:
    if not TWITCH_CLIENT_ID:
        return None
    try:
        token = await _twitch_auth.get_token(session)
        headers = {"Client-Id": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"}
        async with session.get(TWITCH_STREAMS_URL, params={"user_id": user_id}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                streams = data.get("data", [])
                if streams:
                    s = streams[0]
                    import time
                    thumb = s.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720")
                    if thumb and "?" not in thumb:
                        thumb = f"{thumb}?t={int(time.time())}"

                    # Fetch creator profile avatar
                    avatar_url = ""
                    try:
                        async with session.get(TWITCH_USERS_URL, params={"id": user_id}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as u_resp:
                            if u_resp.status == 200:
                                u_data = await u_resp.json()
                                u_list = u_data.get("data", [])
                                if u_list:
                                    avatar_url = u_list[0].get("profile_image_url", "")
                    except Exception:
                        pass

                    return {
                        "is_live": True,
                        "title": s.get("title", ""),
                        "game": s.get("game_name", ""),
                        "thumbnail": thumb,
                        "avatar": avatar_url,
                        "viewer_count": s.get("viewer_count", 0),
                        "url": f"https://www.twitch.tv/{s.get('user_login', '')}",
                        "user_name": s.get("user_name", ""),
                        "user_login": s.get("user_login", ""),
                    }
    except Exception as e:
        print(f"[StreamAlerts] Twitch check error for {user_id}: {e}")
    return None


async def get_kick_stream(session: aiohttp.ClientSession, username: str) -> Optional[dict]:
    clean_user = username.strip().lstrip("@").lower()
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession(impersonate="chrome110") as c_session:
            # 1. Try v1 API first (returns live video screenshot in thumbnail)
            resp = await c_session.get(f"https://kick.com/api/v1/channels/{clean_user}", timeout=10)
            data = None
            if resp.status_code == 200:
                data = resp.json()
            else:
                # Fallback to v2 API
                resp2 = await c_session.get(f"https://kick.com/api/v2/channels/{clean_user}", timeout=10)
                if resp2.status_code == 200:
                    data = resp2.json()

            if not data:
                return None

            livestream = data.get("livestream")
            if not livestream:
                return None

            # 2. Extract live stream preview screenshot / thumbnail
            thumb_url = ""
            thumb = livestream.get("thumbnail")
            if isinstance(thumb, dict):
                thumb_url = thumb.get("url", "")
                if not thumb_url and thumb.get("responsive"):
                    # Extract the highest resolution URL from responsive string
                    parts = thumb.get("responsive", "").split(",")
                    if parts:
                        thumb_url = parts[0].strip().split(" ")[0]
            elif isinstance(thumb, str) and thumb.strip():
                thumb_url = thumb.strip()

            # Fallback to channel banner if no live screenshot yet
            if not thumb_url:
                banner = data.get("banner_image")
                if isinstance(banner, dict):
                    thumb_url = banner.get("url", "")
                elif isinstance(banner, str):
                    thumb_url = banner

            # Fallback to offline banner if available
            if not thumb_url:
                offline_banner = data.get("offline_banner_image")
                if isinstance(offline_banner, dict):
                    thumb_url = offline_banner.get("url", "")
                elif isinstance(offline_banner, str):
                    thumb_url = offline_banner

            # 3. Extract user avatar
            user_obj = data.get("user") or {}
            avatar_url = user_obj.get("profile_pic") or data.get("profile_pic") or ""

            # 4. Extract categories / game
            game_name = ""
            categories = livestream.get("categories") or []
            if categories and isinstance(categories, list) and len(categories) > 0:
                game_name = categories[0].get("name", "")

            # 5. Append cache-buster timestamp so Discord loads fresh live frame
            if thumb_url and "?" not in thumb_url:
                import time
                thumb_url = f"{thumb_url}?t={int(time.time())}"

            creator_name = data.get("name") or user_obj.get("username") or username

            return {
                "is_live": True,
                "title": livestream.get("session_title") or f"{creator_name} is live on Kick!",
                "game": game_name,
                "thumbnail": thumb_url,
                "avatar": avatar_url,
                "viewer_count": livestream.get("viewer_count", 0),
                "url": f"https://kick.com/{clean_user}",
                "user_name": creator_name,
            }
    except Exception as e:
        print(f"[StreamAlerts] Kick check error for {username}: {e}")
        return None


# ---------------------------------------------------------------------------
# Embed builders
# ---------------------------------------------------------------------------

def build_live_embed(platform: str, creator: str, info: dict) -> discord.Embed:
    color = 0xFF0000 if platform.lower() == "youtube" else PLATFORM_META.get(platform, {}).get("color", 0xFF0000)
    title_text = info.get("title", "Live Stream")

    embed = discord.Embed(
        title=title_text,
        color=color,
        url=info.get("url", ""),
    )
    
    # Author name & avatar
    author_name = str(
        info.get("channel_title") or info.get("user_name") or creator
    ).upper()
    
    stream_url = info.get("url", "")
    if info.get("avatar"):
        embed.set_author(name=author_name, icon_url=info["avatar"], url=stream_url if stream_url else None)
    else:
        embed.set_author(name=author_name, url=stream_url if stream_url else None)
        
    if info.get("game"):
        embed.add_field(name="Playing / Category", value=info["game"], inline=True)

    if info.get("viewer_count") is not None:
        embed.add_field(name="Viewers", value=str(info["viewer_count"]), inline=True)
        
    if info.get("thumbnail"):
        embed.set_image(url=info["thumbnail"])
    elif info.get("avatar"):
        embed.set_thumbnail(url=info["avatar"])
    
    meta = PLATFORM_META.get(platform, {})
    embed.set_footer(text=f"{meta.get('name', platform.title())} Live Alert")
    return embed


def build_video_embed(platform: str, creator: str, info: dict) -> discord.Embed:
    meta = PLATFORM_META.get(platform, {"emoji": "📹", "color": 0xFF0000, "name": platform.title()})
    embed = discord.Embed(
        title=f"{meta['emoji']} New Video — {info.get('channel_title', creator)}",
        description=info.get("title", ""),
        color=meta["color"],
        url=info.get("url", ""),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    if info.get("thumbnail"):
        embed.set_image(url=info["thumbnail"])
    embed.set_footer(text=f"{meta['name']} Video Alert")
    return embed


# ---------------------------------------------------------------------------
# Main Cog
# ---------------------------------------------------------------------------

class StreamAlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = StreamAlertsDatabase()
        self.db.initialize()
        self._session: Optional[aiohttp.ClientSession] = None
        # youtube_live_confirm[alert_id] = count of consecutive polls that showed live
        # We require YOUTUBE_LIVE_CONFIRM_COUNT consecutive live polls before firing the alert
        self._yt_live_confirm: dict[int, int] = {}

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession()
        self.stream_check_loop.start()
        self.video_check_loop.start()
        self.yt_notifier = None
        self._ytnoti_task: Optional[asyncio.Task] = None

        if has_ytnoti:
            cb_url = (os.getenv("YTNOTI_WEBHOOK_URL") or "").strip()
            # Only start ytnoti if an explicit, valid external webhook URL is configured
            if cb_url and cb_url.startswith(("http://", "https://")) and "localhost" not in cb_url and "127.0.0.1" not in cb_url:
                try:
                    self.yt_notifier = AsyncYouTubeNotifier(callback_url=cb_url)

                    @self.yt_notifier.upload()
                    async def on_upload(video):
                        await self._handle_ytnoti_upload(video)

                    alerts = self.db.get_all_alerts()
                    yt_channels = list({a.creator_id for a in alerts if a.platform == "youtube" and a.creator_id})
                    self._ytnoti_task = asyncio.create_task(self._start_ytnoti(yt_channels))
                except Exception as exc:
                    print(f"[StreamAlerts] ⚠️ Could not initialize ytnoti: {exc}. Using built-in YouTube polling.")
                    self.yt_notifier = None
            else:
                self.yt_notifier = None
                print("[StreamAlerts] ℹ️ YTNOTI_WEBHOOK_URL not configured. Using built-in high-efficiency YouTube API/RSS polling.")
        else:
            self.yt_notifier = None

    async def _start_ytnoti(self, initial_channels: list[str]):
        """Start AsyncYouTubeNotifier in a background task with safe error handling."""
        if not self.yt_notifier:
            return
        try:
            if initial_channels:
                print(f"[StreamAlerts] Subscribing {len(initial_channels)} channels to ytnoti...")
                await self.yt_notifier.subscribe(initial_channels)
                print(f"[StreamAlerts] ytnoti subscribed to {len(initial_channels)} channels.")
            await self.yt_notifier.run(port=8086)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[StreamAlerts] ⚠️ ytnoti startup/connection error: {e}. Falling back to standard YouTube polling.")
            self.yt_notifier = None

    async def _handle_ytnoti_upload(self, video):
        # ytnoti Video object
        # Find all alerts for this channel ID
        alerts = self.db.get_all_alerts()
        matching = [a for a in alerts if a.platform == "youtube" and a.creator_id == video.channel_id]
        if not matching: return
        
        info = {
            "title": video.title,
            "url": video.url,
            "channel_title": video.channel_name,
            "video_id": video.id,
            "is_live": False # We would ideally check if it's a live stream from the API
        }
        
        for alert in matching:
            if alert.notify_videos:
                if alert.last_video_id != video.id:
                    self.db.update_last_video(alert.id, video.id)
                    await self._send_video_alert(alert, info)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """On startup, silently sync live states WITHOUT sending notifications.
        This prevents duplicate alerts when the bot restarts while a stream is still live.
        """
        asyncio.create_task(self._sync_live_states_on_startup())

    async def _sync_live_states_on_startup(self) -> None:
        """Check all tracked streams silently and update last_live in DB.
        No alerts are sent — this only calibrates the state so the next poll
        knows which streams were ALREADY live before the bot came online.
        """
        print("[StreamAlerts] 🔄 Running startup live-state sync (no alerts will fire)...")
        await asyncio.sleep(5)  # small delay to let the session fully start
        alerts = self.db.get_all_alerts()
        live_alerts = [a for a in alerts if a.notify_live]
        if not live_alerts:
            print("[StreamAlerts] ✅ No alerts to sync on startup.")
            return

        # ── YouTube batch sync ────────────────────────────────────────────────
        yt_alerts = [a for a in live_alerts if a.platform == "youtube" and a.creator_id]
        yt_channel_ids = list({a.creator_id for a in yt_alerts})
        yt_results: dict = {}
        if yt_channel_ids:
            try:
                live_direct = await check_youtube_live_direct(self.session, yt_channel_ids)
                rss_batch = await get_youtube_batch(self.session, yt_channel_ids)
                for cid in yt_channel_ids:
                    yt_results[cid] = live_direct.get(cid) or rss_batch.get(cid)
            except Exception as exc:
                print(f"[StreamAlerts] Startup YT sync error: {exc}")

        # ── Process each alert silently ───────────────────────────────────────
        for alert in live_alerts:
            try:
                if alert.platform == "youtube":
                    data = yt_results.get(alert.creator_id)
                    is_live_now = bool(data and data.get("is_live"))
                elif alert.platform == "kick":
                    username = alert.creator_id or alert.creator_username
                    info = await get_kick_stream(self.session, username)
                    is_live_now = info is not None
                elif alert.platform == "twitch" and alert.creator_id:
                    info = await get_twitch_stream(self.session, alert.creator_id)
                    is_live_now = info is not None
                else:
                    is_live_now = False

                # Silently update last_live so the next poll won't fire a duplicate
                if is_live_now != alert.last_live:
                    self.db.update_live_state(alert.id, is_live_now)
                    status = "🔴 LIVE" if is_live_now else "⚫ offline"
                    print(f"[StreamAlerts] Startup sync: {alert.creator_username} ({alert.platform}) → {status} (no alert sent)")
                else:
                    print(f"[StreamAlerts] Startup sync: {alert.creator_username} ({alert.platform}) → state unchanged")

            except Exception as exc:
                print(f"[StreamAlerts] Startup sync error for {alert.creator_username}: {exc}")

        print("[StreamAlerts] ✅ Startup live-state sync complete.")

    async def cog_unload(self) -> None:
        self.stream_check_loop.cancel()
        self.video_check_loop.cancel()
        if self._ytnoti_task and not self._ytnoti_task.done():
            self._ytnoti_task.cancel()
        if self._session:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ── Background polling ─────────────────────────────────────────────────

    @tasks.loop(seconds=STREAM_POLL_SECONDS)
    async def stream_check_loop(self):
        """Check live status for all alerts — YouTube batched into 1 API call."""
        try:
            alerts = self.db.get_all_alerts()
        except Exception as exc:
            print(f"[StreamAlerts] DB error: {exc}")
            return

        live_alerts = [a for a in alerts if a.notify_live]
        if not live_alerts:
            return

        # ── Batch fetch all YouTube channels: DIRECT LIVE SEARCH + RSS/Videos fallback ───────
        yt_alerts = [a for a in live_alerts if a.platform == "youtube" and a.creator_id]
        yt_channel_ids = list({a.creator_id for a in yt_alerts})  # deduplicate
        yt_results: dict[str, Optional[dict]] = {}
        if yt_channel_ids:
            try:
                # Step 1: Direct live search (Search API, eventType=live) — real-time accurate
                live_direct = await check_youtube_live_direct(self.session, yt_channel_ids)
                # Step 2: RSS batch for video data (for non-live channels / video alerts)
                rss_batch = await get_youtube_batch(self.session, yt_channel_ids)
                # Merge: prefer the direct live result if channel is live, else use RSS batch result
                for cid in yt_channel_ids:
                    if live_direct.get(cid):  # channel is live right now
                        yt_results[cid] = live_direct[cid]
                    else:
                        yt_results[cid] = rss_batch.get(cid)  # not live, use RSS data
                print(f"[StreamAlerts] YouTube batch check: {len(yt_channel_ids)} channels checked (direct live search + RSS)")
            except Exception as exc:
                print(f"[StreamAlerts] YouTube batch error: {exc}")

        # ── Process each alert ────────────────────────────────────────────────
        for alert in live_alerts:
            try:
                if alert.platform == "youtube":
                    data = yt_results.get(alert.creator_id)
                    is_live_now = bool(data and data.get("is_live"))
                    was_live = alert.last_live
                    print(f"[StreamAlerts] {alert.creator_username} (youtube): is_live={is_live_now}, was_live={was_live}")

                    if is_live_now and not was_live:
                        # Double-confirm: require YOUTUBE_LIVE_CONFIRM_COUNT consecutive live polls
                        # to avoid firing alerts from YouTube's API lag when stream already ended
                        confirm = self._yt_live_confirm.get(alert.id, 0) + 1
                        self._yt_live_confirm[alert.id] = confirm
                        if confirm >= YOUTUBE_LIVE_CONFIRM_COUNT:
                            print(f"[StreamAlerts] 🔴 GOING LIVE (confirmed {confirm}x): {alert.creator_username}")
                            await self._send_live_alert(alert, data)
                            self.db.update_live_state(alert.id, True)
                            self._yt_live_confirm.pop(alert.id, None)
                        else:
                            print(f"[StreamAlerts] 🟡 YouTube live candidate ({confirm}/{YOUTUBE_LIVE_CONFIRM_COUNT}): {alert.creator_username} — waiting to confirm")
                    elif not is_live_now:
                        # Reset confirm counter — stream ended or API caught up
                        if alert.id in self._yt_live_confirm:
                            print(f"[StreamAlerts] 🔄 YouTube live confirm reset for {alert.creator_username} (was pending)")
                            self._yt_live_confirm.pop(alert.id, None)
                        if was_live:
                            print(f"[StreamAlerts] ⚫ WENT OFFLINE: {alert.creator_username}")
                        self.db.update_live_state(alert.id, False)
                else:
                    # Twitch / Kick — individual calls (their APIs don't support batch)
                    await self._check_live(alert)
                    await asyncio.sleep(0.3)
            except Exception as exc:
                print(f"[StreamAlerts] Error for {alert.creator_username}: {exc}")

    @stream_check_loop.before_loop
    async def before_stream_check(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=VIDEO_POLL_MINUTES)
    async def video_check_loop(self):
        """Check YouTube for new videos — batched into 1 API call."""
        try:
            alerts = self.db.get_all_alerts()
        except Exception as exc:
            print(f"[StreamAlerts] DB error: {exc}")
            return

        yt_alerts = [a for a in alerts if a.platform == "youtube" and a.notify_videos and a.creator_id]
        if not yt_alerts:
            return

        yt_channel_ids = list({a.creator_id for a in yt_alerts})
        try:
            yt_results = await get_youtube_batch(self.session, yt_channel_ids)
            print(f"[StreamAlerts] YouTube video batch check: {len(yt_channel_ids)} channels, 1 API call")
        except Exception as exc:
            print(f"[StreamAlerts] YouTube video batch error: {exc}")
            return

        for alert in yt_alerts:
            try:
                data = yt_results.get(alert.creator_id)
                if not data or data.get("is_live"):
                    continue  # skip if live or no data
                vid_id = data.get("video_id", "")
                if vid_id and vid_id != alert.last_video_id:
                    await self._send_video_alert(alert, data)
                    self.db.update_last_video(alert.id, vid_id)
            except Exception as exc:
                print(f"[StreamAlerts] Video check error for {alert.creator_username}: {exc}")

    @video_check_loop.before_loop
    async def before_video_check(self):
        await self.bot.wait_until_ready()

    async def _check_live(self, alert: AlertConfig) -> None:
        info = None
        if alert.platform == "twitch" and alert.creator_id:
            info = await get_twitch_stream(self.session, alert.creator_id)
        elif alert.platform == "kick":
            username = alert.creator_id or alert.creator_username
            info = await get_kick_stream(self.session, username)
        elif alert.platform == "youtube" and alert.creator_id:
            data = await get_youtube_latest(self.session, alert.creator_id)
            if data and data.get("is_live"):
                info = data

        is_live_now = info is not None
        was_live = alert.last_live

        print(f"[StreamAlerts] {alert.creator_username} ({alert.platform}): is_live={is_live_now}, was_live={was_live}")

        if is_live_now and not was_live:
            # Just went live — send notification
            print(f"[StreamAlerts] 🔴 GOING LIVE: {alert.creator_username} — sending alert to guild {alert.guild_id}")
            await self._send_live_alert(alert, info)
            self.db.update_live_state(alert.id, True)
        elif not is_live_now and was_live:
            print(f"[StreamAlerts] ⚫ WENT OFFLINE: {alert.creator_username}")
            self.db.update_live_state(alert.id, False)
        # If state hasn't changed, no update needed

    async def _check_new_video(self, alert: AlertConfig) -> None:
        if not alert.creator_id:
            return
        data = await get_youtube_latest(self.session, alert.creator_id)
        if not data or data.get("is_live"):
            return  # skip if live or no data

        vid_id = data.get("video_id", "")
        if vid_id and vid_id != alert.last_video_id:
            await self._send_video_alert(alert, data)
            self.db.update_last_video(alert.id, vid_id)

    async def _send_live_alert(self, alert: AlertConfig, info: dict) -> None:
        guild = self.bot.get_guild(alert.guild_id)
        if not guild:
            return
        channel = guild.get_channel(alert.notification_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        embed = build_live_embed(alert.platform, alert.creator_username, info)
        
        # YouTube uses channel_title; Twitch uses user_name
        author_name = str(info.get('channel_title') or info.get('user_name') or alert.creator_username).upper()
        default_msg = f"@everyone\n**{author_name}** is live!"
        content = alert.custom_live_message or default_msg
        
        view = discord.ui.View()
        stream_url = info.get("url", "")
        if stream_url:
            view.add_item(discord.ui.Button(label="Watch Stream", url=stream_url, style=discord.ButtonStyle.link))
            
        try:
            allowed = discord.AllowedMentions(everyone=True, roles=True)
            await channel.send(content=content, embed=embed, view=view, allowed_mentions=allowed)
        except Exception as exc:
            print(f"[StreamAlerts] Failed to send live alert: {exc}")

    async def _send_video_alert(self, alert: AlertConfig, info: dict) -> None:
        guild = self.bot.get_guild(alert.guild_id)
        if not guild:
            return
        channel = guild.get_channel(alert.notification_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        embed = build_video_embed(alert.platform, alert.creator_username, info)
        content = alert.custom_video_message or f"@everyone\n🎬 **{info.get('channel_title', alert.creator_username)}** just uploaded a new video!"
        
        view = discord.ui.View()
        video_url = info.get("url", "")
        if video_url:
            view.add_item(discord.ui.Button(label="Watch Video", url=video_url, style=discord.ButtonStyle.link))
            
        try:
            allowed = discord.AllowedMentions(everyone=True, roles=True)
            await channel.send(content=content, embed=embed, view=view, allowed_mentions=allowed)
        except Exception as exc:
            print(f"[StreamAlerts] Failed to send video alert: {exc}")

    # ── Slash commands ──────────────────────────────────────────────────────

    alerts_group = app_commands.Group(
        name="alerts",
        description="🔔 Manage stream & video alerts for YouTube, Twitch and Kick",
    )

    @alerts_group.command(name="add", description="Subscribe to a streamer/creator's alerts")
    @app_commands.describe(
        platform="Choose the platform",
        username="The creator's username / channel handle (e.g. @PewDiePie, xqc)",
        channel="The Discord channel where alerts will be posted",
        live="Send an alert when they go live? (default: True)",
        videos="Send an alert when they upload a video? YouTube only (default: True)",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube 🎬", value="youtube"),
        app_commands.Choice(name="Twitch 🟣", value="twitch"),
        app_commands.Choice(name="Kick 🟢", value="kick"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def add_alert(
        self,
        interaction: discord.Interaction,
        platform: str,
        username: str,
        channel: discord.TextChannel,
        live: bool = True,
        videos: bool = True,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Validate API keys
        if platform == "youtube" and not YOUTUBE_API_KEY:
            await interaction.followup.send(
                "❌ YouTube API key (`YOUTUBE_API_KEY`) is not set in the bot's `.env` file. "
                "Please add it and restart the bot.",
                ephemeral=True
            )
            return
        if platform == "twitch" and (not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET):
            await interaction.followup.send(
                embed=embed_error("Twitch credentials (`TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET`) are not set. Please add them and restart the bot."),
                ephemeral=True
            )
            return

        # Resolve creator_id
        creator_id = ""
        display_name = username.lstrip("@")

        try:
            if platform == "youtube":
                creator_id = await resolve_youtube_channel_id(self.session, username) or ""
                if not creator_id:
                    await interaction.followup.send(
                        embed=embed_error(f"Could not find a YouTube channel for `{username}`. Try using the exact channel handle (e.g. `@ChannelName`)."),
                        ephemeral=True
                    )
                    return

            elif platform == "twitch":
                creator_id = await resolve_twitch_user_id(self.session, username.lstrip("@")) or ""
                if not creator_id:
                    await interaction.followup.send(
                        embed=embed_error(f"Could not find a Twitch user for `{username}`."),
                        ephemeral=True
                    )
                    return

            elif platform == "kick":
                # Verify the channel exists
                test = await get_kick_stream(self.session, username.lstrip("@"))
                creator_id = username.lstrip("@")  # Kick has no numeric ID needed
        except Exception as exc:
            await interaction.followup.send(embed=embed_error(f"API error while resolving creator: {exc}"), ephemeral=True)
            return

        success = self.db.add_alert(
            guild_id=interaction.guild.id,
            platform=platform,
            creator_username=display_name.lower(),
            creator_id=creator_id,
            notification_channel_id=channel.id,
            added_by=str(interaction.user.id),
        )

        if not success:
            await interaction.followup.send(
                embed=embed_error(f"An alert for **{display_name}** on **{platform.title()}** already exists in this server."),
                ephemeral=True
            )
            return

        # Set toggle preferences
        alert = next(
            (a for a in self.db.get_alerts_for_guild(interaction.guild.id)
             if a.creator_username == display_name.lower() and a.platform == platform),
            None
        )
        if alert:
            self.db.toggle_notify(alert.id, live, videos)
            
        if platform == "youtube" and self.yt_notifier is not None:
            try:
                await self.yt_notifier.subscribe([creator_id])
                print(f"[StreamAlerts] ytnoti subscribed to {creator_id}")
            except Exception as e:
                print(f"[StreamAlerts] Failed to subscribe to ytnoti: {e}")

        meta = PLATFORM_META[platform]
        embed = discord.Embed(
            title=f"{meta['emoji']} Alert Added: {display_name}",
            color=meta["color"],
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Platform", value=meta["name"], inline=True)
        embed.add_field(name="Creator", value=display_name, inline=True)
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="🔴 Live Alerts", value="✅ On" if live else "❌ Off", inline=True)
        embed.add_field(name="🎬 Video Alerts", value="✅ On" if videos else "❌ Off", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @alerts_group.command(name="remove", description="Remove a streamer/creator alert")
    @app_commands.describe(
        platform="The platform",
        username="The creator's username",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube 🎬", value="youtube"),
        app_commands.Choice(name="Twitch 🟣", value="twitch"),
        app_commands.Choice(name="Kick 🟢", value="kick"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def remove_alert(
        self, interaction: discord.Interaction, platform: str, username: str
    ) -> None:
        removed = self.db.remove_alert(interaction.guild.id, platform, username.lstrip("@"))
        if removed:
            await interaction.response.send_message(
                embed=embed_success("Alert Removed", f"Removed **{platform.title()}** alerts for **{username.lstrip('@')}**."),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed_error(f"No alert found for **{username.lstrip('@')}** on **{platform.title()}**."),
                ephemeral=True
            )

    @alerts_group.command(name="list", description="Show all configured stream alerts for this server")
    @app_commands.default_permissions(manage_guild=True)
    async def list_alerts(self, interaction: discord.Interaction) -> None:
        alerts = self.db.get_alerts_for_guild(interaction.guild.id)
        if not alerts:
            await interaction.response.send_message(
                embed=embed_info("No Alerts", "No stream alerts configured yet. Use `/alerts add` to add one."),
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔔 Stream Alerts",
            description=f"All configured alerts for **{interaction.guild.name}**",
            color=C.BRAND,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        for alert in alerts:
            meta = PLATFORM_META.get(alert.platform, {"emoji": "🔔", "name": alert.platform.title()})
            channel = interaction.guild.get_channel(alert.notification_channel_id)
            chan_str = channel.mention if channel else f"<#{alert.notification_channel_id}>"
            live_str = "✅" if alert.notify_live else "❌"
            vid_str  = "✅" if alert.notify_videos else "❌"
            adder = f"<@{alert.added_by}>" if alert.added_by else "Unknown"
            embed.add_field(
                name=f"{meta['emoji']} {alert.creator_username} ({meta['name']})",
                value=f"📢 Channel: {chan_str}\n🔴 Live: {live_str}  🎬 Videos: {vid_str}\n👤 Added By: {adder}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @alerts_group.command(name="message", description="Set a custom notification message for a creator")
    @app_commands.describe(
        platform="The platform",
        username="The creator's username",
        live_message="Message sent when they go LIVE (leave blank to reset to default)",
        video_message="Message sent when a new VIDEO is posted (leave blank to reset)",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube 🎬", value="youtube"),
        app_commands.Choice(name="Twitch 🟣", value="twitch"),
        app_commands.Choice(name="Kick 🟢", value="kick"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def set_message(
        self,
        interaction: discord.Interaction,
        platform: str,
        username: str,
        live_message: str = "",
        video_message: str = "",
    ) -> None:
        alerts = self.db.get_alerts_for_guild(interaction.guild.id)
        alert = next(
            (a for a in alerts if a.platform == platform and a.creator_username == username.lstrip("@").lower()),
            None
        )
        if not alert:
            await interaction.response.send_message(
                embed=embed_error(f"No alert found for **{username}** on **{platform.title()}**."),
                ephemeral=True
            )
            return

        self.db.update_messages(alert.id, live_message, video_message)
        await interaction.response.send_message(
            embed=embed_success("Messages Updated", f"Custom messages updated for **{username}** on **{platform.title()}**."),
            ephemeral=True
        )

    @alerts_group.command(name="toggle", description="Turn live or video notifications on/off for a creator")
    @app_commands.describe(
        platform="The platform",
        username="The creator's username",
        live="Enable live stream alerts?",
        videos="Enable new video alerts? (YouTube only)",
    )
    @app_commands.choices(platform=[
        app_commands.Choice(name="YouTube 🎬", value="youtube"),
        app_commands.Choice(name="Twitch 🟣", value="twitch"),
        app_commands.Choice(name="Kick 🟢", value="kick"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def toggle_alert(
        self,
        interaction: discord.Interaction,
        platform: str,
        username: str,
        live: bool,
        videos: bool,
    ) -> None:
        alerts = self.db.get_alerts_for_guild(interaction.guild.id)
        alert = next(
            (a for a in alerts if a.platform == platform and a.creator_username == username.lstrip("@").lower()),
            None
        )
        if not alert:
            await interaction.response.send_message(
                embed=embed_error(f"No alert found for **{username}** on **{platform.title()}**."),
                ephemeral=True
            )
            return

        self.db.toggle_notify(alert.id, live, videos)
        await interaction.response.send_message(
            embed=embed_success(
                "Alerts Toggled",
                f"Updated **{username}** ({platform.title()}): \n"
                f"Live={'✅' if live else '❌'}  Videos={'✅' if videos else '❌'}"
            ),
            ephemeral=True
        )

    @alerts_group.command(name="test", description="Send a test alert to verify your configuration")
    @app_commands.describe(
        platform="The platform",
        username="The creator's username",
        type="Which alert type to test",
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="YouTube 🎬", value="youtube"),
            app_commands.Choice(name="Twitch 🟣", value="twitch"),
            app_commands.Choice(name="Kick 🟢", value="kick"),
        ],
        type=[
            app_commands.Choice(name="Live 🔴", value="live"),
            app_commands.Choice(name="Video 🎬", value="video"),
        ],
    )
    @app_commands.default_permissions(manage_guild=True)
    async def test_alert(
        self,
        interaction: discord.Interaction,
        platform: str,
        username: str,
        type: str = "live",
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        alerts = self.db.get_alerts_for_guild(interaction.guild.id)
        alert = next(
            (a for a in alerts if a.platform == platform and a.creator_username == username.lstrip("@").lower()),
            None
        )
        if not alert:
            await interaction.followup.send(
                embed=embed_error(f"No alert found for **{username}** on **{platform.title()}**. Add it first with `/alerts add`."),
                ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(alert.notification_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(embed=embed_error("Notification channel not found."), ephemeral=True)
            return

        meta = PLATFORM_META[platform]
        if type == "live":
            fake_info = {
                "is_live": True,
                "title": "🧪 This is a test stream title!",
                "game": "Test Game",
                "thumbnail": "",
                "viewer_count": 1234,
                "url": f"https://{'youtube.com' if platform=='youtube' else platform+'.com'}/{username.lstrip('@')}",
                "user_name": username.lstrip("@"),
                "channel_title": username.lstrip("@"),
                "description": "",
            }
            embed = build_live_embed(platform, username, fake_info)
            content = alert.custom_live_message or f"🔴 **{username.lstrip('@')}** is now live!"
        else:
            fake_info = {
                "is_live": False,
                "title": "🧪 This is a test video title!",
                "thumbnail": "",
                "url": f"https://youtube.com/@{username.lstrip('@')}",
                "channel_title": username.lstrip("@"),
                "description": "",
            }
            embed = build_video_embed(platform, username, fake_info)
            content = alert.custom_video_message or f"🎬 **{username.lstrip('@')}** just uploaded a new video!"

        embed.set_footer(text=f"{meta['name']} • TEST ALERT")
        try:
            if type == "live":
                view = discord.ui.View()
                view.add_item(discord.ui.Button(label="Watch Stream", url=fake_info["url"]))
                await channel.send(content=f"[TEST] {content}", embed=embed, view=view)
            else:
                await channel.send(content=f"[TEST] {content}", embed=embed)
            await interaction.followup.send(embed=embed_success("Test Sent", f"Test alert sent to {channel.mention}!"), ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=embed_error(f"Failed to send test: {exc}"), ephemeral=True)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    cog = StreamAlertsCog(bot)
    await bot.add_cog(cog)
    # NOTE: alerts_group is registered automatically when the cog is added.
    # Do NOT call bot.tree.add_command(cog.alerts_group) — that causes a duplicate error.
    print("🔔 Stream Alerts system loaded!")
