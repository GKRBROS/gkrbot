"""
music.py — GKR Bot High-Fidelity Music System.
Direct FFmpeg + yt-dlp playback engine with original GKR UI theme,
combined visualizer GIF, 3-row interactive control panel, audio filters,
lyrics, and multi-install slash command profile support.
"""

import asyncio
import io
import json
import logging
import os
import random
import re
from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Tuple
from urllib.parse import urlparse

import aiohttp
import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from bot_config import BOT_NAME
from gkr_ui import C, embed_error, embed_success, embed_info
from voice_handoff import yield_voice_to, restore_voice_from

load_dotenv()
log = logging.getLogger("gkr-music")

MAX_QUEUE = 100
MAX_SEARCH_RESULTS = 5
SPOTIFY_METADATA_API = os.getenv("SPOTIFY_METADATA_API", "").strip().rstrip("/")

COMBINED_VISUALIZER_GIF_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "combined_music_visualizer.gif")
MUSIC_VISUALIZER_GIF_FILENAME = "combined_music_visualizer.gif"
MUSIC_VISUALIZER_GIF_URL = os.getenv(
    "MUSIC_VISUALIZER_GIF_URL",
    "https://media.discordapp.net/attachments/1247646566794133585/1557275890897915964/combined_music_visualizer.gif?backend=b2&ex=6ada5371&is=6ad901f1&hm=768e324311ee1f887245027da04b41a6903fb6d0a4a8dcd463ef3aa527daae3a&="
)

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "format_sort": ["abr", "asr", "ext"],
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "skip_download": True,
    "source_address": "0.0.0.0",
    "extractor_retries": 2,
    "socket_timeout": 15,
}

# Before-options: reconnect flags for stream URLs; -ss for seek is appended dynamically
FFMPEG_BEFORE_OPTIONS = (
    "-nostdin -hide_banner -loglevel warning"
    " -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    " -reconnect_on_network_error 1"
    " -probesize 512K -analyzeduration 0"
)
# Audio-only output; do NOT add -ar/-ac here — discord.py (FFmpegPCMAudio) adds them internally
FFMPEG_AUDIO_OPTIONS = "-vn -sn -dn"

FILTERS = {
    "Normal": None,
    "Bassboost": "bass=g=6",
    "Nightcore": "asetrate=48000*1.15,aresample=48000,atempo=1.0",
    "Vaporwave": "asetrate=48000*0.85,aresample=48000,atempo=1.0",
    "8D Audio": "apulsator=hz=0.08",
}


def get_visualizer_file() -> Optional[discord.File]:
    if os.path.isfile(COMBINED_VISUALIZER_GIF_PATH):
        try:
            return discord.File(COMBINED_VISUALIZER_GIF_PATH, filename=MUSIC_VISUALIZER_GIF_FILENAME)
        except Exception:
            pass
    return None


def format_ms(ms: int) -> str:
    if not ms or ms < 0:
        return "0:00"
    seconds = int(ms) // 1000 if ms > 3600 else int(ms)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def build_progress_bar(position_sec: int, duration_sec: int, length: int = 15) -> str:
    if not duration_sec or duration_sec <= 0:
        return ""
    ratio = max(0.0, min(1.0, position_sec / duration_sec))
    filled = int(round(ratio * length))
    filled = max(0, min(length, filled))
    bar = "▬" * filled + "🔘" + "▬" * (length - filled)
    return f"`{bar}`  {format_ms(position_sec)} / {format_ms(duration_sec)}"


@dataclass
class Track:
    title: str
    webpage_url: str
    stream_url: str
    requester_id: int
    requester_name: str
    duration: int = 0
    artist: str = ""
    thumbnail: str = ""
    resolved_at: float = 0.0  # epoch seconds when stream_url was resolved

_STREAM_URL_TTL = 4 * 3600  # refresh only if >4h old


def is_url(text: str) -> bool:
    parsed = urlparse(text.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def extract_info_sync(query: str, search_count: int = 1):
    opts = dict(YTDL_OPTIONS)
    if not is_url(query):
        opts["default_search"] = f"ytsearch{search_count}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query if is_url(query) else f"ytsearch{search_count}:{query}", download=False)
    if info and "entries" in info:
        info["entries"] = [e for e in info["entries"] if e]
    return info


def parse_spotify_url(query: str):
    try:
        parsed = urlparse(query.strip())
        if parsed.netloc.lower() not in {"open.spotify.com", "www.open.spotify.com"}:
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"track", "album", "playlist"}:
            return parts[0], parts[1].split("?")[0]
    except Exception:
        pass
    return None


async def spotify_metadata(query: str):
    parsed = parse_spotify_url(query)
    if not parsed or not SPOTIFY_METADATA_API:
        return None

    kind, _ = parsed
    endpoint = {"track": "/api/track", "album": "/api/album", "playlist": "/api/playlist"}[kind]
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{SPOTIFY_METADATA_API}{endpoint}", params={"url": query}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except Exception:
        return None

    def normalise_track(item):
        if not isinstance(item, dict):
            return None
        item = item.get("track") or item.get("item") or item
        if not isinstance(item, dict):
            return None
        title = item.get("title") or item.get("name")
        artists = item.get("artists") or item.get("artist") or item.get("author") or ""
        if isinstance(artists, list):
            artists = ", ".join((a.get("name", "") if isinstance(a, dict) else str(a)) for a in artists).strip(", ")
        spotify_url = item.get("uri") or item.get("url") or item.get("external_urls", {}).get("spotify") or query
        if not title:
            return None
        return {"title": str(title), "artist": str(artists), "spotify_url": spotify_url}

    if kind == "track":
        track = normalise_track(data)
        return [track] if track else []

    raw_tracks = data.get("tracks", []) if isinstance(data, dict) else []
    return [t for t in (normalise_track(raw) for raw in raw_tracks[:MAX_QUEUE]) if t]


async def resolve_tracks(query: str, requester_id: int, requester_name: str, count: int = 1) -> List[Track]:
    spotify = parse_spotify_url(query)
    if spotify:
        metadata = await spotify_metadata(query)
        if metadata:
            wanted = metadata[:1] if spotify[0] == "track" else metadata[:MAX_QUEUE]
            resolved: List[Track] = []
            for meta in wanted:
                title = (meta.get("title") or "").strip()
                artist = (meta.get("artist") or "").strip()
                if not title:
                    continue
                try:
                    info = await asyncio.to_thread(extract_info_sync, f"{title} {artist}".strip(), 1)
                    entries = (info or {}).get("entries") or ([info] if info else [])
                    item = next((e for e in entries if e and e.get("url")), None)
                    if item:
                        thumb = meta.get("thumbnail") or item.get("thumbnail")
                        if not thumb and item.get("thumbnails"):
                            thumb = item["thumbnails"][-1].get("url")
                        if not thumb and item.get("id"):
                            thumb = f"https://i.ytimg.com/vi/{item['id']}/hqdefault.jpg"
                        resolved.append(Track(
                            title=title[:250],
                            webpage_url=meta.get("spotify_url") or query,
                            stream_url=item.get("url"),
                            requester_id=requester_id,
                            requester_name=requester_name,
                            duration=int(item.get("duration") or 0),
                            artist=artist or item.get("artist") or item.get("uploader") or "",
                            thumbnail=thumb or "",
                            resolved_at=__import__('time').time(),
                        ))
                except Exception:
                    pass
            if resolved:
                return resolved

    info = await asyncio.to_thread(extract_info_sync, query, count)
    if not info:
        return []
    entries = info.get("entries") or [info]
    tracks: List[Track] = []
    for item in entries[:count]:
        if not item or not item.get("url"):
            continue
        thumb = item.get("thumbnail")
        if not thumb and item.get("thumbnails"):
            thumb = item["thumbnails"][-1].get("url")
        if not thumb and item.get("id"):
            thumb = f"https://i.ytimg.com/vi/{item['id']}/hqdefault.jpg"
        tracks.append(Track(
            title=(item.get("title") or "Unknown title")[:250],
            webpage_url=item.get("webpage_url") or item.get("original_url") or query,
            stream_url=item["url"],
            requester_id=requester_id,
            requester_name=requester_name,
            duration=int(item.get("duration") or 0),
            artist=item.get("artist") or item.get("uploader") or "",
            thumbnail=thumb or "",
            resolved_at=__import__('time').time(),
        ))
    return tracks


async def refresh_track(track: Track) -> Track:
    """Re-resolve the stream URL only if it is stale (>4 h old)."""
    import time as _time
    if track.resolved_at and (_time.time() - track.resolved_at) < _STREAM_URL_TTL:
        return track  # still fresh — skip expensive yt-dlp call
    results = await resolve_tracks(track.webpage_url, track.requester_id, track.requester_name, 1)
    if not results:
        raise RuntimeError("Could not refresh stream URL.")
    return results[0]


# ─────────────────────────────────────────────────────────────────────────────
# Audio Filter Select UI View
# ─────────────────────────────────────────────────────────────────────────────

class AudioFilterSelect(discord.ui.Select):
    def __init__(self, current_filter: str):
        options = [
            discord.SelectOption(label="Normal (Off)", value="Normal", emoji="📻", description="Original balanced audio output", default=(current_filter == "Normal")),
            discord.SelectOption(label="Bass Boost", value="Bassboost", emoji="🔊", description="Enhanced low frequencies", default=(current_filter == "Bassboost")),
            discord.SelectOption(label="Nightcore", value="Nightcore", emoji="⚡", description="High pitch with faster tempo", default=(current_filter == "Nightcore")),
            discord.SelectOption(label="Vaporwave", value="Vaporwave", emoji="🌊", description="Slowed reverb atmosphere", default=(current_filter == "Vaporwave")),
            discord.SelectOption(label="8D Audio", value="8D Audio", emoji="🎧", description="Rotating spatial surround sound", default=(current_filter == "8D Audio")),
        ]
        super().__init__(placeholder="Select audio filter preset...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog: MusicCog = interaction.client.get_cog("MusicCog")
        if not cog:
            return
        player = cog.get_player(interaction.guild_id)
        selected = self.values[0]
        player.current_filter = selected
        restarted = player.apply_filter_to_current()
        await player.update_panel()
        msg = f"Audio filter set to **{selected}**."
        if restarted:
            msg += " Track restarted with filter applied."
        await interaction.followup.send(embed=embed_success("Filter Updated", msg), ephemeral=True)


class AudioFilterView(discord.ui.View):
    def __init__(self, current_filter: str):
        super().__init__(timeout=60)
        self.add_item(AudioFilterSelect(current_filter))


# ─────────────────────────────────────────────────────────────────────────────
# Original GKR MusicControlView (3-Row Layout)
# ─────────────────────────────────────────────────────────────────────────────

class PlaybackActionSelect(discord.ui.Select):
    def __init__(self, player: "GuildPlayer"):
        self.player = player
        options = [
            discord.SelectOption(label="Pause / Resume", value="playpause", emoji="⏯️", description="Toggle audio playback"),
            discord.SelectOption(label="Skip Track", value="skip", emoji="⏭️", description="Skip to the next song in queue"),
            discord.SelectOption(label="Previous Track", value="prev", emoji="⏮️", description="Replay previous track from history"),
            discord.SelectOption(label="Forward 10s", value="forward", emoji="⏩", description="Jump forward 10 seconds"),
            discord.SelectOption(label="Rewind 10s", value="rewind", emoji="⏪", description="Jump backward 10 seconds"),
            discord.SelectOption(label="Volume Up (+10%)", value="vol_up", emoji="🔊", description="Increase playback volume"),
            discord.SelectOption(label="Volume Down (-10%)", value="vol_down", emoji="🔉", description="Decrease playback volume"),
            discord.SelectOption(label="Shuffle Queue", value="shuffle", emoji="🔀", description="Randomize upcoming songs"),
            discord.SelectOption(label="Toggle Loop Mode", value="loop", emoji="🔁", description="Switch between Off / Single / Queue"),
            discord.SelectOption(label="Save to Favorites (DM)", value="fav", emoji="❤️", description="Send track details to your DMs"),
            discord.SelectOption(label="Stop & Disconnect", value="stop", emoji="⏹️", description="Stop music and leave voice channel"),
        ]
        super().__init__(placeholder="🎛️ Playback Controls...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if not await self.player.check_voice_interact(interaction):
            return
        action = self.values[0]

        if action == "playpause":
            vc = self.player.voice
            if not vc:
                return await interaction.response.send_message(embed=embed_error("Nothing playing."), ephemeral=True)
            if vc.is_paused():
                vc.resume()
            elif vc.is_playing():
                vc.pause()
            await interaction.response.defer()
            await self.player.update_panel()

        elif action == "skip":
            if not self.player.current and not self.player.queue:
                return await interaction.response.send_message(embed=embed_error("Nothing to skip."), ephemeral=True)
            self.player.skip()
            await interaction.response.defer()
            await self.player.update_panel()

        elif action == "prev":
            if not self.player.history:
                return await interaction.response.send_message(embed=embed_error("No previous track in history."), ephemeral=True)
            prev_track = self.player.history.pop()
            if self.player.current:
                self.player.queue.appendleft(self.player.current)
            self.player.queue.appendleft(prev_track)
            self.player.skip()
            await interaction.response.defer()
            await self.player.update_panel()

        elif action == "forward":
            if not self.player.current or not self.player.voice or not self.player.voice.is_playing():
                return await interaction.response.send_message(embed=embed_error("Nothing is playing."), ephemeral=True)
            self.player.playback_position = min(self.player.current.duration, self.player.playback_position + 10)
            self.player.restart_current_at_position(self.player.playback_position)
            await interaction.response.defer()
            await self.player.update_panel()

        elif action == "rewind":
            if not self.player.current or not self.player.voice or not self.player.voice.is_playing():
                return await interaction.response.send_message(embed=embed_error("Nothing is playing."), ephemeral=True)
            self.player.playback_position = max(0, self.player.playback_position - 10)
            self.player.restart_current_at_position(self.player.playback_position)
            await interaction.response.defer()
            await self.player.update_panel()

        elif action == "vol_up":
            self.player.volume = min(150, self.player.volume + 10)
            if self.player.voice and self.player.voice.source and isinstance(self.player.voice.source, discord.PCMVolumeTransformer):
                self.player.voice.source.volume = self.player.volume / 100.0
            await interaction.response.defer()
            await self.player.update_panel()

        elif action == "vol_down":
            self.player.volume = max(0, self.player.volume - 10)
            if self.player.voice and self.player.voice.source and isinstance(self.player.voice.source, discord.PCMVolumeTransformer):
                self.player.voice.source.volume = self.player.volume / 100.0
            await interaction.response.defer()
            await self.player.update_panel()

        elif action == "shuffle":
            if len(self.player.queue) < 2:
                return await interaction.response.send_message(embed=embed_info("Queue", "Need at least 2 songs in queue to shuffle."), ephemeral=True)
            items = list(self.player.queue)
            random.shuffle(items)
            self.player.queue.clear()
            self.player.queue.extend(items)
            await interaction.response.defer()
            await self.player.update_panel()
            await interaction.followup.send(embed=embed_success("Queue Shuffled", "Randomized queue order! 🔀"), ephemeral=True)

        elif action == "loop":
            modes = [None, "single", "queue"]
            cur = self.player.loop_mode
            self.player.loop_mode = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "single"
            await interaction.response.defer()
            await self.player.update_panel()

        elif action == "fav":
            track = self.player.current
            if not track:
                return await interaction.response.send_message(embed=embed_error("No track currently playing."), ephemeral=True)
            try:
                fav_embed = discord.Embed(
                    title="❤️ Saved to Favorites",
                    description=f"**[{track.title}]({track.webpage_url})**\n👤 **Artist:** `{track.artist or 'Unknown'}`\n⏱️ **Duration:** `{format_ms(track.duration)}`",
                    color=0xE74C3C
                )
                if track.thumbnail:
                    fav_embed.set_thumbnail(url=track.thumbnail)
                fav_embed.set_footer(text=f"Saved from {interaction.guild.name} • {BOT_NAME} Music")
                await interaction.user.send(embed=fav_embed)
                await interaction.response.send_message(embed=embed_success("Saved!", f"Sent **{track.title}** to your DMs! ❤️"), ephemeral=True)
            except Exception:
                await interaction.response.send_message(embed=embed_success("Liked", f"Liked **{track.title}**!"), ephemeral=True)

        elif action == "stop":
            self.player.stop(clear=True)
            if self.player.voice and self.player.voice.is_connected():
                guild = self.player.voice.guild
                await self.player.voice.disconnect(force=True)
                restore_voice_from(interaction.client, guild, "music")
            self.player.voice = None
            await interaction.response.defer()
            await self.player.update_panel()
            await interaction.followup.send(embed=embed_success("Stopped", "Music stopped and disconnected."), ephemeral=True)


class FilterActionSelect(discord.ui.Select):
    def __init__(self, player: "GuildPlayer"):
        self.player = player
        options = [
            discord.SelectOption(label="Normal (Off)", value="Normal", emoji="📻", description="Original balanced audio output", default=(player.current_filter == "Normal")),
            discord.SelectOption(label="Bass Boost", value="Bassboost", emoji="🔊", description="Enhanced low-end punch", default=(player.current_filter == "Bassboost")),
            discord.SelectOption(label="Nightcore", value="Nightcore", emoji="⚡", description="High pitch with faster tempo", default=(player.current_filter == "Nightcore")),
            discord.SelectOption(label="Vaporwave", value="Vaporwave", emoji="🌊", description="Slowed reverb atmosphere", default=(player.current_filter == "Vaporwave")),
            discord.SelectOption(label="8D Audio", value="8D Audio", emoji="🎧", description="Rotating spatial surround sound", default=(player.current_filter == "8D Audio")),
        ]
        super().__init__(placeholder="🎚️ Audio Filter Presets...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        if not await self.player.check_voice_interact(interaction):
            return
        selected = self.values[0]
        self.player.current_filter = selected
        restarted = self.player.apply_filter_to_current()
        await interaction.response.defer()
        await self.player.update_panel()
        msg = f"Audio filter set to **{selected}**."
        if restarted:
            msg += " Current track restarted with filter applied."
        await interaction.followup.send(embed=embed_success("Filter Updated", msg), ephemeral=True)


class ToolsActionSelect(discord.ui.Select):
    def __init__(self, player: "GuildPlayer"):
        self.player = player
        options = [
            discord.SelectOption(label="Show Music Queue", value="queue", emoji="📜", description="Display upcoming track list"),
            discord.SelectOption(label="View Lyrics", value="lyrics", emoji="🎙️", description="Fetch song lyrics from LRCLIB"),
            discord.SelectOption(label="Toggle 24/7 Mode", value="247", emoji="⚡", description="Keep bot in voice channel forever"),
            discord.SelectOption(label="Clear Upcoming Queue", value="clear", emoji="🗑️", description="Remove all queued tracks"),
        ]
        super().__init__(placeholder="⚙️ Queue & Utilities...", min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]

        if action == "queue":
            if not self.player.current and not self.player.queue:
                return await interaction.response.send_message(embed=embed_info("Queue", "The queue is currently empty."), ephemeral=True)
            lines = []
            if self.player.current:
                lines.append(f"**Now Playing:** `{self.player.current.title}` ({format_ms(self.player.current.duration)})")
            if self.player.queue:
                lines.append("\n**Up Next:**")
                for i, t in enumerate(list(self.player.queue)[:10], 1):
                    lines.append(f"`{i}.` **{t.title}** ({format_ms(t.duration)})")
                if len(self.player.queue) > 10:
                    lines.append(f"\n*...and {len(self.player.queue) - 10} more tracks in queue*")
            q_embed = discord.Embed(
                title=f"📜 Music Queue — {interaction.guild.name}",
                description="\n".join(lines),
                color=C.BRAND
            )
            total_tracks = len(self.player.queue) + (1 if self.player.current else 0)
            q_embed.set_footer(text=f"Total: {total_tracks} songs")
            return await interaction.response.send_message(embed=q_embed, ephemeral=True)

        if action == "lyrics":
            track = self.player.current
            if not track:
                return await interaction.response.send_message(embed=embed_error("Nothing is currently playing."), ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://lrclib.net/api/search", params={"q": f"{track.title} {track.artist}"}) as resp:
                        if resp.status == 200:
                            results = await resp.json()
                            if results:
                                item = results[0]
                                lyrics_text = item.get("plainLyrics") or "*No plain lyrics found.*"
                                lyrics_embed = discord.Embed(
                                    title=f"🎤 Lyrics — {track.title}",
                                    description=lyrics_text[:3900],
                                    color=C.BRAND
                                )
                                lyrics_embed.set_footer(text=f"Artist: {track.artist or 'Unknown'}")
                                return await interaction.followup.send(embed=lyrics_embed, ephemeral=True)
                await interaction.followup.send(embed=embed_info("Lyrics", f"No lyrics found for **{track.title}**."), ephemeral=True)
            except Exception as e:
                await interaction.followup.send(embed=embed_error(f"Lyrics lookup failed: {e}"), ephemeral=True)
            return

        if action == "247":
            if not await self.player.check_voice_interact(interaction):
                return
            self.player.mode_247 = not self.player.mode_247
            status = "enabled" if self.player.mode_247 else "disabled"
            await interaction.response.defer()
            await self.player.update_panel()
            return await interaction.followup.send(embed=embed_info("24/7 Mode", f"24/7 playback **{status}**! ⚡"), ephemeral=True)

        if action == "clear":
            if not await self.player.check_voice_interact(interaction):
                return
            self.player.queue.clear()
            await interaction.response.defer()
            await self.player.update_panel()
            return await interaction.followup.send(embed=embed_success("Queue Cleared", "Upcoming queue was cleared."), ephemeral=True)


TOPGG_VOTE_URL = "https://top.gg/bot/1397848684061790301/vote"


class MusicControlView(discord.ui.View):
    def __init__(self, player: "GuildPlayer"):
        super().__init__(timeout=None)
        self.player = player
        self.add_item(PlaybackActionSelect(player))
        self.add_item(FilterActionSelect(player))
        self.add_item(ToolsActionSelect(player))
        self.add_item(discord.ui.Button(
            label="Vote on Top.gg",
            emoji="❤️",
            style=discord.ButtonStyle.link,
            url=TOPGG_VOTE_URL,
            row=3,
        ))


# ─────────────────────────────────────────────────────────────────────────────
# Guild Player Logic
# ─────────────────────────────────────────────────────────────────────────────

class GuildPlayer:
    def __init__(self, cog: "MusicCog", guild_id: int):
        self.cog = cog
        self.bot = cog.bot
        self.guild_id = guild_id
        self.queue = deque()
        self.history: List[Track] = []
        self.current: Optional[Track] = None
        self.panel_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.voice: Optional[discord.VoiceClient] = None
        self.volume: int = 80
        self.current_filter: str = "Normal"
        self.loop_mode: Optional[str] = None  # None, "single", "queue"
        self.mode_247: bool = False
        self.playback_position: int = 0
        self.lock = asyncio.Lock()
        self.finished = asyncio.Event()
        self.task = asyncio.create_task(self._run())
        self.ticker_task: Optional[asyncio.Task] = None

    async def check_voice_interact(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(embed=embed_error("Join a voice channel first."), ephemeral=True)
            return False
        if not self.voice or not self.voice.is_connected():
            await interaction.response.send_message(embed=embed_error("Bot is not connected to voice."), ephemeral=True)
            return False
        if interaction.user.voice.channel != self.voice.channel:
            try:
                await self.voice.move_to(interaction.user.voice.channel)
            except Exception as e:
                await interaction.response.send_message(embed=embed_error(f"Could not move to channel: {e}"), ephemeral=True)
                return False
        return True

    def build_embed(self) -> Tuple[discord.Embed, Optional[discord.File]]:
        embed = discord.Embed(color=C.BRAND)
        bot_avatar = None
        guild = self.bot.get_guild(self.guild_id)
        if guild and guild.me and guild.me.display_avatar:
            bot_avatar = guild.me.display_avatar.url
        embed.set_author(name=f"{BOT_NAME.upper()} MUSIC PLAYER", icon_url=bot_avatar)

        track = self.current
        vc = self.voice
        is_active = bool(vc and (vc.is_playing() or vc.is_paused()) and track)

        if not is_active:
            desc = (
                "**No track currently playing.**\n\n"
                "Use `/play <song or link>` to start streaming!"
            )
            embed.description = desc
            embed.set_footer(text=f"Queue: 0 tracks · {BOT_NAME} Studio Audio")
            if MUSIC_VISUALIZER_GIF_URL:
                embed.set_image(url=MUSIC_VISUALIZER_GIF_URL)
            return embed, None

        loop_str = {"single": "🔂 Single", "queue": "🔁 Queue"}.get(self.loop_mode, "Off")
        status_badge = "⏸️ **Paused**" if vc.is_paused() else "🟢 **Playing**"
        progress = build_progress_bar(self.playback_position, track.duration)

        desc = (
            f"## [{track.title}]({track.webpage_url})\n"
            f"*by* **{track.artist or 'Unknown Artist'}**\n\n"
            + (f"{progress}\n\n" if progress else "")
            + f"🔊 `{self.volume}%`  ·  🎛️ `{self.current_filter}`  ·  🔁 `{loop_str}`  ·  ⚡ `{'24/7 ON' if self.mode_247 else '24/7 OFF'}`\n\n"
            f"🎧 Requested by **{track.requester_name}**  ·  {status_badge}"
        )
        embed.description = desc

        thumb = track.thumbnail or ""
        if not thumb and track.webpage_url:
            parsed = urlparse(track.webpage_url)
            vid = None
            if parsed.netloc.endswith("youtu.be"):
                vid = parsed.path.strip("/").split("/")[0]
            elif "v=" in parsed.query:
                import urllib.parse
                qs = urllib.parse.parse_qs(parsed.query)
                if "v" in qs and qs["v"]:
                    vid = qs["v"][0]
            if vid:
                thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        if thumb:
            embed.set_thumbnail(url=thumb)

        if MUSIC_VISUALIZER_GIF_URL:
            embed.set_image(url=MUSIC_VISUALIZER_GIF_URL)

        embed.set_footer(text=f"Queue · {len(self.queue)} tracks   |   Source · {BOT_NAME} Studio Audio")
        return embed, None

    async def update_panel(self):
        msg = self.panel_message
        if not msg:
            return
        embed, _ = self.build_embed()
        view = MusicControlView(self)
        try:
            await msg.edit(embed=embed, view=view)
        except (discord.NotFound, discord.HTTPException):
            # Stale message — post a fresh panel in the same channel
            try:
                new_msg = await msg.channel.send(embed=embed, view=view)
                self.panel_message = new_msg
            except Exception:
                self.panel_message = None
        except Exception:
            pass

    async def enqueue(self, tracks: List[Track]):
        async with self.lock:
            if len(self.queue) + (1 if self.current else 0) + len(tracks) > MAX_QUEUE:
                raise ValueError(f"Queue limit is {MAX_QUEUE} tracks.")
            self.queue.extend(tracks)
        self.finished.set()

    def restart_current_at_position(self, pos_sec: int):
        if not self.current or not self.voice or not self.voice.is_connected():
            return
        self.playback_position = pos_sec
        options = {"before_options": f"{FFMPEG_BEFORE_OPTIONS} -ss {pos_sec}", "options": FFMPEG_AUDIO_OPTIONS}
        af = FILTERS.get(self.current_filter)
        if af:
            options["options"] += f' -af "{af}"'
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(self.current.stream_url, **options),
            volume=self.volume / 100.0
        )
        if self.voice.is_playing() or self.voice.is_paused():
            self.voice.stop()
        self.voice.play(source)

    def apply_filter_to_current(self) -> bool:
        if not self.current or not self.voice or not self.voice.is_connected():
            return False
        if self.voice.is_playing() or self.voice.is_paused():
            self.restart_current_at_position(self.playback_position)
            return True
        return False

    def skip(self):
        if self.voice and (self.voice.is_playing() or self.voice.is_paused()):
            self.voice.stop()
        elif self.queue:
            self.finished.set()

    def stop(self, clear: bool = True):
        if clear:
            self.queue.clear()
        if self.voice and (self.voice.is_playing() or self.voice.is_paused()):
            self.voice.stop()
        self.finished.set()

    async def _ticker(self):
        while self.voice and self.voice.is_connected() and (self.voice.is_playing() or self.voice.is_paused()):
            if self.voice.is_playing():
                self.playback_position += 1
            await asyncio.sleep(1)

    async def _run(self):
        while not self.bot.is_closed():
            await self.finished.wait()
            self.finished.clear()
            while (self.queue or self.current) and self.voice and self.voice.is_connected():
                if not self.current and self.queue:
                    self.current = self.queue.popleft()
                if not self.current:
                    break

                self.playback_position = 0
                try:
                    track = await refresh_track(self.current)
                    self.current = track

                    options = {"before_options": FFMPEG_BEFORE_OPTIONS, "options": FFMPEG_AUDIO_OPTIONS}
                    af = FILTERS.get(self.current_filter)
                    if af:
                        options["options"] += f' -af "{af}"'

                    source = discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(track.stream_url, **options),
                        volume=self.volume / 100.0
                    )
                    done = asyncio.Event()

                    def after(error):
                        if error:
                            log.warning(f"Playback error in guild {self.guild_id}: {error}")
                        self.bot.loop.call_soon_threadsafe(done.set)

                    self.voice.play(source, after=after)
                    self.ticker_task = asyncio.create_task(self._ticker())
                    await self.update_panel()  # update once after playback starts
                    await done.wait()

                except asyncio.CancelledError:
                    return
                except Exception as e:
                    log.error(f"Playback exception in guild {self.guild_id}: {e}")
                finally:
                    if self.ticker_task:
                        self.ticker_task.cancel()
                    finished_track = self.current
                    if finished_track:
                        self.history.append(finished_track)
                        if len(self.history) > 20:
                            self.history.pop(0)

                    # Handle loop modes
                    if self.loop_mode == "single" and finished_track:
                        self.current = finished_track
                    elif self.loop_mode == "queue" and finished_track:
                        self.queue.append(finished_track)
                        self.current = None
                    else:
                        self.current = None

                    await self.update_panel()

            # Empty queue handling / 24/7 mode
            if not self.queue and not self.current and self.voice and self.voice.is_connected() and not self.mode_247:
                await asyncio.sleep(180)
                if not self.queue and not self.current and not self.mode_247 and self.voice and self.voice.is_connected():
                    guild = self.voice.guild
                    await self.voice.disconnect(force=True)
                    self.voice = None
                    await self.update_panel()
                    await restore_voice_from(self.bot, guild, "music")


# ─────────────────────────────────────────────────────────────────────────────
# MusicCog Definition & Slash Commands
# ─────────────────────────────────────────────────────────────────────────────

class MusicCog(commands.Cog):
    """GKR Studio Music System"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer(self, guild_id)
        return self.players[guild_id]

    async def ensure_voice(self, interaction: discord.Interaction, player: GuildPlayer) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.followup.send(embed=embed_error("Join a voice channel first!"), ephemeral=True)
            return False

        await yield_voice_to(self.bot, interaction.guild, "music")
        channel = member.voice.channel
        if player.voice and player.voice.is_connected():
            if player.voice.channel != channel:
                await player.voice.move_to(channel)
        else:
            player.voice = await channel.connect()
        return True

    async def send_panel(self, interaction: discord.Interaction, player: GuildPlayer, *, followup: bool = False):
        embed, _ = player.build_embed()
        view = MusicControlView(player)
        # Delete stale panel if one exists
        if player.panel_message:
            try:
                await player.panel_message.delete()
            except Exception:
                pass
            player.panel_message = None

        if followup:
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()
        player.panel_message = msg
        return msg

    # --- voice_handoff callbacks ---
    def suspend_for_handoff(self, guild: discord.Guild) -> bool:
        player = self.players.get(guild.id)
        if not player or not player.voice or not player.voice.is_connected():
            return False
        player.stop(clear=False)
        return True

    def resume_from_handoff(self, guild: discord.Guild) -> bool:
        player = self.players.get(guild.id)
        if not player or not player.queue:
            return False
        player.finished.set()
        return True

    # ── Slash Commands (Multi-Install & Profile Visibility Enabled) ──────────

    @app_commands.command(name="play", description="🎵 Play a song or playlist (YouTube, Spotify, SoundCloud)")
    @app_commands.describe(query="Song title, artist, YouTube URL, or Spotify link")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.guild:
            return await interaction.response.send_message(embed=embed_error("Run this command in a server."), ephemeral=True)
        await interaction.response.defer(thinking=True)
        player = self.get_player(interaction.guild_id)
        player.text_channel = interaction.channel
        if not await self.ensure_voice(interaction, player):
            return

        try:
            tracks = await resolve_tracks(query, interaction.user.id, interaction.user.display_name, 1)
            if not tracks:
                return await interaction.followup.send(embed=embed_error("No playable tracks found."), ephemeral=True)
            await player.enqueue(tracks)
            await self.send_panel(interaction, player, followup=True)
        except Exception as e:
            await interaction.followup.send(embed=embed_error(f"Could not load track: {e}"), ephemeral=True)

    @app_commands.command(name="nowplaying", description="🎶 Display the current interactive music player")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def nowplaying(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild_id)
        await self.send_panel(interaction, player)

    @app_commands.command(name="queue", description="📜 View the upcoming songs in the server queue")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def queue_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild_id)
        await self.send_panel(interaction, player)

    @app_commands.command(name="skip", description="⏭️ Skip the current song")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def skip(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        self.get_player(interaction.guild_id).skip()
        await interaction.response.send_message(embed=embed_success("Skipped", "Skipped to next song! ⏭️"))

    @app_commands.command(name="stop", description="⏹️ Stop music, clear queue, and disconnect")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
    async def stop(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        player = self.get_player(interaction.guild_id)
        player.stop(clear=True)
        if player.voice and player.voice.is_connected():
            guild = player.voice.guild
            await player.voice.disconnect(force=True)
            restore_voice_from(self.bot, guild, "music")
        player.voice = None
        await interaction.response.send_message(embed=embed_success("Stopped", "Music playback stopped."))

    @app_commands.command(name="pause", description="⏸️ Pause audio playback")
    async def pause(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        p = self.get_player(interaction.guild_id)
        if p.voice and p.voice.is_playing():
            p.voice.pause()
            await interaction.response.send_message(embed=embed_info("Paused", "Music playback paused. ⏸️"))
            await p.update_panel()
        else:
            await interaction.response.send_message(embed=embed_error("Nothing is playing."), ephemeral=True)

    @app_commands.command(name="resume", description="▶️ Resume paused playback")
    async def resume(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        p = self.get_player(interaction.guild_id)
        if p.voice and p.voice.is_paused():
            p.voice.resume()
            await interaction.response.send_message(embed=embed_success("Resumed", "Music resumed! ▶️"))
            await p.update_panel()
        else:
            await interaction.response.send_message(embed=embed_error("Playback is not paused."), ephemeral=True)

    @app_commands.command(name="volume", description="🔊 Change playback volume (1% - 150%)")
    @app_commands.describe(percent="Volume percentage")
    async def volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 1, 150]):
        if not interaction.guild:
            return
        p = self.get_player(interaction.guild_id)
        p.volume = percent
        if p.voice and p.voice.source and isinstance(p.voice.source, discord.PCMVolumeTransformer):
            p.voice.source.volume = percent / 100.0
        await interaction.response.send_message(embed=embed_success("Volume", f"Volume set to **{percent}%** 🔊"))
        await p.update_panel()

    @app_commands.command(name="filter", description="🎛️ Set an audio filter preset")
    @app_commands.choices(preset=[
        app_commands.Choice(name="Normal (Off)", value="Normal"),
        app_commands.Choice(name="Bass Boost", value="Bassboost"),
        app_commands.Choice(name="Nightcore", value="Nightcore"),
        app_commands.Choice(name="Vaporwave", value="Vaporwave"),
        app_commands.Choice(name="8D Audio", value="8D Audio"),
    ])
    async def filter_cmd(self, interaction: discord.Interaction, preset: app_commands.Choice[str]):
        if not interaction.guild:
            return
        p = self.get_player(interaction.guild_id)
        p.current_filter = preset.value
        restarted = p.apply_filter_to_current()
        msg = f"Audio filter set to **{preset.name}**."
        if restarted:
            msg += " Current track restarted with the filter applied."
        await interaction.response.send_message(embed=embed_success("Filter", msg))
        await p.update_panel()

    @app_commands.command(name="toggle_247", description="⚡ Toggle 24/7 mode (stay in voice channel forever)")
    async def toggle_247(self, interaction: discord.Interaction):
        if not interaction.guild:
            return
        p = self.get_player(interaction.guild_id)
        p.mode_247 = not p.mode_247
        status = "enabled" if p.mode_247 else "disabled"
        await interaction.response.send_message(embed=embed_info("24/7 Mode", f"24/7 playback **{status}**! ⚡"))
        await p.update_panel()

    @app_commands.command(name="lyrics", description="🎤 Search lyrics for the current or specified song")
    @app_commands.describe(query="Song title and artist (optional)")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def lyrics_cmd(self, interaction: discord.Interaction, query: Optional[str] = None):
        if not query:
            if interaction.guild:
                p = self.get_player(interaction.guild_id)
                if p.current:
                    query = f"{p.current.title} {p.current.artist}"
        if not query:
            return await interaction.response.send_message(embed=embed_error("Specify a song name: `/lyrics <song>`"), ephemeral=True)

        await interaction.response.defer(thinking=True)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://lrclib.net/api/search", params={"q": query}) as resp:
                    if resp.status == 200:
                        results = await resp.json()
                        if results:
                            item = results[0]
                            lyrics_text = item.get("plainLyrics") or "*No plain lyrics found.*"
                            embed = discord.Embed(
                                title=f"🎤 Lyrics — {item.get('trackName', query)}",
                                description=lyrics_text[:3900],
                                color=C.BRAND
                            )
                            embed.set_footer(text=f"Artist: {item.get('artistName', 'Unknown')}")
                            return await interaction.followup.send(embed=embed)
            await interaction.followup.send(embed=embed_info("Lyrics", f"No lyrics found for **{query}**."))
        except Exception as e:
            await interaction.followup.send(embed=embed_error(f"Lyrics lookup failed: {e}"))


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
    print("🎵 GKR Music system loaded (direct FFmpeg + yt-dlp)!")