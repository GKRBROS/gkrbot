"""
music.py — Lavalink/Wavelink Music System for GKR Bot.
Uses Lavalink (via wavelink) for all audio — no yt-dlp bot detection issues.
Supports YouTube, Spotify (search fallback), SoundCloud, playlists, and interactive controls.
"""

import asyncio
import os
import random
import difflib
import re
from typing import Optional, List, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
import aiohttp
import discord
import wavelink
from discord import app_commands
from discord.ext import commands, tasks
from gkr_ui import C, embed_error, embed_success, embed_info, BOT_NAME
from dotenv import load_dotenv
from voice_handoff import yield_voice_to, restore_voice_from

load_dotenv()


# ==================================================
# URL / TRACK NORMALIZATION HELPERS
# ==================================================


def is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def clean_youtube_watch_url(value: str) -> str:
    """Normalize single-video YouTube URLs and remove tracking/playlist parameters."""
    text = value.strip()
    try:
        parsed = urlparse(text)
        host = parsed.netloc.lower().removeprefix("www.")
        params = parse_qs(parsed.query)

        video_id: Optional[str] = None

        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0] or None

        elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path.rstrip("/") == "/watch" and params.get("v"):
                video_id = params["v"][0]
            else:
                parts = [part for part in parsed.path.split("/") if part]
                if len(parts) >= 2 and parts[0] in {"shorts", "live", "embed"}:
                    video_id = parts[1]

        if video_id:
            kept: dict[str, str] = {"v": video_id}
            for optional in ("t", "start"):
                if params.get(optional):
                    kept[optional] = params[optional][0]
            return urlunparse(("https", "www.youtube.com", "/watch", "", urlencode(kept), ""))

    except Exception:
        pass

    return text


def clean_spotify_url(value: str) -> str:
    """Normalize Spotify share links and remove tracking parameters."""
    text = value.strip()
    try:
        parsed = urlparse(text)
        host = parsed.netloc.lower().removeprefix("www.")
        if host != "open.spotify.com":
            return text

        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0].startswith("intl-"):
            parts = parts[1:]

        if len(parts) >= 2 and parts[0] in {
            "track",
            "album",
            "playlist",
            "artist",
            "episode",
            "show",
        }:
            return urlunparse(
                ("https", "open.spotify.com", "/" + "/".join(parts[:2]), "", "", "")
            )
    except Exception:
        pass
    return text


def youtube_video_id(value: str) -> Optional[str]:
    try:
        parsed = urlparse(value.strip())
        host = parsed.netloc.lower().removeprefix("www.")

        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
            return video_id or None

        if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
            params = parse_qs(parsed.query)
            if params.get("v"):
                return params["v"][0]

            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"shorts", "live", "embed"}:
                return parts[1]
    except Exception:
        return None
    return None



def get_player(guild: Optional[discord.Guild]) -> Optional[wavelink.Player]:
    """
    Safely fetch this guild's wavelink.Player, if any.

    ROOT CAUSE FIX: every command/listener in this file used to read
    `guild.voice_client` directly and just *assume* (via a type hint only,
    which does nothing at runtime) that it was a wavelink.Player. But
    `guild.voice_client` is whatever VoiceProtocol is currently connected for
    that guild — and this bot also has a separate Radio cog that connects
    with a plain `discord.VoiceClient` (no `.queue`, no `.playing`, no
    `.paused`, etc). If Radio is active in a guild, `guild.voice_client`
    returns that plain VoiceClient, and any code here that touches those
    attributes crashes with AttributeError — exactly the reported traceback
    (`'VoiceClient' object has no attribute 'paused'` in `_execute_play`).

    Routing every read through this helper means we only ever get back an
    actual wavelink.Player (or None), so the rest of the code can keep
    assuming `vc.queue`/`vc.paused`/etc. exist without re-checking everywhere.
    """
    if not guild:
        return None
    vc = guild.voice_client
    return vc if isinstance(vc, wavelink.Player) else None


async def get_or_create_music_vc(bot: commands.Bot, guild: discord.Guild, channel: discord.VoiceChannel, **connect_kwargs) -> wavelink.Player:
    """
    Get (or create) a wavelink.Player connected to `channel`, handing off
    cleanly from Radio first if Radio currently owns the connection.
    Includes timeout handling and stale session cleanup.
    """
    try:
        from blacklist import STORE as BLACKLIST_STORE
        if guild.id in BLACKLIST_STORE.server_ids:
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect(force=True)
                except Exception:
                    pass
            raise PermissionError(f"Guild {guild.id} is blacklisted.")
    except ImportError:
        pass

    # Ensure Lavalink node is ready before attempting voice connection
    if hasattr(wavelink, "Pool"):
        nodes = getattr(wavelink.Pool, "nodes", {})
        connected_nodes = [n for n in nodes.values() if getattr(n, "status", None) == wavelink.NodeStatus.CONNECTED]
        if not connected_nodes:
            cog = bot.get_cog("MusicCog")
            if cog and hasattr(cog, "_connect_lavalink"):
                try:
                    await cog._connect_lavalink()
                except Exception:
                    pass

    vc = get_player(guild)
    if vc is None:
        # If something non-wavelink (i.e. Radio) is connected, ask it to step aside
        existing = guild.voice_client
        if existing is not None:
            try:
                await yield_voice_to(bot, guild, "music")
            except Exception:
                pass
            if guild.voice_client and not isinstance(guild.voice_client, wavelink.Player):
                try:
                    await guild.voice_client.disconnect(force=True)
                except Exception:
                    pass

        timeout = connect_kwargs.pop("timeout", 30.0)
        try:
            return await channel.connect(cls=wavelink.Player, timeout=timeout, **connect_kwargs)
        except (TimeoutError, asyncio.TimeoutError):
            print(f"[Music] Initial voice connect to {channel.name} timed out. Resetting voice state and retrying once...")
            try:
                if guild.voice_client:
                    await guild.voice_client.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(1.0)
            return await channel.connect(cls=wavelink.Player, timeout=timeout, **connect_kwargs)

    if vc.channel and vc.channel.id != channel.id:
        await vc.move_to(channel)
    return vc

class TrackSelect(discord.ui.Select):
    def __init__(self, tracks, execute_callback, vc, gp):
        self.tracks_list = tracks
        self.execute_callback = execute_callback
        self.vc = vc
        self.gp = gp
        options = []
        for i, tr in enumerate(tracks[:5]):
            dur_ms = getattr(tr, 'length', 0) or 0
            dur_str = format_ms(dur_ms) if dur_ms else ""
            desc = f"{tr.author[:50]} · {dur_str}" if dur_str else tr.author[:90]
            options.append(discord.SelectOption(
                label=f"{i+1}. {tr.title[:80]}",
                description=desc,
                value=str(i),
                emoji="🎵"
            ))
        super().__init__(placeholder="Select the exact track...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        track = self.tracks_list[idx]
        await interaction.response.defer()
        await self.execute_callback(interaction, self.vc, [track], self.gp)

class TrackSelectView(discord.ui.View):
    def __init__(self, tracks, execute_callback, vc, gp):
        super().__init__(timeout=60)
        self.add_item(TrackSelect(tracks, execute_callback, vc, gp))

class AudioFilterSelect(discord.ui.Select):
    def __init__(self, current_filter: str):
        options = [
            discord.SelectOption(label="Normal (Off)", value="Normal", emoji="📻", description="Original balanced audio output", default=(current_filter == "Normal")),
            discord.SelectOption(label="Bass Boost", value="Bassboost", emoji="🔊", description="Enhanced low frequencies", default=(current_filter == "Bassboost")),
            discord.SelectOption(label="Nightcore", value="Nightcore", emoji="⚡", description="High pitch with faster tempo", default=(current_filter == "Nightcore")),
            discord.SelectOption(label="Vaporwave", value="Vaporwave", emoji="🌊", description="Slowed reverb atmosphere", default=(current_filter == "Vaporwave")),
            discord.SelectOption(label="8D Audio", value="8D Audio", emoji="🎧", description="Rotating spatial surround sound", default=(current_filter == "8D Audio")),
        ]
        super().__init__(placeholder="Choose an audio filter...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        gp: GuildPlayer = self.view.gp
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc:
            return await interaction.response.send_message(embed=embed_error("Bot is not connected to voice."), ephemeral=True)

        gp.current_filter = selected
        f = wavelink.Filters()
        if selected == "Bassboost":
            f.equalizer.set(bands=[{"band": 0, "gain": 0.3}, {"band": 1, "gain": 0.25}, {"band": 2, "gain": 0.2}])
        elif selected == "Nightcore":
            f.timescale.set(pitch=1.2, speed=1.2)
        elif selected == "Vaporwave":
            f.timescale.set(pitch=0.85, speed=0.85)
        elif selected == "8D Audio":
            f.rotation.set(rotation_hz=0.2)
        else:
            f.reset()

        await vc.set_filters(f)

        filters_status = [
            f"• **Bass Boost:** `{'Active' if selected == 'Bassboost' else 'Off'}`",
            f"• **Nightcore:** `{'Active' if selected == 'Nightcore' else 'Off'}`",
            f"• **8D Audio:** `{'Active' if selected == '8D Audio' else 'Off'}`",
            f"• **Vaporwave:** `{'Active' if selected == 'Vaporwave' else 'Off'}`",
        ]
        embed = discord.Embed(
            title="🎚  Audio Filters",
            description="\n".join(filters_status),
            color=C.BRAND
        )
        embed.set_footer(text=f"Active filter: {selected}")
        await interaction.response.edit_message(embed=embed, view=AudioFilterView(gp))

class AudioFilterView(discord.ui.View):
    def __init__(self, gp: "GuildPlayer"):
        super().__init__(timeout=120)
        self.gp = gp
        self.add_item(AudioFilterSelect(gp.current_filter))


LAVALINK_URI      = os.getenv("LAVALINK_URI")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD")

SPOTIPY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
sp = None
if SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET:
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET
        ))
        print("✅ Spotify integration enabled.")
    except Exception as e:
        print(f"⚠️ Spotify not available: {e}")

def build_progress_bar(position: int, duration: int, length: int = 15) -> str:
    """Renders a simple text progress bar, e.g. `▬▬▬🔘▬▬▬▬▬▬▬  1:23 / 3:45`."""
    if not duration or duration <= 0:
        return ""
    ratio = max(0.0, min(1.0, position / duration))
    filled = int(round(ratio * length))
    filled = max(0, min(length, filled))
    bar = "▬" * filled + "🔘" + "▬" * (length - filled)
    return f"`{bar}`  {format_ms(position)} / {format_ms(duration)}"

# BUG FIX (from a previous pass): this used to be a raw Discord CDN attachment
# link (media.discordapp.net/.../combined_music_visualizer.gif?ex=...&is=...&hm=...).
# Those `ex=`/`is=`/`hm=` query params are a signed, TIME-LIMITED URL — Discord
# attachment links are not meant to be hotlinked long-term. That link's `ex`
# timestamp decodes to 2026-08-20, so it had been rendering as a broken image
# in every "Now Playing" panel since then. Fixed by loading a local file
COMBINED_VISUALIZER_GIF_PATH = os.path.join(os.path.dirname(__file__), "combined_music_visualizer.gif")
MUSIC_VISUALIZER_GIF_FILENAME = "combined_music_visualizer.gif"
MUSIC_VISUALIZER_GIF_URL = os.getenv(
    "MUSIC_VISUALIZER_GIF_URL",
    "https://media.discordapp.net/attachments/1247646566794133585/1557275890897915964/combined_music_visualizer.gif?backend=b2&ex=6ada5371&is=6ad901f1&hm=768e324311ee1f887245027da04b41a6903fb6d0a4a8dcd463ef3aa527daae3a&="
)


def get_visualizer_file() -> Optional[discord.File]:
    """Always returns None to prevent multi-megabyte local GIF re-uploads."""
    return None

async def set_voice_channel_status(bot: commands.Bot, channel_id: int, status: str):
    """Update Discord voice channel status text for the connected VC."""
    if not channel_id:
        return
    try:
        route = discord.http.Route('PUT', '/channels/{channel_id}/voice-status', channel_id=channel_id)
        await bot.http.request(route, json={'status': status})
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions & UI Components
# ─────────────────────────────────────────────────────────────────────────────

def format_ms(ms: int) -> str:
    """Format milliseconds into MM:SS or HH:MM:SS."""
    if not ms or ms < 0:
        return "0:00"
    seconds = ms // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"

def render_progress_bar(position_ms: int, length_ms: int, bar_length: int = 15) -> str:
    """Render a sleek, minimalist progress bar with playhead."""
    if not length_ms or length_ms <= 0:
        return "━━━━━━━━━━━━━━━"
    percent = min(1.0, max(0.0, position_ms / length_ms))
    progress = int(percent * bar_length)
    progress = min(progress, bar_length - 1)
    bar = "━" * progress + "●" + "─" * (bar_length - progress - 1)
    return bar


async def set_india_voice_region(channel: discord.VoiceChannel) -> None:
    """Safely handle voice region requests without interrupting ongoing connection handshakes."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Control Panel (Buttons - Clean & Modern Spotify/Discord Theme)
# ─────────────────────────────────────────────────────────────────────────────

TOPGG_VOTE_URL = "https://top.gg/bot/1397848684061790301/vote"


async def check_voice_interact(player: "GuildPlayer", interaction: discord.Interaction) -> bool:
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message(embed=embed_error("Join a voice channel first."), ephemeral=True)
        return False
    vc = get_player(interaction.guild)
    if not vc:
        await interaction.response.send_message(embed=embed_error("Bot is not connected to voice."), ephemeral=True)
        return False
    if interaction.user.voice.channel != vc.channel:
        try:
            await vc.move_to(interaction.user.voice.channel)
        except Exception as e:
            await interaction.response.send_message(embed=embed_error(f"Could not move to channel: {e}"), ephemeral=True)
            return False
    return True


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
        if not await check_voice_interact(self.player, interaction):
            return
        action = self.values[0]
        vc: Optional[wavelink.Player] = get_player(interaction.guild)

        if action == "playpause":
            if not vc or (not vc.playing and vc.queue.is_empty):
                return await interaction.response.send_message(embed=embed_error("Nothing playing."), ephemeral=True)
            if vc.paused:
                await vc.pause(False)
                if vc.channel and vc.current:
                    st = f"🎶 {vc.current.title}" + (f" - {vc.current.author}" if vc.current.author else "")
                    await set_voice_channel_status(interaction.client, vc.channel.id, st[:100])
            else:
                await vc.pause(True)
                if vc.channel and vc.current:
                    await set_voice_channel_status(interaction.client, vc.channel.id, f"⏸️ Paused: {vc.current.title[:85]}")
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)

        elif action == "skip":
            if not vc or not vc.playing:
                return await interaction.response.send_message(embed=embed_error("Nothing to skip."), ephemeral=True)
            await vc.skip(force=True)
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)

        elif action == "prev":
            if not self.player.history:
                return await interaction.response.send_message(embed=embed_error("No previous track in history."), ephemeral=True)
            if not vc:
                return await interaction.response.send_message(embed=embed_error("Bot is not connected."), ephemeral=True)
            self.player.skip_prev = True
            prev_track = self.player.history.pop()
            if vc.playing and vc.current:
                await vc.queue.put_wait(vc.current)
                vc.queue.swap(0, len(vc.queue) - 1)
            await vc.play(prev_track)
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)

        elif action == "forward":
            if not vc or not vc.playing or not vc.current:
                return await interaction.response.send_message(embed=embed_error("Nothing is playing."), ephemeral=True)
            new_pos = min(vc.current.length, vc.position + 10000)
            await vc.seek(new_pos)
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)

        elif action == "rewind":
            if not vc or not vc.playing or not vc.current:
                return await interaction.response.send_message(embed=embed_error("Nothing is playing."), ephemeral=True)
            new_pos = max(0, vc.position - 10000)
            await vc.seek(new_pos)
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)

        elif action == "vol_up":
            if not vc:
                return
            new_vol = min(150, vc.volume + 10)
            await vc.set_volume(new_vol)
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)

        elif action == "vol_down":
            if not vc:
                return
            new_vol = max(0, vc.volume - 10)
            await vc.set_volume(new_vol)
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)

        elif action == "shuffle":
            if not vc or vc.queue.count < 2:
                return await interaction.response.send_message(embed=embed_info("Queue", "Need at least 2 songs in queue to shuffle."), ephemeral=True)
            items = list(vc.queue)
            random.shuffle(items)
            vc.queue.clear()
            for it in items:
                await vc.queue.put_wait(it)
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)
            await interaction.followup.send(embed=embed_success("Queue Shuffled", "Queue order randomized! 🔀"), ephemeral=True)

        elif action == "loop":
            modes = [None, "single", "queue"]
            cur = self.player.loop_mode
            self.player.loop_mode = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "single"
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)

        elif action == "fav":
            if not vc or not vc.current:
                return await interaction.response.send_message(embed=embed_error("No track currently playing."), ephemeral=True)
            track = vc.current
            try:
                fav_embed = discord.Embed(
                    title="❤️ Saved to Favorites",
                    description=f"**[{track.title}]({track.uri})**\n👤 **Artist:** `{track.author or 'Unknown'}`\n⏱️ **Duration:** `{format_ms(track.length)}`",
                    color=0xE74C3C
                )
                artwork = getattr(track, 'artwork_url', None) or getattr(track, 'thumbnail', None)
                if artwork:
                    fav_embed.set_thumbnail(url=artwork)
                fav_embed.set_footer(text=f"Saved from {interaction.guild.name} • {BOT_NAME} Music")
                await interaction.user.send(embed=fav_embed)
                await interaction.response.send_message(embed=embed_success("Saved!", f"Sent **{track.title}** to your DMs! ❤️"), ephemeral=True)
            except Exception:
                await interaction.response.send_message(embed=embed_success("Liked", f"Liked **{track.title}**!"), ephemeral=True)

        elif action == "stop":
            self.player.mode_247 = False
            if vc:
                if vc.channel:
                    await set_voice_channel_status(interaction.client, vc.channel.id, "")
                vc.queue.clear()
                await vc.disconnect()
            await restore_voice_from(interaction.client, interaction.guild, "music")
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)
            await interaction.followup.send(embed=embed_success("Stopped", "Music stopped and disconnected."), ephemeral=True)


class FilterActionSelect(discord.ui.Select):
    def __init__(self, player: "GuildPlayer"):
        self.player = player
        options = [
            discord.SelectOption(label="Normal (Off)", value="Normal", emoji="📻", description="Original balanced audio output", default=(player.current_filter == "Normal")),
            discord.SelectOption(label="Bass Boost", value="Bassboost", emoji="🔊", description="Enhanced low frequencies", default=(player.current_filter == "Bassboost")),
            discord.SelectOption(label="Nightcore", value="Nightcore", emoji="⚡", description="High pitch with faster tempo", default=(player.current_filter == "Nightcore")),
            discord.SelectOption(label="Vaporwave", value="Vaporwave", emoji="🌊", description="Slowed reverb atmosphere", default=(player.current_filter == "Vaporwave")),
            discord.SelectOption(label="8D Audio", value="8D Audio", emoji="🎧", description="Rotating spatial surround sound", default=(player.current_filter == "8D Audio")),
        ]
        super().__init__(placeholder="🎚️ Audio Filter Presets...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        if not await check_voice_interact(self.player, interaction):
            return
        selected = self.values[0]
        self.player.current_filter = selected
        vc = get_player(interaction.guild)
        if vc:
            f = wavelink.Filters()
            if selected == "Bassboost":
                f.equalizer.set(bands=[{"band": 0, "gain": 0.3}, {"band": 1, "gain": 0.25}, {"band": 2, "gain": 0.2}])
            elif selected == "Nightcore":
                f.timescale.set(pitch=1.2, speed=1.2)
            elif selected == "Vaporwave":
                f.timescale.set(pitch=0.85, speed=0.85)
            elif selected == "8D Audio":
                f.rotation.set(rotation_hz=0.2)
            else:
                f.reset()
            await vc.set_filters(f)
        await interaction.response.defer()
        await self.player.update_panel(interaction.client)
        await interaction.followup.send(embed=embed_success("Filter Updated", f"Audio filter set to **{selected}**."), ephemeral=True)


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
        vc = get_player(interaction.guild)

        if action == "queue":
            cur = getattr(vc, 'current', None)
            q_list = list(vc.queue) if (vc and not vc.queue.is_empty) else []
            if not cur and not q_list:
                return await interaction.response.send_message(embed=embed_info("Queue", "The queue is currently empty."), ephemeral=True)
            lines = []
            if cur:
                lines.append(f"**Now Playing:** `{cur.title}` ({format_ms(cur.length)})")
            if q_list:
                lines.append("\n**Up Next:**")
                for i, t in enumerate(q_list[:10], 1):
                    lines.append(f"`{i}.` **{t.title}** ({format_ms(t.length)})")
                if len(q_list) > 10:
                    lines.append(f"\n*...and {len(q_list) - 10} more tracks in queue*")
            q_embed = discord.Embed(
                title=f"📜 Music Queue — {interaction.guild.name}",
                description="\n".join(lines),
                color=C.BRAND
            )
            total_tracks = len(q_list) + (1 if cur else 0)
            q_embed.set_footer(text=f"Total: {total_tracks} songs")
            return await interaction.response.send_message(embed=q_embed, ephemeral=True)

        if action == "lyrics":
            cur = getattr(vc, 'current', None)
            if not cur:
                return await interaction.response.send_message(embed=embed_error("Nothing is currently playing."), ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            lyrics_text = getattr(self.player, 'lyrics_cache', {}).get(cur.identifier, "")
            if not lyrics_text:
                try:
                    import urllib.parse
                    clean_title = re.sub(r'\s*(\([^)]*\)|\[[^]]*\])', '', cur.title, flags=re.IGNORECASE).strip()
                    async with aiohttp.ClientSession() as session:
                        async with session.get("https://lrclib.net/api/search", params={"q": f"{clean_title} {cur.author or ''}"}) as resp:
                            if resp.status == 200:
                                results = await resp.json()
                                if results:
                                    item = results[0]
                                    lyrics_text = item.get("plainLyrics") or "*No plain lyrics found.*"
                except Exception:
                    lyrics_text = "*Could not fetch lyrics.*"
            if not lyrics_text:
                lyrics_text = f"*No lyrics found for **{cur.title}**.*"
            lyrics_embed = discord.Embed(
                title=f"🎤 Lyrics — {cur.title}",
                description=lyrics_text[:3900],
                color=C.BRAND
            )
            lyrics_embed.set_footer(text=f"Artist: {cur.author or 'Unknown'}")
            return await interaction.followup.send(embed=lyrics_embed, ephemeral=True)

        if action == "247":
            if not await check_voice_interact(self.player, interaction):
                return
            self.player.mode_247 = not self.player.mode_247
            status = "enabled" if self.player.mode_247 else "disabled"
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)
            return await interaction.followup.send(embed=embed_info("24/7 Mode", f"24/7 playback **{status}**! ⚡"), ephemeral=True)

        if action == "clear":
            if not await check_voice_interact(self.player, interaction):
                return
            if vc:
                vc.queue.clear()
            await interaction.response.defer()
            await self.player.update_panel(interaction.client)
            return await interaction.followup.send(embed=embed_success("Queue Cleared", "Upcoming queue was cleared."), ephemeral=True)


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

    async def refresh_panel(self, interaction: discord.Interaction):
        await self.player.update_panel(interaction.client)

# ─────────────────────────────────────────────────────────────────────────────
# Per-Guild Player State
# ─────────────────────────────────────────────────────────────────────────────

class GuildPlayer:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.loop_mode: Optional[str] = None   # None, "single", "queue"
        self.mode_247: bool = False
        self.panel_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.history: List[wavelink.Playable] = []
        self.skip_prev: bool = False
        self.gif_index: int = 0
        self.current_filter: str = "Normal"
        self.voice_client: Optional[wavelink.Player] = None
        self.metrics: dict = {}
        self.loading_track: Optional[wavelink.Playable] = None

    def _get_requester(self, track: wavelink.Playable) -> Optional[str]:
        """Safely extract requester from ExtrasNamespace (wavelink 3.x)."""
        try:
            extras = getattr(track, 'extras', None)
            if extras is None:
                return None
            return getattr(extras, 'requester', None)
        except Exception:
            return None

    def build_embed(self, vc: Optional[wavelink.Player], track: Optional[wavelink.Playable] = None) -> Tuple[discord.Embed, Optional[discord.File]]:
        embed = discord.Embed(color=C.BRAND)
        bot_avatar = None
        try:
            if vc and vc.guild and vc.guild.me and vc.guild.me.display_avatar:
                bot_avatar = vc.guild.me.display_avatar.url
        except Exception:
            pass
        embed.set_author(name=f"{BOT_NAME.upper()} MUSIC PLAYER", icon_url=bot_avatar)

        cur_track = track or (getattr(vc, 'current', None) if vc else None)
        if not cur_track and hasattr(self, 'loading_track') and self.loading_track:
            cur_track = self.loading_track

        is_active = bool(cur_track)

        if not is_active:
            desc = (
                "**No track currently playing.**\n\n"
                "Use `/play <song or link>` or `/random` to start streaming!"
            )
            try:
                from bot_status_msg import get_status_message
                status_msg = get_status_message()
                if status_msg and status_msg.get("active") and status_msg.get("message"):
                    desc += f"\n\n📢 **Notice:** {status_msg['message']}"
            except Exception:
                pass

            embed.description = desc
            embed.set_footer(text=f"Queue: 0 tracks · {BOT_NAME} Studio Audio")
            if MUSIC_VISUALIZER_GIF_URL:
                embed.set_image(url=MUSIC_VISUALIZER_GIF_URL)
            return embed, None

        track = cur_track
        self.voice_client = vc
        loop_str = {"single": "🔂 Single", "queue": "🔁 Queue"}.get(self.loop_mode, "Off")
        is_paused = getattr(vc, 'paused', False) if vc else False
        is_playing = getattr(vc, 'playing', False) if vc else False

        if is_paused:
            status_badge = "⏸️ **Paused**"
        elif not is_playing and (hasattr(self, 'loading_track') and self.loading_track == track):
            status_badge = "⏳ **Loading...**"
        else:
            status_badge = "🟢 **Playing**"

        requester = self._get_requester(track) or "User"
        pos = getattr(vc, "position", 0) if vc else 0
        dur = getattr(track, "length", 0) or 0
        progress = build_progress_bar(pos, dur)
        vol = getattr(vc, "volume", 100) if vc else 100

        desc = (
            f"## [{track.title}]({track.uri})\n"
            f"*by* **{track.author or 'Unknown Artist'}**\n\n"
            + (f"{progress}\n\n" if progress else "")
            + f"🔊 `{vol}%`  ·  🎛️ `{self.current_filter}`  ·  🔁 `{loop_str}`  ·  ⚡ `{'24/7 ON' if self.mode_247 else '24/7 OFF'}`\n\n"
            f"🎧 Requested by **{requester}**  ·  {status_badge}"
        )
        try:
            from bot_status_msg import get_status_message
            status_msg = get_status_message()
            if status_msg and status_msg.get("active") and status_msg.get("message"):
                desc += f"\n\n📢 **Notice:** {status_msg['message']}"
        except Exception:
            pass
        embed.description = desc

        artwork = getattr(track, 'artwork_url', None) or getattr(track, 'thumbnail', None)
        if not artwork and hasattr(track, 'identifier') and track.identifier and len(track.identifier) == 11:
            artwork = f"https://i.ytimg.com/vi/{track.identifier}/hqdefault.jpg"
        if artwork:
            embed.set_thumbnail(url=artwork)

        if MUSIC_VISUALIZER_GIF_URL:
            embed.set_image(url=MUSIC_VISUALIZER_GIF_URL)

        q_count = vc.queue.count if (vc and hasattr(vc, 'queue')) else 0
        embed.set_footer(text=f"Queue · {q_count} tracks   |   Source · {BOT_NAME} Studio Audio")
        return embed, None

    async def update_panel(self, bot: commands.Bot, track: Optional[wavelink.Playable] = None):
        guild = bot.get_guild(self.guild_id)
        if not guild:
            return
        vc: Optional[wavelink.Player] = get_player(guild)
        self.voice_client = vc

        embed, _ = self.build_embed(vc, track)
        view = MusicControlView(self)

        if self.panel_message:
            try:
                await self.panel_message.edit(embed=embed, view=view)
                return
            except (discord.NotFound, discord.HTTPException):
                self.panel_message = None
            except Exception:
                pass

        channel = self.text_channel
        if not channel or not channel.permissions_for(guild.me).send_messages:
            channel = None
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    channel = ch
                    break
        if channel:
            try:
                self.panel_message = await channel.send(embed=embed, view=view)
            except Exception as e:
                print(f"[Music] Failed to send panel: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main Music Cog
# ─────────────────────────────────────────────────────────────────────────────

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_players: dict[int, GuildPlayer] = {}
        # Guild ids -> saved session state, for guilds where Music was
        # suspended so Radio could take over the voice channel. See
        # suspend_for_handoff()/resume_from_handoff() and voice_handoff.py.
        self._handoff_state: dict[int, dict] = {}

    def get_gp(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.guild_players:
            self.guild_players[guild_id] = GuildPlayer(guild_id)
        return self.guild_players[guild_id]

    # -----------------------------------------------------------------------
    # Music <-> Radio voice handoff (see voice_handoff.py)
    # -----------------------------------------------------------------------

    async def suspend_for_handoff(self, guild: discord.Guild) -> bool:
        """Called by the Radio cog (via voice_handoff.yield_voice_to) right
        before it wants to connect and play a station. If Music currently
        owns this guild's voice connection, save the queue/current
        track/position/volume/loop state and disconnect cleanly so Radio can
        take the channel, instead of Radio just yanking it out from under us."""
        vc = get_player(guild)
        if not vc:
            return False  # Music isn't the one holding the connection right now

        gp = self.get_gp(guild.id)
        try:
            queue_items = list(vc.queue)
        except Exception:
            queue_items = []
        current = getattr(vc, "current", None)
        position = getattr(vc, "position", 0) or 0
        was_paused = bool(getattr(vc, "paused", False))
        volume = getattr(vc, "volume", 100)
        channel_id = vc.channel.id if vc.channel else None

        # Nothing worth resuming later (no track, no queue) — just let Radio
        # have the channel, nothing to save.
        if not current and not queue_items:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            return False

        self._handoff_state[guild.id] = {
            "channel_id": channel_id,
            "queue": queue_items,
            "current": current,
            "position": position,
            "was_paused": was_paused,
            "volume": volume,
            "loop_mode": gp.loop_mode,
            "mode_247": gp.mode_247,
            "text_channel": gp.text_channel,
        }

        try:
            if vc.channel:
                await set_voice_channel_status(self.bot, vc.channel.id, "")
        except Exception:
            pass
        try:
            await vc.disconnect(force=True)
        except Exception as e:
            print(f"[Music] suspend_for_handoff disconnect error: {e}")

        return True

    async def resume_from_handoff(self, guild: discord.Guild) -> bool:
        """Called by the Radio cog (via voice_handoff.restore_voice_from)
        once it stops, to give the channel back to Music if Music was
        suspended for this handoff. Reconnects and resumes the saved queue
        and current track from the saved position."""
        saved = self._handoff_state.pop(guild.id, None)
        if not saved:
            return False

        channel_id = saved.get("channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        if not isinstance(channel, discord.VoiceChannel):
            return False

        # Same race as Radio's side: reconnecting the instant Radio
        # disconnects can beat Discord's voice gateway to fully process the
        # teardown and silently time out. Back off and retry once.
        vc = None
        last_err: Optional[Exception] = None
        for attempt, delay in enumerate((1.5, 3.0), start=1):
            await asyncio.sleep(delay)
            try:
                vc = await channel.connect(cls=wavelink.Player, self_deaf=True)
                break
            except Exception as e:
                last_err = e
                print(f"[Music] Reconnect attempt {attempt} after handoff failed: {e}")

        if vc is None:
            print(f"[Music] Failed to reconnect after handoff: {last_err}")
            text_channel = saved.get("text_channel")
            if text_channel:
                try:
                    await text_channel.send("🎵 I couldn't automatically resume music after the radio finished — try playing your track again.")
                except Exception:
                    pass
            return False

        gp = self.get_gp(guild.id)
        gp.loop_mode = saved.get("loop_mode")
        gp.mode_247 = saved.get("mode_247", False)
        gp.text_channel = saved.get("text_channel")
        gp.voice_client = vc

        try:
            await vc.set_volume(saved.get("volume", 100))
        except Exception:
            pass

        for item in saved.get("queue", []):
            try:
                await vc.queue.put_wait(item)
            except Exception:
                pass

        current = saved.get("current")
        if current:
            try:
                await vc.play(current, start=int(saved.get("position", 0) or 0))
                if saved.get("was_paused"):
                    await vc.pause(True)
                if vc.channel and not saved.get("was_paused"):
                    st = f"🎶 {current.title}" + (f" - {current.author}" if getattr(current, "author", None) else "")
                    await set_voice_channel_status(self.bot, vc.channel.id, st[:100])
            except Exception as e:
                print(f"[Music] Failed to resume current track after handoff: {e}")
        elif not vc.queue.is_empty:
            try:
                next_track = vc.queue.get()
                await vc.play(next_track)
            except Exception as e:
                print(f"[Music] Failed to resume queue after handoff: {e}")

        await gp.update_panel(self.bot, getattr(vc, "current", None))
        return True

    async def cog_load(self):
        await self._connect_lavalink()

    async def cog_unload(self):
        """Cleanup all active music players, voice connections, and Wavelink nodes when cog unloads."""
        for guild_id, gp in list(self.guild_players.items()):
            try:
                guild = self.bot.get_guild(guild_id)
                if guild and guild.voice_client:
                    if hasattr(guild.voice_client, 'stop'):
                        await guild.voice_client.stop()
                    await guild.voice_client.disconnect(force=True)
            except Exception as e:
                print(f"[Music] Error cleaning up player for guild {guild_id}: {e}")
        self.guild_players.clear()

        # Cleanly close all Wavelink nodes and stop reconnect loops
        try:
            if hasattr(wavelink, "Pool") and wavelink.Pool.nodes:
                await wavelink.Pool.close()
                print("[Music] Wavelink pool closed.")
        except Exception as e:
            print(f"[Music] Error closing Wavelink pool: {e}")

    async def _connect_lavalink(self):
        if not LAVALINK_URI or not LAVALINK_PASSWORD:
            print("[Music] ⚠️ LAVALINK_URI or LAVALINK_PASSWORD not set in environment.")
            return

        # Check if already connected or has an active node
        if hasattr(wavelink, "Pool") and wavelink.Pool.nodes:
            for n in list(wavelink.Pool.nodes.values()):
                if getattr(n, "status", None) == wavelink.NodeStatus.CONNECTED:
                    print(f"✅ Lavalink already connected → {n.uri}")
                    return
            try:
                await wavelink.Pool.close()
            except Exception:
                pass

        use_ssl = LAVALINK_URI.startswith("https://")
        print(f"[Music] Connecting to Lavalink: {LAVALINK_URI} (ssl={use_ssl})")
        try:
            node = wavelink.Node(
                uri=LAVALINK_URI,
                password=LAVALINK_PASSWORD,
                inactive_player_timeout=300,
                retries=3
            )
            await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=300)
            print(f"✅ Lavalink node registered → {LAVALINK_URI}")
        except Exception as e:
            print(f"❌ Lavalink connection failed: {e}")

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"🎵 Lavalink node '{payload.node.identifier}' is ready and connected!")


    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        if not payload.player:
            return
        import time
        gp = self.get_gp(payload.player.guild.id)
        gp.metrics["track_start"] = time.time()
        track_title = getattr(payload.track, 'title', 'Unknown')
        track_author = getattr(payload.track, 'author', '')
        
        print("\n━━━━━━━━ TRACK PLAYBACK ━━━━━━━━━")
        print(f"Lavalink title: {track_title}")
        print(f"Lavalink artist: {track_author}")
        print(f"Lavalink identifier: {payload.track.identifier}")
        if hasattr(gp, 'last_queued_identifier'):
            match = "YES" if gp.last_queued_identifier == payload.track.identifier else "NO (MISMATCH!)"
            print(f"MATCH: {match}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        # Update Discord voice channel status
        if payload.player.channel:
            st = f"🎶 {track_title}" + (f" - {track_author}" if track_author else "")
            await set_voice_channel_status(self.bot, payload.player.channel.id, st[:100])

        gp.loading_track = None
        # Update the music panel embed
        await gp.update_panel(self.bot, payload.track)

    async def _prefetch_lyrics(self, guild_id: int, track: wavelink.Playable):
        gp = self.get_gp(guild_id)
        if not hasattr(gp, 'lyrics_cache'):
            gp.lyrics_cache = {}
            
        import urllib.parse
        clean_title = re.sub(r'\s*(\(feat[^)]*\)|\(ft[^)]*\)|\[feat[^]]*\]|\(Remix\)|\(Official.*?\))', '', track.title, flags=re.IGNORECASE).strip()
        author = track.author or ""
        
        search_attempts = [
            f"https://lrclib.net/api/get?track_name={urllib.parse.quote(track.title)}&artist_name={urllib.parse.quote(author)}",
            f"https://lrclib.net/api/get?track_name={urllib.parse.quote(clean_title)}&artist_name={urllib.parse.quote(author)}",
            f"https://lrclib.net/api/search?q={urllib.parse.quote(clean_title)}"
        ]
        
        lyrics_text = ""
        try:
            async with aiohttp.ClientSession() as session:
                for url in search_attempts:
                    if lyrics_text: break
                    try:
                        async with session.get(url, timeout=5) as resp:
                            if resp.status == 200:
                                d = await resp.json()
                                if isinstance(d, list) and d: d = d[0]
                                if isinstance(d, dict):
                                    lyrics_text = d.get("plainLyrics") or d.get("syncedLyrics") or ""
                    except Exception:
                        continue
        except Exception:
            pass
            
        gp.lyrics_cache[track.identifier] = lyrics_text

    async def _wait_for_audio_flow(self, player: wavelink.Player, gp):
        import time
        start_wait = time.time()
        # Wait up to 10 seconds for Lavalink position to start moving (indicating audio frames are flowing)
        while player.position == 0 and (time.time() - start_wait) < 10.0:
            await asyncio.sleep(0.01)
            
        t_audio = time.time()
        # Give track_start event a moment to populate if it hasn't already
        await asyncio.sleep(0.1)

        m = gp.metrics
        try:
            search = m.get("search_end", t_audio) - m.get("search_start", t_audio)
            load = m.get("load_end", t_audio) - m.get("load_start", t_audio)
            voice = m.get("voice_end", t_audio) - m.get("voice_start", t_audio)
            play_cmd = m.get("play_cmd", t_audio)
            lavalink = m.get("track_start", t_audio) - play_cmd
            audio = t_audio - m.get("track_start", t_audio)
            total = t_audio - m.get("cmd_recv", t_audio)
            
            print("\n━━━━━━━━ MUSIC LATENCY ━━━━━━━━")
            print(f"Search:       {search:.2f}s")
            print(f"Track Load:   {load:.2f}s")
            print(f"Voice:        {voice:.2f}s")
            print(f"Lavalink:     {lavalink:.2f}s")
            print(f"First Audio:  {audio:.2f}s (Based on player.position > 0)")
            print("───────────────────────────────")
            print(f"TOTAL:        {total:.2f}s")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        except Exception as e:
            print(f"[Music] Diagnostic error: {e}")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        """Handle Lavalink track errors — auto-skip to next track."""
        track_title = getattr(payload.track, 'title', 'Unknown')
        print(f"[Music] ⚠️ Track exception on '{track_title}': {payload.exception}")
        if not payload.player:
            return
        gp = self.get_gp(payload.player.guild.id)
        # Auto-skip: if queue has next track, play it
        if not payload.player.queue.is_empty:
            try:
                next_track = payload.player.queue.get()
                await payload.player.play(next_track)
                return
            except Exception:
                pass
        ch = gp.text_channel
        if ch:
            try:
                await ch.send(
                    f"⚠️ **Couldn't play '{track_title}'** — Lavalink error. Queue is empty.",
                    delete_after=10
                )
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        track_title = getattr(payload.track, 'title', 'Unknown')
        print(f"[Music] ⏹️ Track ended: '{track_title}' (Reason: {payload.reason})")
        if not payload.player:
            return
        gp = self.get_gp(payload.player.guild.id)
        player: wavelink.Player = payload.player

        # Add to history
        if payload.track:
            gp.history.append(payload.track)
            if len(gp.history) > 20:
                gp.history.pop(0)

        # Loop logic
        if gp.loop_mode == "single" and payload.track:
            try:
                await player.play(payload.track)
                return
            except Exception as exc:
                print(f"[Music] Direct loop replay failed ({exc}), attempting re-resolve...")
                try:
                    res = await self._resolve(payload.track.uri or payload.track.title, payload.player.guild.me)
                    if res.get("type") == "single" and res.get("track"):
                        await player.play(res["track"])
                        return
                except Exception as ex2:
                    print(f"[Music] Re-resolve loop replay failed: {ex2}")
                    if gp.text_channel:
                        try:
                            await gp.text_channel.send(
                                f"⚠️ **Could not loop '{track_title}'**: Lavalink error ({exc}). Continuing queue.",
                                delete_after=10
                            )
                        except Exception:
                            pass
                    gp.loop_mode = None

        if gp.loop_mode == "queue" and payload.track:
            try:
                await player.queue.put_wait(payload.track)
            except Exception:
                pass

        # Play next — pop directly from queue (no get_wait latency)
        if player.queue.is_empty:
            if player.channel:
                try:
                    await set_voice_channel_status(self.bot, player.channel.id, "")
                except Exception:
                    pass
            try:
                await gp.update_panel(self.bot, None)
            except Exception:
                pass
            if not gp.mode_247:
                await asyncio.sleep(30)
                if player.queue.is_empty and not player.playing:
                    guild = player.guild
                    try:
                        if player.channel:
                            await set_voice_channel_status(self.bot, player.channel.id, "")
                        await player.disconnect()
                    except Exception:
                        pass
                    # FEATURE: if Radio was paused to let this music session
                    # play, hand the voice channel back to it now that the
                    # queue is actually finished and we've disconnected.
                    if guild:
                        await restore_voice_from(self.bot, guild, "music")
        else:
            try:
                next_track = player.queue.get()
                await player.play(next_track)
            except Exception:
                try:
                    # Fallback to get_wait if get() is not available
                    next_track = await player.queue.get_wait()
                    await player.play(next_track)
                except Exception as e:
                    print(f"[Music] Failed to play next track from queue: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        """Auto-disconnect if alone in VC (unless 24/7 mode)."""
        if member.bot:
            return
        guild = member.guild
        vc = get_player(guild)
        if not vc or not isinstance(vc, wavelink.Player):
            return
        gp = self.get_gp(guild.id)
        if gp.mode_247:
            return
        # Check if bot is alone
        if not vc.channel:
            return
        members_in_vc = [m for m in vc.channel.members if not m.bot]
        if not members_in_vc:
            await asyncio.sleep(60)
            vc2 = get_player(guild)
            if vc2 and isinstance(vc2, wavelink.Player) and vc2.channel and not [m for m in vc2.channel.members if not m.bot]:
                if vc2.channel:
                    await set_voice_channel_status(self.bot, vc2.channel.id, "")
                if hasattr(vc2, "queue"):
                    vc2.queue.clear()
                await vc2.disconnect()


    # ── Music Search Ranking Engine ────────────────────────────────────────────
    # Deterministic, multi-signal scoring: title relevance > artist match >
    # canonical/official version > popularity. Non-music content is hard-rejected.
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_query(text: str) -> str:
        """Normalize text for comparison: lowercase, strip punctuation/noise words."""
        if not text:
            return ""
        import unicodedata
        text = unicodedata.normalize("NFKC", text)
        text = text.lower().strip()
        text = re.sub(r"[''`]", "", text)        # curly quotes
        text = re.sub(r"[-–—]", " ", text)       # dashes → space
        text = re.sub(r"[^\w\s]", " ", text)     # remove punctuation
        text = re.sub(r"\s+", " ", text).strip()
        # Remove generic filler words users add that confuse title matching
        filler = r"\b(full song|full video song|official song|official music video|official audio|official video|music video|full video|hd video|hd|4k|mp3|song|songs|audio|video|track)\b"
        text = re.sub(filler, "", text).strip()
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _extract_intent(query: str):
        """
        Parse the raw query into (artist, title, version_tags).
        version_tags is a set of explicitly requested alternate versions.
        """
        q = query.lower().strip()

        # Detect explicitly requested alternate versions
        version_keywords = {
            "instrumental", "whistle", "flute", "violin", "guitar", "piano",
            "saxophone", "sitar", "veena", "bgm", "background music", "theme",
            "ost", "karaoke", "playback", "cover", "remix", "slowed", "reverb",
            "slowed reverb", "sped up", "speed up", "nightcore", "daycore",
            "bass boosted", "bass boost", "lofi", "lo fi", "8d", "16d", "3d audio",
            "acoustic", "unplugged", "live", "mashup", "medley", "ai cover",
            "trending", "beats", "trap remix", "extended",
        }
        found_versions = {kw for kw in version_keywords if kw in q}

        # Artist/title split patterns: "Artist - Title", "Title by Artist"
        artist, title = None, None
        dash_match = re.match(r"^(.+?)\s*[-–—]\s*(.+)$", q)
        by_match = re.match(r"^(.+?)\s+by\s+(.+)$", q)

        if dash_match:
            part_a, part_b = dash_match.group(1).strip(), dash_match.group(2).strip()
            artist, title = part_a, part_b
        elif by_match:
            title, artist = by_match.group(1).strip(), by_match.group(2).strip()
        else:
            title = q
            artist = None

        return artist, title, found_versions

    @staticmethod
    def _is_non_music(title: str, author: str) -> bool:
        """
        Hard-reject obvious non-music content: tutorials, news, gaming,
        motivational, podcast, reaction, documentary, Shorts memes, etc.
        Returns True if the result should be EXCLUDED from music search.
        """
        combined = (title + " " + author).lower()

        # Patterns that are very unlikely to be music tracks
        non_music_patterns = [
            r"\bhow to\b", r"\btutorial\b", r"\btips\b", r"\btricks\b",
            r"\breview\b", r"\bnews\b", r"\bbreaking news\b", r"\bpodcast\b",
            r"\binterview\b", r"\bcomedy\b", r"\bprank\b", r"\bchallenge\b",
            r"\bgaming\b", r"\bminecraft\b", r"\bfortnite\b", r"\bfree fire\b",
            r"\bpubg\b", r"\bvlog\b", r"\bhaul\b", r"\bunboxing\b",
            r"\bdocumentary\b", r"\bexplained\b", r"\beducation\b",
            r"\b(nikola )?tesla\b(?!.*music)", r"\btop \d+\b",
            r"\bworkout\b", r"\bmeditation\b", r"\brelaxing sounds\b",
            r"\bstudying\b", r"\bstudy music\b(?!.*official)",
            r"\bnature sounds\b", r"\brain sounds\b", r"\bbinauralbeats\b",
            r"\bpropaganda\b", r"\bpolitics\b", r"\bspeech\b",
            r"\b(motivational|inspirational)\s+(speech|video|talk)\b",
            r"\bunlock your potential\b", r"\blaw of attraction\b",
            r"\bsecrets? (of|to)\b", r"\b\d{4}[\s_]\d{2}[\s_]\d{2}\b",  # date-stamp filenames
        ]
        for pat in non_music_patterns:
            if re.search(pat, combined):
                return True

        # Reject if title is a bare alphanumeric timestamp (like "2024 06 25 05 05 22")
        if re.fullmatch(r"[\d\s_\-:\.]+", title.strip()):
            return True

        return False

    @staticmethod
    def _is_shorts(uri: str, title: str) -> bool:
        """Detect YouTube Shorts."""
        if not uri:
            return False
        return "/shorts/" in uri or "#shorts" in title.lower() or "#ytshorts" in title.lower()

    @staticmethod
    def _official_score(title: str, author: str) -> float:
        """Score how 'official' a result looks (0.0–1.0)."""
        t = title.lower()
        a = author.lower()
        score = 0.0
        if "- topic" in a or a.endswith("topic"):
            score += 1.0   # YouTube Music official topic channel = highest
        if "vevo" in a or "vevo" in t:
            score += 0.9
        official_terms = ["official audio", "official music video", "official video",
                          "full video song", "full song", "lyrical video", "lyric video",
                          "official lyric", "official"]
        for term in official_terms:
            if term in t:
                score += 0.5
                break
        # Known major labels / music channels
        label_signals = [
            "t-series", "tseries", "sony music", "zee music", "saregama",
            "aditya music", "lahari music", "think music", "tips music", "divo",
            "muzik247", "speed records", "universal music", "warner music",
            "columbia records", "atlantic records", "republic records", "rca records",
            "interscope", "def jam", "epic records", "capitol records",
            "monstercat", "spinnin", "ultra music", "armada music", "anjunabeats",
        ]
        for lbl in label_signals:
            if lbl in a or lbl in t:
                score += 0.6
                break
        return min(score, 1.0)

    @staticmethod
    def _alternate_version_penalty(title: str, author: str, requested_versions: set) -> float:
        """
        Return a penalty score (0.0 = no penalty, 1.0 = heavy penalty) for
        alternate/derivative versions that the user did NOT request.
        """
        combined = (title + " " + author).lower()
        alternate_signals = {
            "instrumental", "instrumental version", "whistle", "flute", "violin",
            "guitar", "piano", "saxophone", "sitar", "veena", "bgm",
            "background music", "background score", "karaoke", "minus one",
            "no vocals", "without vocals", "vocal removed", "acapella",
            "ost", "cover", "remix", "slowed", "reverb",
            "sped up", "speed up", "nightcore", "daycore", "bass boosted",
            "bass boost", "lofi", "lo-fi", "8d", "16d", "acoustic", "unplugged",
            "live version", "mashup", "medley", "ai cover", "trending music",
            "trending audio", "edit audio", "ringtone", "status video",
        }
        penalty = 0.0
        for sig in alternate_signals:
            if sig in combined and sig not in requested_versions:
                penalty += 0.6  # each unasked-for alternate tag adds penalty
        return min(penalty, 1.0)

    @staticmethod
    def _token_relevance(norm_query: str, norm_title: str, norm_author: str) -> float:
        """
        Token-based relevance: how many query words appear in title+author?
        Returns 0.0–1.0.
        """
        q_words = set(norm_query.split())
        if not q_words:
            return 0.0
        target = set((norm_title + " " + norm_author).split())
        matched = q_words & target
        return len(matched) / len(q_words)

    @staticmethod
    def _rank_tracks(query: str, tracks: List[wavelink.Playable], spotify_top: Optional[dict] = None) -> dict:
        """
        Score candidates and return single best result or ambiguous list.
        Scoring incorporates:
          - Title relevance & exact canonical title match bonus
          - Global streaming popularity from Spotify chart data
          - Artist matching & topic channel / label verification
          - Rejection of unrequested features, instrumentals, or derivative covers
        """
        if not tracks:
            return {"type": "error", "message": "No tracks found"}

        raw_query = query.strip()
        artist_intent, title_intent, version_tags = MusicCog._extract_intent(raw_query)
        norm_query = MusicCog._normalize_query(raw_query)
        norm_title_intent = MusicCog._normalize_query(title_intent or raw_query)
        norm_artist_intent = MusicCog._normalize_query(artist_intent or "")

        scored = []

        for rank_idx, track in enumerate(tracks[:30]):
            raw_title = track.title or ""
            raw_author = track.author or ""
            uri = getattr(track, "uri", "") or ""
            length_ms = getattr(track, "length", 0) or 0

            # ── Hard Rejects ──────────────────────────────────────────────────
            if getattr(track, "is_stream", False):
                continue
            if MusicCog._is_non_music(raw_title, raw_author):
                print(f"[Rank] 🚫 Hard-rejected (non-music): '{raw_title}'")
                continue

            # Reject vocal-less/alternate versions unless explicitly requested.
            raw_combined = f"{raw_title} {raw_author}".lower()
            vocal_less_signals = (
                "instrumental", "karaoke", "background music",
                "background score", "no vocals", "without vocals",
                "vocal removed", "minus one", "karaoke version",
            )
            if (any(sig in raw_combined for sig in vocal_less_signals)
                    and not any(v in version_tags for v in
                                ("instrumental", "karaoke", "bgm",
                                 "background music", "playback"))):
                print(f"[Rank] 🚫 Hard-rejected (vocal-less variant): '{raw_title}'")
                continue
            if MusicCog._is_shorts(uri, raw_title) and not any(v in ("short", "shorts") for v in version_tags):
                if length_ms < 60_000:
                    print(f"[Rank] 🚫 Hard-rejected (Shorts): '{raw_title}'")
                    continue
            if length_ms > 1_200_000 and not any(w in norm_query for w in ("mix", "compilation", "playlist", "mashup", "hour")):
                continue

            norm_t = MusicCog._normalize_query(raw_title)
            norm_a = MusicCog._normalize_query(raw_author)

            # ── 1. Title Relevance (0.0–1.0) ─────────────────────────────────
            title_sim = difflib.SequenceMatcher(None, norm_title_intent, norm_t).ratio()
            token_rel = MusicCog._token_relevance(norm_title_intent, norm_t, norm_a)
            relevance_score = (title_sim * 0.6 + token_rel * 0.4)

            # Check sub-segments (e.g., "Artist - Song Title | Official Video")
            title_parts = re.split(r"[-–—:|]", raw_title)
            best_sub_sim = 0.0
            for part in title_parts:
                norm_part = MusicCog._normalize_query(part)
                if norm_part:
                    part_sim = difflib.SequenceMatcher(None, norm_title_intent, norm_part).ratio()
                    if norm_title_intent == norm_part:
                        best_sub_sim = max(best_sub_sim, 1.0)
                    elif norm_title_intent in norm_part.split():
                        best_sub_sim = max(best_sub_sim, 0.95)
                    else:
                        best_sub_sim = max(best_sub_sim, part_sim)

            if best_sub_sim > 0.6:
                relevance_score = max(relevance_score, best_sub_sim * 0.7 + token_rel * 0.3)

            if norm_title_intent and norm_title_intent in norm_t.split():
                relevance_score = min(1.0, max(relevance_score + 0.3, 0.90))

            # ── 2. Exact Title Matching Bonus ────────────────────────────────
            # Pure title "STAY" should beat "Stay (feat. Gabzy)"
            exact_title_bonus = 0.0
            if norm_title_intent and norm_t == norm_title_intent:
                exact_title_bonus = 0.15
            elif norm_title_intent and any(feat in norm_t for feat in ("feat", "ft", "featuring", "with")):
                if not any(feat in norm_query for feat in ("feat", "ft", "featuring", "with")):
                    exact_title_bonus = -0.06

            # ── 3. Artist Match (0.0–1.0) ─────────────────────────────────────
            artist_score = 0.0
            if norm_artist_intent:
                artist_sim = difflib.SequenceMatcher(None, norm_artist_intent, norm_a).ratio()
                artist_token = MusicCog._token_relevance(norm_artist_intent, norm_a, norm_t)
                artist_score = (artist_sim * 0.6 + artist_token * 0.4)
                if norm_artist_intent in norm_a:
                    artist_score = min(1.0, artist_score + 0.3)
            else:
                artist_score = MusicCog._token_relevance(norm_query, norm_t, norm_a) * 0.5

            # ── 4. Global Hit / Spotify Popularity Bonus ──────────────────────
            spotify_bonus = 0.0
            if spotify_top:
                spot_title = MusicCog._normalize_query(spotify_top.get("title", ""))
                spot_artists = [MusicCog._normalize_query(a) for a in spotify_top.get("artists", [])]
                spot_pop = float(spotify_top.get("popularity", 0)) / 100.0

                title_sim_spot = difflib.SequenceMatcher(None, spot_title, norm_t).ratio()
                title_matched = (spot_title == norm_t) or (spot_title in norm_t) or (norm_t in spot_title) or (title_sim_spot >= 0.8)

                artist_matched = any(
                    sa and (sa in norm_a or norm_a in sa or sa in norm_t or norm_t in sa or difflib.SequenceMatcher(None, sa, norm_a).ratio() >= 0.7)
                    for sa in spot_artists
                )

                if title_matched and artist_matched:
                    # Direct match with globally most-played song on charts
                    spotify_bonus = spot_pop * 0.35
                elif title_matched and not norm_artist_intent:
                    spotify_bonus = spot_pop * 0.10

            # ── 5. Canonical Version Score (0.0–1.0) ──────────────────────────
            alt_penalty = MusicCog._alternate_version_penalty(raw_title, raw_author, version_tags)
            canonical_score = max(0.0, 1.0 - alt_penalty)

            if version_tags:
                combined_lc = (raw_title + " " + raw_author).lower()
                version_match = sum(1 for v in version_tags if v in combined_lc)
                canonical_score = min(1.0, version_match / len(version_tags))

            # ── 6. Official Score (0.0–1.0) ───────────────────────────────────
            official_score = MusicCog._official_score(raw_title, raw_author)
            release_text = f"{raw_title} {raw_author}".lower()
            if any(sig in release_text for sig in (
                "official audio", "official lyric", "lyric video",
                "lyrics", "lyrical", "audio",
            )):
                official_score = min(1.0, official_score + 0.15)

            # ── 7. Search Index Soft Priority (0.0–1.0) ───────────────────────
            # Rank-based popularity — tighter decay to not crush later high-quality hits
            popularity_score = max(0.0, 1.0 - (rank_idx * 0.08))

            # ── 8. Duration Score (0.0–1.0) ───────────────────────────────────
            if 100_000 <= length_ms <= 360_000:
                duration_score = 1.0
            elif 60_000 <= length_ms < 100_000:
                duration_score = 0.5
            elif length_ms < 60_000:
                duration_score = 0.1
            else:
                duration_score = max(0.0, 1.0 - (length_ms - 360_000) / 2_000_000)

            # ── Shorts Penalty ─────────────────────────────────────────────────
            shorts_penalty = 0.5 if MusicCog._is_shorts(uri, raw_title) else 0.0

            # ── FINAL SCORE ────────────────────────────────────────────────────
            # Weights mirror commit e468fd3: relevance is the dominant factor (0.60 total)
            final = (
                relevance_score   * 0.35   # primary title relevance
                + relevance_score * 0.25   # title component doubled (dominant)
                + artist_score    * 0.15
                + canonical_score * 0.10
                + official_score  * 0.07
                + popularity_score * 0.04
                + duration_score  * 0.04
                + exact_title_bonus
                + spotify_bonus
                - shorts_penalty
                - (alt_penalty * 0.60)
            )

            if relevance_score < 0.10 and not norm_artist_intent and not spotify_bonus:
                final = min(final, 0.05)

            scored.append((final, rank_idx, track, {
                "relevance": round(relevance_score, 3),
                "artist": round(artist_score, 3),
                "canonical": round(canonical_score, 3),
                "official": round(official_score, 3),
                "popularity": round(popularity_score, 3),
                "exact": round(exact_title_bonus, 3),
                "spot_bonus": round(spotify_bonus, 3),
                "final": round(final, 3),
            }))

        if not scored:
            # All candidates were rejected — return first non-stream as emergency fallback
            for tr in tracks:
                if not getattr(tr, "is_stream", False):
                    print(f"[Rank] ⚠️ All candidates rejected, emergency fallback to: '{tr.title}'")
                    return {"type": "single", "track": tr, "all_tracks": [tr]}
            return {"type": "error", "message": "No playable results found"}

        # Sort by final score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        all_ranked_tracks = [t for _, _, t, _ in scored]

        # ── Structured Logging ────────────────────────────────────────────────
        print(f"\n━━━━━━━━ SEARCH RANKING ━━━━━━━━")
        print(f"QUERY: \"{raw_query}\"")
        for i, (final, ri, tr, dbg) in enumerate(scored[:5]):
            print(f"\n  #{i+1} [{ri}] {tr.title[:60]} — {tr.author or 'N/A'}")
            print(f"       relevance={dbg['relevance']} artist={dbg['artist']} "
                  f"canonical={dbg['canonical']} official={dbg['official']} "
                  f"spot_bonus={dbg['spot_bonus']} FINAL={dbg['final']}")
        # Decision log printed below after confidence check


        best_final, _, best_track, best_dbg = scored[0]

        # ── Confidence & Disambiguation ────────────────────────────────────────
        # Decision rules:
        #   score >= 0.70              → always auto-play (high confidence, best wins)
        #   score >= 0.45, gap >= 0.06 → auto-play (moderate lead)
        #   score < 0.30               → always show menu (too uncertain)
        #   otherwise                  → show menu (close scores, ambiguous)
        #
        # NOTE: gap check alone must NOT override a high score. When a search for
        # "kalyani" returns 5 songs all named Kalyani, they all score ~0.85.
        # That is not ambiguity — the top result IS the right answer.
        if len(scored) > 1:
            second_final = scored[1][0]
            gap = best_final - second_final

            if best_final >= 0.70:
                # High confidence — top result wins even if others score similarly
                print(f"[Rank] ✅ HIGH confidence ({best_final:.3f}), auto-playing: \"{best_track.title}\"")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                return {"type": "single", "track": best_track, "all_tracks": all_ranked_tracks}

            elif best_final >= 0.45 and gap >= 0.06:
                # Moderate confidence with a clear gap over second place
                print(f"[Rank] ✅ MODERATE confidence ({best_final:.3f}, gap={gap:.3f}), auto-playing: \"{best_track.title}\"")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                return {"type": "single", "track": best_track, "all_tracks": all_ranked_tracks}

            elif best_final < 0.30:
                # Low confidence — let user choose
                print(f"[Rank] ❓ LOW confidence ({best_final:.3f}), showing menu")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                candidates = [t for _, _, t, _ in scored[:5]]
                return {"type": "ambiguous", "tracks": candidates, "all_tracks": all_ranked_tracks}

            else:
                # Mid-range score with close competitors — show menu
                print(f"[Rank] ❓ AMBIGUOUS ({best_final:.3f}, gap={gap:.3f}), showing menu")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                candidates = [t for _, _, t, _ in scored[:5]]
                return {"type": "ambiguous", "tracks": candidates, "all_tracks": all_ranked_tracks}
        else:
            print(f"[Rank] ✅ Only 1 candidate, auto-playing: \"{best_track.title}\"")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        return {"type": "single", "track": best_track, "all_tracks": all_ranked_tracks}


    async def _resolve_legacy(self, query: str, requester: discord.Member, gp=None) -> dict:
        """
        Resolve a search query or URL to track(s).
        Strategy:
          1. If URL, load directly.
          2. If query has explicit prefix (ytmsearch: etc.), use it directly.
          3. Otherwise:
             a. Optionally resolve artist+title via Spotify popularity API.
             b. Search ytmsearch: (YouTube Music catalog) first — most reliable for music.
             c. Fallback to ytsearch: only if ytmsearch yields low-confidence results.
             d. scsearch:/spsearch: as tertiary fallbacks.
          4. Run deterministic ranking engine on each candidate pool.
          5. Return highest-confidence result.
        """
        import time

        nodes = wavelink.Pool.nodes
        if not nodes:
            print("[Music] ❌ No Lavalink nodes connected!")
            return {"type": "error", "message": "No Lavalink node connected"}

        # ── URL normalization ──────────────────────────────────────────────────
        if "music.youtube.com" in query:
            query = query.replace("music.youtube.com", "www.youtube.com")
        if "youtu.be/" in query:
            video_id = query.split("youtu.be/")[1].split("?")[0].split("&")[0]
            query = f"https://www.youtube.com/watch?v={video_id}"

        is_url = query.startswith("http://") or query.startswith("https://")

        def _tag(tr):
            try:
                tr.extras.requester = requester.display_name
            except Exception:
                pass
            return tr

        # ── Direct URL ────────────────────────────────────────────────────────
        if is_url:
            try:
                results = await wavelink.Playable.search(query)
                if isinstance(results, wavelink.Playlist):
                    return {"type": "playlist", "tracks": [_tag(tr) for tr in results.tracks]}
                elif results:
                    return {"type": "single", "track": _tag(results[0])}
            except Exception as e:
                print(f"[Music] URL search error: {e}")
            return {"type": "error", "message": "Could not resolve URL"}

        # ── Explicit prefix bypass ─────────────────────────────────────────────
        explicit_prefixes = ("ytsearch:", "ytmsearch:", "spsearch:", "dzsearch:", "amsearch:")
        if any(query.startswith(p) for p in explicit_prefixes):
            try:
                res = await wavelink.Playable.search(query)
                if gp:
                    gp.metrics["load_start"] = gp.metrics.get("load_start", time.time())
                    gp.metrics["load_end"] = time.time()
                if res:
                    ranked = self._rank_tracks(query.split(":", 1)[1], res)
                    if ranked.get("type") in ("single", "ambiguous"):
                        if ranked["type"] == "single":
                            return {"type": "single", "track": _tag(ranked["track"])}
                        return {"type": "ambiguous", "tracks": [_tag(t) for t in ranked["tracks"]]}
            except Exception as e:
                print(f"[Music] Explicit prefix search error: {e}")
            return {"type": "error", "message": "No results found"}

        # ── Clean query of generic filler before searching ─────────────────────
        filler_re = r"\b(full song|full video song|official song|official music video|official audio|official video|music video|mp3|hd|4k)\b"
        clean_q = re.sub(filler_re, "", query, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r"\s+", " ", clean_q).strip() or query.strip()

        # ── Optional Spotify popularity enrichment ─────────────────────────────
        spotify_enriched = None
        if sp:
            try:
                loop = asyncio.get_running_loop()
                sp_res = await loop.run_in_executor(
                    None, lambda: sp.search(q=clean_q, type="track", limit=5)
                )
                items = (sp_res or {}).get("tracks", {}).get("items", [])
                if items:
                    items.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                    top = items[0]
                    pop = top.get("popularity", 0)
                    if pop >= 25:
                        artist = top["artists"][0]["name"]
                        title = top["name"]
                        spotify_enriched = f"{artist} - {title}"
                        print(f"[Music] 🌟 Spotify resolved ({pop}/100): '{spotify_enriched}'")
            except Exception as e:
                print(f"[Music] Spotify enrichment info: {e}")

        # ── Search priority ladder ─────────────────────────────────────────────
        # ytmsearch: targets the YouTube Music catalog which contains verified
        # artist releases, label uploads, and topic channels — far better signal
        # quality than raw ytsearch: for music queries.
        # We only fall back to ytsearch: when ytmsearch: yields low confidence.
        if spotify_enriched:
            search_ladder = [
                ("ytmsearch", f"ytmsearch:{spotify_enriched}"),
                ("ytmsearch_raw", f"ytmsearch:{clean_q}"),
                ("ytsearch_enriched", f"ytsearch:{spotify_enriched}"),
                ("ytsearch", f"ytsearch:{clean_q}"),
                ("spsearch", f"spsearch:{clean_q}"),
            ]
        else:
            search_ladder = [
                ("ytmsearch", f"ytmsearch:{clean_q}"),
                ("ytsearch", f"ytsearch:{clean_q}"),
                ("spsearch", f"spsearch:{clean_q}"),
            ]

        best_result = None
        best_confidence = -1.0

        for source_name, prefix in search_ladder:
            try:
                t0 = time.time()
                res = await wavelink.Playable.search(prefix)
                t1 = time.time()
                print(f"[Music] 🔍 {source_name} ({t1-t0:.2f}s) → {len(res) if res else 0} results")

                if gp:
                    gp.metrics["load_start"] = t0
                    gp.metrics["load_end"] = t1

                if not res:
                    continue

                ranked = self._rank_tracks(query, res)
                if ranked.get("type") == "error":
                    continue

                if ranked["type"] == "single":
                    # Estimate confidence from score position
                    # Re-run to get the top score value for comparison
                    track = ranked["track"]
                    # Use a simple heuristic: if we got a clean single result from ytmsearch, trust it
                    if source_name in ("ytmsearch", "ytmsearch_raw") and best_result is None:
                        # ytmsearch is trusted catalog — use result immediately if title matches
                        norm_q = self._normalize_query(query)
                        norm_t = self._normalize_query(track.title)
                        sim = difflib.SequenceMatcher(None, norm_q, norm_t).ratio()
                        if sim >= 0.25 or self._official_score(track.title, track.author) >= 0.5:
                            return {"type": "single", "track": _tag(track)}
                        # Low similarity even from ytmsearch — keep searching
                        best_result = ranked
                        best_confidence = sim
                    elif best_result is None:
                        best_result = ranked
                        norm_q = self._normalize_query(query)
                        norm_t = self._normalize_query(track.title)
                        best_confidence = difflib.SequenceMatcher(None, norm_q, norm_t).ratio()

                elif ranked["type"] == "ambiguous":
                    if best_result is None:
                        best_result = ranked
                    # If we already have a result but it's ambiguous too, keep the first

            except Exception as e:
                print(f"[Music] Search error ({source_name}): {e}")
                continue

        # Return whatever we found
        if best_result:
            if best_result["type"] == "single":
                return {"type": "single", "track": _tag(best_result["track"])}
            elif best_result["type"] == "ambiguous":
                return {"type": "ambiguous", "tracks": [_tag(t) for t in best_result["tracks"]]}



    async def _resolve_merged(self, query: str, requester: discord.Member, gp=None) -> dict:
        """Resolve URLs directly and rank merged results from all providers."""
        import time

        nodes = wavelink.Pool.nodes
        if not nodes:
            return {"type": "error", "message": "No Lavalink node connected."}

        original_query = (query or "").strip()
        if not original_query:
            return {"type": "error", "message": "Please enter a song name or URL."}

        if "music.youtube.com" in query:
            query = query.replace("music.youtube.com", "www.youtube.com")
        if "youtu.be/" in query:
            video_id = query.split("youtu.be/", 1)[1].split("?", 1)[0].split("&", 1)[0]
            query = f"https://www.youtube.com/watch?v={video_id}"

        def tag(track):
            try:
                if getattr(track, "extras", None) is None:
                    track.extras = {}
                track.extras.requester = requester.display_name
            except Exception:
                pass
            return track

        if query.startswith(("http://", "https://")):
            try:
                results = await wavelink.Playable.search(query)
                if isinstance(results, wavelink.Playlist):
                    tracks = [tag(track) for track in results.tracks if track]
                    return ({"type": "playlist", "tracks": tracks} if tracks else
                            {"type": "error", "message": "Playlist contains no playable tracks."})
                if results:
                    return {"type": "single", "track": tag(results[0])}
            except Exception as exc:
                return {"type": "error", "message": f"Could not resolve URL: {exc}"}
            return {"type": "error", "message": "Could not resolve the supplied URL."}

        prefixes = ("ytsearch:", "ytmsearch:", "spsearch:", "scsearch:", "dzsearch:", "amsearch:")
        if query.lower().startswith(prefixes):
            try:
                provider, search_text = query.split(":", 1)
                results = await wavelink.Playable.search(search_text, source=provider)
                if not results:
                    return {"type": "error", "message": "No results found."}
                ranked = self._rank_tracks(search_text, list(results))
                if ranked.get("type") == "single":
                    return {"type": "single", "track": tag(ranked["track"])}
                if ranked.get("type") == "ambiguous":
                    return {"type": "ambiguous", "tracks": [tag(track) for track in ranked["tracks"]]}
            except Exception as exc:
                print(f"[Music] Explicit search failed: {exc}")
            return {"type": "error", "message": "No playable results found."}

        filler = re.compile(
            r"\b(full song|full video song|official song|official music video|official audio|"
            r"official video|music video|audio|video|song|track|music|mp3|hd|4k)\b",
            re.IGNORECASE,
        )
        clean_query = re.sub(r"\s+", " ", filler.sub("", original_query)).strip() or original_query

        spotify_query = None
        if sp:
            try:
                loop = asyncio.get_running_loop()
                spotify_result = await loop.run_in_executor(
                    None, lambda: sp.search(q=clean_query, type="track", limit=5)
                )
                items = spotify_result.get("tracks", {}).get("items", [])
                if items and items[0].get("artists"):
                    artist = items[0]["artists"][0].get("name", "")
                    title = items[0].get("name", "")
                    if artist and title:
                        spotify_query = f"{artist} - {title}"
            except Exception as exc:
                print(f"[Music] Spotify enrichment unavailable: {exc}")

        searches = [
            ("ytmsearch", clean_query),
            ("ytsearch", clean_query),
            ("spsearch", clean_query),
        ]
        if spotify_query:
            searches.extend([
                ("ytmsearch_spotify", spotify_query),
                ("ytsearch_spotify", spotify_query),
            ])

        async def search_one(source, search_query):
            started = time.time()
            try:
                provider = source.removesuffix("_spotify")
                results = await wavelink.Playable.search(search_query, source=provider)
                tracks = list(results) if results else []
                print(f"[Music] {source}: {len(tracks)} results ({time.time() - started:.2f}s)")
                return source, tracks
            except Exception as exc:
                print(f"[Music] {source} failed: {exc}")
                return source, []

        search_results = await asyncio.gather(*(search_one(*item) for item in searches))
        candidates = {}
        for source, tracks in search_results:
            for rank, track in enumerate(tracks[:20]):
                identifier = getattr(track, "identifier", None) or getattr(track, "uri", None) or getattr(track, "title", "")
                key = str(identifier).lower()
                if key and (key not in candidates or rank < candidates[key]["rank"]):
                    candidates[key] = {"track": track, "source": source, "rank": rank}

        artist_intent, title_intent, requested_versions = self._extract_intent(clean_query)
        normalized_query = self._normalize_query(clean_query)
        normalized_title_intent = self._normalize_query(title_intent or clean_query)
        normalized_artist_intent = self._normalize_query(artist_intent or "")
        query_words = set(normalized_title_intent.split())
        scored = []
        for item in candidates.values():
            track = item["track"]
            title = getattr(track, "title", "") or ""
            author = getattr(track, "author", "") or ""
            uri = getattr(track, "uri", "") or ""
            if getattr(track, "is_stream", False) or self._is_non_music(title, author):
                continue
            raw = f"{title} {author} {uri}".lower()
            if ("/shorts/" in uri.lower() or " shorts " in f" {raw} ") and "short" not in normalized_query:
                continue
            normalized_title = self._normalize_query(title)
            normalized_author = self._normalize_query(author)
            title_words = set(normalized_title.split())
            author_words = set(normalized_author.split())
            overlap = (len(query_words.intersection(title_words)) / len(query_words)) if query_words else 0
            similarity = difflib.SequenceMatcher(None, normalized_title_intent, normalized_title).ratio()
            title_relevance = 1.0 if normalized_title == normalized_title_intent else max(
                similarity * 0.55 + overlap * 0.45,
                0.90 if normalized_title_intent and normalized_title_intent in normalized_title else 0,
            )
            artist_score = 0.0
            if normalized_artist_intent:
                artist_overlap = len(set(normalized_artist_intent.split()).intersection(normalized_author.split())) / len(normalized_artist_intent.split())
                artist_score = difflib.SequenceMatcher(None, normalized_artist_intent, normalized_author).ratio() * 0.6 + artist_overlap * 0.4
                if normalized_artist_intent in normalized_author:
                    artist_score = min(1.0, artist_score + 0.3)
            elif normalized_title_intent:
                artist_score = len(query_words.intersection(title_words | author_words)) / len(query_words)

            author_relevance = difflib.SequenceMatcher(
                None, normalized_title_intent, normalized_author
            ).ratio()
            author_overlap = (
                len(query_words.intersection(author_words)) / len(query_words)
                if query_words else 0
            )
            if not normalized_artist_intent and author_overlap:
                title_relevance = max(title_relevance, author_relevance * 0.75 + author_overlap * 0.25)

            # A provider's popularity or official label must not make an unrelated title playable.
            if normalized_title_intent and title_relevance < 0.20 and artist_score < 0.35:
                continue
            unwanted = ("instrumental", "karaoke", "cover", "remix", "slowed", "reverb", "nightcore", "mashup", "trailer", "shorts", "tiktok")
            alternate_penalty = min(1.0, sum(word in raw and word not in requested_versions for word in unwanted) * 0.25)
            length = getattr(track, "length", 0) or 0
            duration = 1.0 if 120000 <= length <= 360000 else 0.65 if 60000 <= length < 120000 else 0.75 if length <= 600000 else 0.25
            source_bonus = {"ytsearch": 0.08, "ytsearch_spotify": 0.08, "ytmsearch": 0.06, "ytmsearch_spotify": 0.06, "spsearch": 0.04, "scsearch": 0.02}.get(item["source"], 0)
            final = (title_relevance * 0.50 + artist_score * 0.15 + (1 - alternate_penalty) * 0.15 + self._official_score(title, author) * 0.08 + max(0, 1 - item["rank"] * 0.035) * 0.05 + duration * 0.07 + source_bonus - alternate_penalty * 0.35)
            scored.append((final, track))

        if not scored:
            return {"type": "error", "message": "No suitable music result found. Try: Artist - Song."}
        scored.sort(key=lambda item: item[0], reverse=True)
        return {"type": "single", "track": tag(scored[0][1])}

    async def _resolve(self, query: str, requester: discord.Member, gp=None) -> dict:
        """Resolve query or URL to playable track(s), prioritizing vocal/studio audio releases."""
        import time

        if not wavelink.Pool.nodes:
            return {"type": "error", "message": "No Lavalink node connected."}

        raw_query = (query or "").strip()
        if not raw_query:
            return {"type": "error", "message": "Please enter a song name or URL."}

        cleaned = clean_spotify_url(clean_youtube_watch_url(raw_query))

        def tag(track):
            try:
                if getattr(track, "extras", None) is None:
                    track.extras = {}
                track.extras.requester = requester.display_name
            except Exception:
                pass
            return track

        # Direct HTTP/HTTPS URL
        if is_http_url(cleaned):
            try:
                results = await asyncio.wait_for(wavelink.Playable.search(cleaned), timeout=35)
                if isinstance(results, wavelink.Playlist):
                    tracks = [tag(track) for track in results.tracks if track]
                    return ({"type": "playlist", "tracks": tracks} if tracks else
                            {"type": "error", "message": "Playlist contains no playable tracks."})
                if results:
                    return {"type": "single", "track": tag(results[0])}
            except Exception as exc:
                return {"type": "error", "message": f"Could not resolve URL: {exc}"}
            return {"type": "error", "message": "Could not resolve the supplied URL."}

        # Explicit prefix search if provided (e.g. ytmsearch:, ytsearch:)
        prefixes = ("ytsearch:", "ytmsearch:", "dzsearch:", "amsearch:")
        explicit_prefix = cleaned.lower().startswith(prefixes)

        search_text = cleaned
        spotify_top = None

        if explicit_prefix:
            provider, search_text = cleaned.split(":", 1)
            sources_to_try = [(search_text, provider)]
        else:
            filler = re.compile(
                r"\b(full song|full video song|official song|official music video|official audio|"
                r"official video|music video|audio|video|song|track|music|mp3|hd|4k)\b",
                re.IGNORECASE,
            )
            search_text = re.sub(r"\s+", " ", filler.sub("", cleaned)).strip() or cleaned

            if sp:
                try:
                    loop = asyncio.get_running_loop()
                    sp_res = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: sp.search(q=search_text, type="track", limit=5)),
                        timeout=2.0,
                    )
                    items = (sp_res or {}).get("tracks", {}).get("items", [])
                    if items:
                        items.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                        top_item = items[0]
                        artist_names = [a.get("name", "") for a in top_item.get("artists", []) if a.get("name")]
                        spotify_top = {
                            "title": top_item.get("name", ""),
                            "artists": artist_names,
                            "popularity": top_item.get("popularity", 0),
                        }
                        print(f"[Music] 🌟 Spotify top hit: '{top_item.get('name')}' by {', '.join(artist_names)} (popularity={top_item.get('popularity')}/100)")
                except Exception as exc:
                    print(f"[Music] Spotify lookup notice: {exc}")

            sources_to_try = []
            if spotify_top and spotify_top.get("popularity", 0) >= 30 and spotify_top.get("artists"):
                enriched_query = f"{spotify_top['title']} {spotify_top['artists'][0]}"
                sources_to_try.append((enriched_query, wavelink.TrackSource.YouTubeMusic))

            sources_to_try.append((search_text, wavelink.TrackSource.YouTubeMusic))
            sources_to_try.append((search_text, wavelink.TrackSource.YouTube))

        started = time.time()
        results = []
        ranked = {"type": "error", "message": "No suitable music result found."}

        for term, src in sources_to_try:
            try:
                raw = await asyncio.wait_for(
                    wavelink.Playable.search(term, source=src), timeout=35
                )

                if not raw:
                    continue

                candidate_results = list(raw)
                finished = time.time()
                print(f"[Music] {src} ('{term}'): {len(candidate_results)} results ({finished - started:.2f}s)")

                if gp:
                    gp.metrics["load_start"] = started
                    gp.metrics["load_end"] = finished

                candidate_ranked = self._rank_tracks(search_text, candidate_results, spotify_top=spotify_top)

                if candidate_ranked.get("type") in ("single", "ambiguous"):
                    results = candidate_results
                    ranked = candidate_ranked
                    break

            except Exception as exc:
                print(f"[Music] {src} search failed: {exc}")
                continue

        # Fallback: Video ID search if query had a video ID
        if ranked.get("type") == "error":
            vid = youtube_video_id(cleaned)
            if vid:
                try:
                    raw = await asyncio.wait_for(
                        wavelink.Playable.search(vid, source=wavelink.TrackSource.YouTube),
                        timeout=35,
                    )
                    if raw:
                        candidate_results = list(raw)
                        candidate_ranked = self._rank_tracks(search_text, candidate_results, spotify_top=spotify_top)
                        if candidate_ranked.get("type") in ("single", "ambiguous"):
                            results = candidate_results
                            ranked = candidate_ranked
                except Exception as exc:
                    print(f"[Music] Video ID fallback search failed: {exc}")

        if ranked.get("type") == "single":
            return {"type": "single", "track": tag(ranked["track"])}
        if ranked.get("type") == "ambiguous":
            return {"type": "ambiguous", "tracks": [tag(track) for track in ranked["tracks"]]}

        # Fallback to first non-stream track if ranker was too strict
        if results:
            for tr in results:
                if not getattr(tr, "is_stream", False):
                    return {"type": "single", "track": tag(tr)}

        return {"type": "error", "message": ranked.get("message", "No suitable music result found.")}

    # ── Slash Commands ────────────────────────────────────────────────────────


    @app_commands.command(name="play", description="Play a song or playlist from YouTube, Spotify, or SoundCloud.")
    @app_commands.describe(query="YouTube URL, Spotify link, or song name to search")
    async def play(self, interaction: discord.Interaction, query: str):
        import time
        t_cmd = time.time()
        gp = self.get_gp(interaction.guild.id)
        gp.metrics.clear()
        gp.metrics["cmd_recv"] = t_cmd

        # 1. State: Searching
        await interaction.response.send_message(embed=embed_info("🔍 Searching", f"Looking for `{query}`..."))
        gp.metrics["search_start"] = time.time()

        if not interaction.user.voice:
            return await interaction.edit_original_response(embed=embed_error("Join a voice channel first."))

        user_channel = interaction.user.voice.channel

        # 2. Connect (hands off from Radio first if Radio is currently playing)
        gp.metrics["voice_start"] = time.time()
        vc = get_player(interaction.guild)
        try:
            if not vc:
                vc = await get_or_create_music_vc(self.bot, interaction.guild, user_channel, self_deaf=True)
            elif vc.channel != user_channel:
                await vc.move_to(user_channel)
        except (TimeoutError, asyncio.TimeoutError) as te:
            print(f"[Music] Voice connection timed out for {interaction.guild.name}: {te}")
            return await interaction.edit_original_response(
                embed=embed_error("⏱️ Voice connection timed out. Please try again.")
            )
        except Exception as exc:
            print(f"[Music] Voice connection failed for {interaction.guild.name}: {exc}")
            return await interaction.edit_original_response(
                embed=embed_error(f"Could not connect to voice channel: {exc}")
            )
        gp.metrics["voice_end"] = time.time()

        # 3. Resolve query
        result = await self._resolve(query, interaction.user, gp=gp)
        gp.metrics["search_end"] = time.time()

        if result["type"] == "error":
            return await interaction.edit_original_response(embed=embed_error(result.get("message", "No tracks found.")))
            
        if result["type"] == "ambiguous":
            view = TrackSelectView(result["tracks"], self._execute_play, vc, gp)
            embed = embed_info("🤔 Ambiguous Search", "Found multiple exact matches. Please select the specific track you meant:")
            return await interaction.edit_original_response(embed=embed, view=view)
            
        tracks = result.get("tracks", [])
        if result["type"] == "single":
            tracks = [result["track"]]

        await self._execute_play(interaction, vc, tracks, gp)

    async def _execute_play(self, interaction: discord.Interaction, vc, tracks, gp):
        if not tracks: return
        gp.text_channel = interaction.channel

        if vc.paused:
            for tr in tracks:
                await vc.queue.put_wait(tr)
            await vc.pause(False)
            embed = embed_success("Resumed", f"Resumed and added **{len(tracks)}** track(s) to the queue.")
            if interaction.response.is_done(): await interaction.edit_original_response(embed=embed, view=None)
            else: await interaction.response.send_message(embed=embed)
        elif not vc.playing:
            first_track = tracks[0]
            for tr in tracks[1:]:
                await vc.queue.put_wait(tr)
            
            import time
            gp.metrics["play_cmd"] = time.time()
            gp.last_queued_identifier = first_track.identifier
            
            print(f"\n━━━━━━━━ TRACK SELECTION ━━━━━━━━")
            print(f"Selected: {first_track.title}")
            print(f"Artist: {first_track.author}")
            print(f"Identifier: {first_track.identifier}")
            print(f"URI: {first_track.uri}")
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            
            # Start every new song with completely clean audio.
            # This prevents any stale Lavalink filter state from carrying over.
            try:
                await vc.set_filters(wavelink.Filters())
                gp.current_filter = "Normal"
            except Exception as filter_exc:
                print(f"[Music] Filter reset warning: {filter_exc}")

            await vc.set_volume(100)
            await vc.play(first_track)
            import asyncio
            asyncio.create_task(self._wait_for_audio_flow(vc, gp))
            
            gp.loading_track = first_track
            embed, _ = gp.build_embed(vc, first_track)
            view = MusicControlView(gp)
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=view)
                try:
                    gp.panel_message = await interaction.original_response()
                except Exception:
                    pass
            else:
                await interaction.response.send_message(embed=embed, view=view)
                try:
                    gp.panel_message = await interaction.original_response()
                except Exception:
                    pass
        else:
            for tr in tracks:
                await vc.queue.put_wait(tr)
            names = ", ".join(f"**{t.title}**" for t in tracks[:3])
            extra = f" + {len(tracks) - 3} more" if len(tracks) > 3 else ""
            embed = embed_success("Added to Queue", f"Added {names}{extra} to queue")
            if interaction.response.is_done(): await interaction.edit_original_response(embed=embed, view=None)
            else: await interaction.response.send_message(embed=embed)

    @app_commands.command(name="random", description="Play a random trending song.")
    async def random(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send(embed=embed_error("Join a voice channel first."), ephemeral=True)

        user_channel = interaction.user.voice.channel
        vc: Optional[wavelink.Player] = get_player(interaction.guild)

        if not vc:
            try:
                await set_india_voice_region(user_channel)
                vc = await get_or_create_music_vc(self.bot, interaction.guild, user_channel)
            except Exception as e:
                return await interaction.followup.send(embed=embed_error(f"Could not connect: {e}"), ephemeral=True)
        elif vc.channel != user_channel:
            try:
                await set_india_voice_region(user_channel)
                await vc.move_to(user_channel)
            except Exception as e:
                return await interaction.followup.send(embed=embed_error(f"Could not move to your channel: {e}"), ephemeral=True)

        try:
            await vc.set_volume(100)
        except Exception:
            pass

        queries = [
            "spsearch:Today Top Hits",
            "spsearch:Viral Hits 2026",
            "ytmsearch:trending songs 2025",
            "ytmsearch:top hits playlist",
        ]
        query = random.choice(queries)
        tracks = await self._resolve(query, interaction.user)
        if not tracks:
            return await interaction.followup.send(embed=embed_error("Failed to find trending songs."), ephemeral=True)
        track = random.choice(tracks)

        gp = self.get_gp(interaction.guild.id)
        gp.text_channel = interaction.channel

        if vc.paused:
            await vc.queue.put_wait(track)
            await vc.pause(False)
            embed = embed_success("Resumed", f"Resumed and added **{track.title}** to queue.")
            await interaction.followup.send(embed=embed)
        elif not vc.playing:
            try:
                await vc.set_filters(wavelink.Filters())
                gp.current_filter = "Normal"
            except Exception as filter_exc:
                print(f"[Music] Random-play filter reset warning: {filter_exc}")

            # Play directly — no queue round-trip for instant start
            await vc.play(track, volume=100)
            embed = embed_success("🎲 Random Song", f"Now playing **{track.title}**")
            await interaction.followup.send(embed=embed)
        else:
            await vc.queue.put_wait(track)
            embed = embed_success("🎲 Random Song", f"Added **{track.title}** to queue")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="stop", description="Stop music and disconnect.")
    async def stop(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc:
            return await interaction.response.send_message(embed=embed_error("Not connected."), ephemeral=True)
        gp = self.get_gp(interaction.guild.id)
        gp.mode_247 = False
        if vc.channel:
            await set_voice_channel_status(self.bot, vc.channel.id, "")
        vc.queue.clear()
        await vc.disconnect()
        # FEATURE: an explicit stop also counts as "music session finished" —
        # hand the channel back to Radio if it was paused for this handoff.
        await restore_voice_from(self.bot, interaction.guild, "music")
        await interaction.response.send_message(embed=embed_success("Stopped", "Stopped and disconnected."))

    @app_commands.command(name="skip", description="Skip the current track.")
    async def skip(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=embed_error("Nothing playing."), ephemeral=True)
        await vc.skip(force=True)
        await interaction.response.send_message(embed=embed_success("Skipped", "Skipped track."))

    @app_commands.command(name="pause", description="Pause the current track.")
    async def pause(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=embed_error("Nothing playing."), ephemeral=True)
        await vc.pause(True)
        if vc.channel and vc.current:
            await set_voice_channel_status(self.bot, vc.channel.id, f"⏸️ Paused: {vc.current.title[:85]}")
        await interaction.response.send_message(embed=embed_success("Paused", "Paused playback."))

    @app_commands.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc or not vc.paused:
            return await interaction.response.send_message(embed=embed_error("Not paused."), ephemeral=True)
        await vc.pause(False)
        if vc.channel and vc.current:
            st = f"🎶 {vc.current.title}" + (f" - {vc.current.author}" if vc.current.author else "")
            await set_voice_channel_status(self.bot, vc.channel.id, st[:100])
        await interaction.response.send_message(embed=embed_success("Resumed", "Resumed playback."))

    @app_commands.command(name="volume", description="Set the volume (0–100).")
    @app_commands.describe(level="Volume level 0-100")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 0 <= level <= 100:
            return await interaction.response.send_message(embed=embed_error("Volume must be 0–100."), ephemeral=True)
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc:
            return await interaction.response.send_message(embed=embed_error("Not connected."), ephemeral=True)
        await vc.set_volume(level)
        await interaction.response.send_message(embed=embed_success("Volume", f"Volume set to **{level}%**"))

    @app_commands.command(name="filter", description="Open the audio filter control panel.")
    async def filter_cmd(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc:
            return await interaction.response.send_message(embed=embed_error("Bot is not connected to voice."), ephemeral=True)
        gp = self.get_gp(interaction.guild.id)
        filters_status = [
            f"• **Bass Boost:** `{'Active' if gp.current_filter == 'Bassboost' else 'Off'}`",
            f"• **Nightcore:** `{'Active' if gp.current_filter == 'Nightcore' else 'Off'}`",
            f"• **8D Audio:** `{'Active' if gp.current_filter == '8D Audio' else 'Off'}`",
            f"• **Vaporwave:** `{'Active' if gp.current_filter == 'Vaporwave' else 'Off'}`",
        ]
        embed = discord.Embed(
            title="🎚  Audio Filters",
            description="\n".join(filters_status),
            color=C.BRAND
        )
        embed.set_footer(text=f"Current filter: {gp.current_filter}")
        await interaction.response.send_message(embed=embed, view=AudioFilterView(gp), ephemeral=True)

    @app_commands.command(name="queue", description="Show the music queue.")
    async def queue_cmd(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc:
            return await interaction.response.send_message(embed=embed_error("Not connected."), ephemeral=True)

        if not vc.current and vc.queue.is_empty:
            return await interaction.response.send_message(embed=embed_info("Queue Empty", "The playback queue is currently empty."))

        lines = []
        if vc.current:
            dur_str = format_ms(vc.current.length)
            lines.append(f"**Now Playing:**\n[{vc.current.title}]({vc.current.uri}) · `{dur_str}`\n")

        q_items = list(vc.queue)[:15]
        if q_items:
            lines.append("**Up Next:**")
            for i, t in enumerate(q_items, 1):
                dur = format_ms(t.length)
                lines.append(f"`{i}.` **{t.title[:65]}** · `{dur}`")
            if vc.queue.count > 15:
                lines.append(f"\n*... and {vc.queue.count - 15} more tracks in queue*")

        embed = discord.Embed(
            title=f"📜  Playback Queue — {interaction.guild.name}",
            description="\n".join(lines),
            color=C.BRAND
        )
        embed.set_footer(text=f"Total: {vc.queue.count + (1 if vc.current else 0)} tracks in session")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Show the now playing panel with controls.")
    async def nowplaying(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=embed_error("Nothing is currently playing."), ephemeral=True)

        gp = self.get_gp(interaction.guild.id)
        embed, _ = gp.build_embed(vc, vc.current)
        view = MusicControlView(gp)
        await interaction.response.send_message(embed=embed, view=view)
        gp.panel_message = await interaction.original_response()

    @app_commands.command(name="loop", description="Toggle loop mode (single → queue → off).")
    async def loop(self, interaction: discord.Interaction):
        gp = self.get_gp(interaction.guild.id)
        modes = [None, "single", "queue"]
        cur = gp.loop_mode
        gp.loop_mode = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "single"
        mode_str = {"single": "Single Song", "queue": "Queue"}.get(gp.loop_mode, "Off")
        await interaction.response.send_message(embed=embed_info("Loop Mode", f"Loop mode: **{mode_str}**"))

    @app_commands.command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc or vc.queue.is_empty:
            return await interaction.response.send_message(embed=embed_error("Queue is empty."), ephemeral=True)
        items = list(vc.queue)
        random.shuffle(items)
        vc.queue.clear()
        for it in items:
            await vc.queue.put_wait(it)
        await interaction.response.send_message(embed=embed_success("Queue Shuffled", "Queue shuffled!"))

    @app_commands.command(name="remove", description="Remove a track from the queue by position.")
    @app_commands.describe(index="Position in queue (1 = first)")
    async def remove(self, interaction: discord.Interaction, index: int):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc or vc.queue.is_empty:
            return await interaction.response.send_message(embed=embed_error("Queue is empty."), ephemeral=True)
        items = list(vc.queue)
        if index < 1 or index > len(items):
            return await interaction.response.send_message(embed=embed_error(f"Index must be 1–{len(items)}."), ephemeral=True)
        removed = items.pop(index - 1)
        vc.queue.clear()
        for it in items:
            await vc.queue.put_wait(it)
        await interaction.response.send_message(embed=embed_success("Removed", f"Removed **{removed.title}**"))

    @app_commands.command(name="clear", description="Clear the entire queue.")
    async def clear(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = get_player(interaction.guild)
        if not vc:
            return await interaction.response.send_message(embed=embed_error("Not connected."), ephemeral=True)
        vc.queue.clear()
        await interaction.response.send_message(embed=embed_success("Cleared", "Queue cleared."))

    @app_commands.command(name="toggle_247", description="Toggle 24/7 mode (bot stays in VC forever).")
    async def toggle_247(self, interaction: discord.Interaction):
        gp = self.get_gp(interaction.guild.id)
        gp.mode_247 = not gp.mode_247
        status = "enabled" if gp.mode_247 else "disabled"
        await interaction.response.send_message(embed=embed_info("24/7 Mode", f"24/7 mode **{status}**"))


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
    print("🎵 Lavalink Music system loaded!")