"""
music.py — Advanced Interactive Music System for GKR Bot.
Supports YouTube URLs, YouTube playlists, Spotify tracks/playlists/albums,
raw search queries, progress bar embeds, and 3-row interactive remote control buttons.
"""

import asyncio
import os
import sys
import time
import random
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
from typing import Dict, List, Optional
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

# Spotify API configuration
SPOTIPY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
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
    except Exception as e:
        print(f"Failed to initialize Spotify: {e}")

# ── YouTube Cookie Setup ───────────────────────────────────────────────────────
# Option A: Set YOUTUBE_COOKIES_FILE=/path/to/cookies.txt  (path to a Netscape cookie file)
# Option B: Set YOUTUBE_COOKIES=<full Netscape cookie file content as a single env string>
#           On Render/Railway: paste the entire cookies.txt content as one env var value.
# If neither is set the bot still tries via player client fallbacks.

import tempfile

YOUTUBE_COOKIES_FILE = os.getenv("YOUTUBE_COOKIES_FILE", None)
_TEMP_COOKIE_FILE = None  # will hold path if we write from env string

_cookie_env_str = os.getenv("YOUTUBE_COOKIES", None)
if _cookie_env_str and not YOUTUBE_COOKIES_FILE:
    try:
        _tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        _tmp.write(_cookie_env_str.replace('\\n', '\n'))
        _tmp.close()
        _TEMP_COOKIE_FILE = _tmp.name
        print(f"\U0001f36a YouTube cookies loaded from YOUTUBE_COOKIES env var -> {_TEMP_COOKIE_FILE}")
    except Exception as _ce:
        print(f"\u26a0\ufe0f  Failed to write YOUTUBE_COOKIES to temp file: {_ce}")

_ACTIVE_COOKIE_FILE = YOUTUBE_COOKIES_FILE or _TEMP_COOKIE_FILE

print("=" * 50)
print(f"YOUTUBE_COOKIES_FILE = {YOUTUBE_COOKIES_FILE}")
print(f"TEMP_COOKIE_FILE = {_TEMP_COOKIE_FILE}")
print(f"ACTIVE_COOKIE_FILE = {_ACTIVE_COOKIE_FILE}")
print(f"Cookie Exists = {os.path.isfile(_ACTIVE_COOKIE_FILE) if _ACTIVE_COOKIE_FILE else False}")
print("=" * 50)


def normalize_youtube_url(url: str) -> str:
    """Converts YouTube Music and short links to standard youtube.com watch URLs."""
    url = url.replace("music.youtube.com", "www.youtube.com")
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0].split("&")[0]
        url = f"https://www.youtube.com/watch?v={video_id}"
    return url


def _build_ytdl_opts(noplaylist=True, fmt='bestaudio/best') -> dict:
    """Build yt-dlp options. fmt can be overridden for fallback attempts."""
    opts = {
        # Task 2 & 3: Broadest selector — no ext, codec, or format-ID restrictions.
        # Mobile clients (android/ios) serve m4a/mp4 muxed streams so 'bestaudio/best'
        # is the only selector that reliably matches what they return.
        'format': fmt,
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': noplaylist,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'source_address': '0.0.0.0',
        # Task 7: Use tv + mweb. These do not require a JS runtime and
        # are currently the most reliable for bypassing datacenter blocks
        # without triggering the "Requested format is not available" error.
        'extractor_args': {
            'youtube': {
                'player_client': ['tv', 'mweb'],
            }
        },
    }
    if _ACTIVE_COOKIE_FILE and os.path.isfile(_ACTIVE_COOKIE_FILE):
        opts['cookiefile'] = _ACTIVE_COOKIE_FILE
        print(f"\U0001f36a yt-dlp using cookies: {_ACTIVE_COOKIE_FILE}")
    return opts


ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

opts = _build_ytdl_opts()

print("\n===== YTDLP CONFIG =====")
print(opts)
print("========================\n")

ytdl = yt_dlp.YoutubeDL(opts)


class Track:
    """Represents a single music track in the queue."""
    def __init__(self, title: str, url: str, requester: discord.Member, duration: Optional[int] = None, thumbnail: Optional[str] = None):
        self.title = title
        self.url = url  # Search query, YouTube URL, or Spotify track name
        self.requester = requester
        self.duration = duration
        self.thumbnail = thumbnail


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, track: Track, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.track = track
        self.title = track.title
        self.webpage_url = track.url
        self.duration = track.duration
        self.thumbnail = track.thumbnail
        self.requester = track.requester

    @classmethod
    async def from_track(cls, track: Track, loop=None, volume=0.5):
        """Resolves the raw Track metadata to a streaming audio source right before playing."""
        loop = loop or asyncio.get_event_loop()
        # Normalize the URL before passing to yt-dlp
        query = normalize_youtube_url(track.url)

        try:
            print(f"[YTDLP] Query: {query}")
            print(f"[YTDLP] Cookies: {_ACTIVE_COOKIE_FILE}")
            print(f"[YTDLP] Cookie exists: {os.path.isfile(_ACTIVE_COOKIE_FILE) if _ACTIVE_COOKIE_FILE else False}")

            # Task 6: Two-pass fallback — try bestaudio/best first, then bare 'best'
            data = None
            last_err = None
            for fmt_attempt, fmt in enumerate(['bestaudio/best', 'best']):
                ytdl_attempt = yt_dlp.YoutubeDL(_build_ytdl_opts(fmt=fmt))
                for attempt in range(2):  # 2 retries per format
                    try:
                        data = await loop.run_in_executor(
                            None, lambda yd=ytdl_attempt, q=query: yd.extract_info(q, download=False)
                        )
                        if data:
                            print(f"[YTDLP] ✅ Format '{fmt}' succeeded on attempt {attempt+1}")
                            break
                    except Exception as e:
                        last_err = e
                        print(f"⚠️ [Format '{fmt}' attempt {attempt+1}/2] failed: {e}")
                        if attempt < 1:
                            await asyncio.sleep(1)
                if data:
                    break  # Stop trying other formats

            if not data and last_err:
                err_str = str(last_err).lower()
                # If YouTube blocked us, fallback to SoundCloud!
                if "requested format is not available" in err_str or "sign in" in err_str or "bot" in err_str or "confirm" in err_str or "signature" in err_str:
                    print(f"[YTDLP] \u26a0\ufe0f YouTube blocked extraction. Attempting SoundCloud fallback...")
                    sc_opts = _build_ytdl_opts(fmt='bestaudio/best')
                    sc_opts['default_search'] = 'scsearch'
                    
                    sc_query = query
                    # If it's a direct URL, extract the title first because SC can't search YT URLs
                    if query.startswith("http") and ("youtube" in query or "youtu.be" in query):
                        try:
                            fast_ydl = yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True})
                            info = await loop.run_in_executor(None, lambda: fast_ydl.extract_info(query, download=False))
                            if info and 'title' in info:
                                sc_query = info['title']
                        except Exception:
                            pass
                    
                    print(f"[YTDLP] Searching SoundCloud for: {sc_query}")
                    try:
                        sc_ydl = yt_dlp.YoutubeDL(sc_opts)
                        data = await loop.run_in_executor(None, lambda: sc_ydl.extract_info(sc_query, download=False))
                        if data:
                            print(f"[YTDLP] \u2705 SoundCloud fallback succeeded for {sc_query}")
                    except Exception as sc_err:
                        print(f"[YTDLP] \u26a0\ufe0f SoundCloud fallback also failed: {sc_err}")
                
                if not data:
                    raise last_err

        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            raise Exception(f"Failed to get audio: {err}")

        if not data:
            raise Exception("No data returned from YouTube. Try again or use a different song.")

        if 'entries' in data:
            entries = [e for e in data.get('entries', []) if e]
            if not entries:
                raise Exception("No search results found.")
            data = entries[0]

        if not data:
            raise Exception("Could not load audio data for this track.")

        # Task 4 & 5: Get the direct stream URL and log format details
        filename = data.get('url')
        fmt_id   = data.get('format_id', 'unknown')
        vcodec   = data.get('vcodec', 'none')
        acodec   = data.get('acodec', 'none')
        ext      = data.get('ext', 'unknown')
        print(f"[YTDLP] ✅ Selected format_id={fmt_id} ext={ext} vcodec={vcodec} acodec={acodec}")
        print(f"[YTDLP] Stream URL (first 80 chars): {str(filename)[:80]}")

        if not filename:
            raise Exception("No streamable URL found for this track.")

        track.title = data.get('title', track.title)
        track.duration = data.get('duration', track.duration)
        track.thumbnail = data.get('thumbnail', track.thumbnail)
        track.url = data.get('webpage_url', track.url)

        # Task 4: Pass the direct URL straight to FFmpeg — no post-processing
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data, track=track, volume=volume)


class MusicPlayer:
    """A class assigned to each guild to manage the queue, playback loop, and interactive remote controls."""
    __slots__ = ('bot', 'guild', 'channel', 'cog', '_queue', 'history', 'next', 'current', 'loop_mode', 'autoplay', 'mode_247', 'volume', 'panel_message', 'start_time', 'pause_start', 'elapsed_time_paused', 'skip_type')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog

        self._queue: List[Track] = []
        self.history: List[Track] = []
        self.next = asyncio.Event()

        self.current = None
        self.loop_mode = None  # None, "single", "queue"
        self.autoplay = False
        self.mode_247 = False
        self.volume = 0.5
        self.panel_message: Optional[discord.Message] = None

        # Playback tracking
        self.start_time = 0.0
        self.pause_start = None
        self.elapsed_time_paused = 0.0
        self.skip_type = None  # "prev", "replay", or None

        self.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        """Main asynchronous player loop."""
        await self.bot.wait_until_ready()

        inactive_seconds = 0
        while not self.bot.is_closed():
            self.next.clear()

            # Handle looping structures
            if self.loop_mode == "single" and self.current:
                # Re-play current track
                pass
            elif self.loop_mode == "queue" and self.current:
                # Put the current song at the back of the queue
                self._queue.append(self.current.track)
                self.current = None
            else:
                self.current = None

            if not self.current:
                # Keep waiting for tracks if the queue is empty
                while not self._queue:
                    if self.mode_247:
                        await asyncio.sleep(2)
                        continue
                    
                    await asyncio.sleep(1)
                    inactive_seconds += 1
                    
                    # Auto-disconnect after 5 minutes of inactivity
                    if inactive_seconds >= 300:
                        try:
                            await self.channel.send("💤 Disconnected from voice channel due to inactivity.")
                        except:
                            pass
                        return self.destroy(self.guild)
                
                inactive_seconds = 0
                track = self._queue.pop(0)
            else:
                track = self.current.track

            # Build the YTDL audio source
            try:
                self.current = await YTDLSource.from_track(track, loop=self.bot.loop, volume=self.volume)
            except Exception as e:
                try:
                    await self.channel.send(f"❌ Error loading track **{track.title}**: {e}")
                except:
                    pass
                self.current = None
                await asyncio.sleep(2)
                continue

            # Update timing variables
            self.start_time = time.time()
            self.pause_start = None
            self.elapsed_time_paused = 0.0

            try:
                self.guild.voice_client.play(self.current, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            except Exception as e:
                print(f"Error starting audio: {e}")
                self.current = None
                continue

            # Dispatch/refresh the player controls panel
            await self.send_player_panel()

            # Wait until track ends or skip occurs
            await self.next.wait()

            # Clear panel message view so users cannot click outdated buttons
            await self.disable_panel_view()

            # Append to history if this wasn't a skip backwards/replay
            if self.current and self.current.track:
                if self.skip_type not in ("prev", "replay"):
                    self.history.append(self.current.track)
                    self.history = self.history[-20:]  # Limit history to 20 songs

            self.skip_type = None

            # Clean up the audio source processes
            if self.current:
                try:
                    self.current.cleanup()
                except:
                    pass

            # Handle Autoplay if queue is empty and loop is OFF
            if self.autoplay and not self._queue and not self.loop_mode:
                await self.handle_autoplay(track)

    async def handle_autoplay(self, last_track: Track):
        """Queries YouTube for related tracks when Autoplay is enabled."""
        try:
            query = f"related to {last_track.title}"
            loop = self.bot.loop
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
            if 'entries' in data and data['entries']:
                for entry in data['entries']:
                    if entry.get('title') != last_track.title:
                        new_track = Track(
                            title=entry.get('title', 'Autoplay Song'),
                            url=entry.get('webpage_url'),
                            requester=self.bot.user,
                            duration=entry.get('duration'),
                            thumbnail=entry.get('thumbnail')
                        )
                        self._queue.append(new_track)
                        await self.channel.send(f"♾️ **Autoplay** added: **{new_track.title}**")
                        break
        except Exception as e:
            print(f"Autoplay lookup failed: {e}")

    def get_elapsed_time(self) -> float:
        """Returns elapsed playback time in seconds, accounting for pauses."""
        if not self.current or not self.start_time:
            return 0.0
        
        voice = self.guild.voice_client
        if not voice:
            return 0.0
            
        if voice.is_paused():
            if self.pause_start:
                return self.pause_start - self.start_time - self.elapsed_time_paused
            return 0.0
        
        return time.time() - self.start_time - self.elapsed_time_paused

    def format_time(self, seconds: Optional[int]) -> str:
        """Formats seconds into MM:SS or HH:MM:SS."""
        if not seconds:
            return "0:00"
        minutes, seconds = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def create_player_embed(self) -> discord.Embed:
        """Constructs the now playing controller embed."""
        if not self.current:
            return discord.Embed(title="🎶 GKR Music Player", description="No song currently playing.", color=0x8A2BE2)

        track = self.current.track
        embed = discord.Embed(title="🎶 GKR MUSIC PLAYER", color=0x8A2BE2)

        duration = track.duration
        duration_str = self.format_time(duration) if duration else "Live"
        elapsed = int(self.get_elapsed_time())
        elapsed_str = self.format_time(elapsed) if duration else "0:00"

        # Calculate progress bar blocks
        bar_length = 20
        if duration and duration > 0:
            filled = int((elapsed / duration) * bar_length)
            filled = max(0, min(bar_length, filled))
        else:
            filled = 0
        bar = "▬" * filled + "🔘" + "▬" * (bar_length - filled)

        loop_status = self.loop_mode.upper() if self.loop_mode else "OFF"
        autoplay_status = "ON" if self.autoplay else "OFF"
        mode_247_status = "ON" if self.mode_247 else "OFF"

        desc = (
            f"**NOW PLAYING**\n"
            f"🎵 **[{track.title}]({track.url})**\n\n"
            f"`{elapsed_str}` {bar} `{duration_str}`\n\n"
            f"👤 **Requester:** {track.requester.mention}\n"
            f"⏳ **Duration:** `{duration_str}`\n"
            f"🔊 **Volume:** `{int(self.volume * 100)}%`\n"
            f"🔁 **Loop:** `{loop_status}`\n"
            f"♾️ **Autoplay:** `{autoplay_status}`\n"
            f"📡 **24/7:** `{mode_247_status}`"
        )
        embed.description = desc

        if track.thumbnail:
            embed.set_image(url=track.thumbnail)

        embed.set_footer(text="GKR Official Music System • YouTube Search & Links")
        return embed

    async def send_player_panel(self):
        """Sends a fresh player control message."""
        await self.disable_panel_view()
        embed = self.create_player_embed()
        view = MusicControlView(self)
        self.panel_message = await self.channel.send(embed=embed, view=view)

    async def update_panel_message(self):
        """Edits the active control panel message in-place."""
        if self.panel_message:
            try:
                embed = self.create_player_embed()
                view = MusicControlView(self)
                await self.panel_message.edit(embed=embed, view=view)
            except Exception as e:
                print(f"Error updating panel message: {e}")

    async def disable_panel_view(self):
        """Disables the interactive controls on the previous panel message."""
        if self.panel_message:
            try:
                await self.panel_message.edit(view=None)
            except:
                pass

    def destroy(self, guild):
        """Forces cleanup and deletes the player session."""
        return self.bot.loop.create_task(self.cog.cleanup(guild))


class MusicControlView(discord.ui.View):
    """3-row remote controller view attached to the Player Embed."""
    def __init__(self, player: MusicPlayer):
        super().__init__(timeout=None)
        self.player = player
        self.update_button_styles()

    def update_button_styles(self):
        """Highlights Loop and Autoplay buttons when they are active."""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "Loop":
                    child.style = discord.ButtonStyle.success if self.player.loop_mode else discord.ButtonStyle.secondary
                elif child.label == "Autoplay":
                    child.style = discord.ButtonStyle.success if self.player.autoplay else discord.ButtonStyle.secondary

    async def check_voice(self, interaction: discord.Interaction) -> bool:
        """Verifies if the user is in the same voice channel."""
        if not interaction.user.voice or not interaction.guild.voice_client:
            await interaction.response.send_message("❌ You are not connected to my voice channel.", ephemeral=True)
            return False
        if interaction.user.voice.channel != interaction.guild.voice_client.channel:
            await interaction.response.send_message("❌ You must be in the same voice channel to control playback.", ephemeral=True)
            return False
        return True

    # ROW 0: Playback Remote Buttons
    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary, emoji="⏪", row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        if not self.player.history:
            return await interaction.response.send_message("❌ No previous tracks in history.", ephemeral=True)

        self.player.skip_type = "prev"
        prev_track = self.player.history.pop()

        if self.player.current:
            self.player._queue.insert(0, self.player.current.track)

        self.player._queue.insert(0, prev_track)
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏪ Playing previous track...", ephemeral=True)

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, emoji="⏸️", row=0)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            self.player.pause_start = time.time()
            voice.pause()
            await interaction.response.defer()
            await self.player.update_panel_message()
        else:
            await interaction.response.send_message("❌ Music is already paused or not playing.", ephemeral=True)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.success, emoji="▶️", row=0)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        voice = interaction.guild.voice_client
        if voice and voice.is_paused():
            if self.player.pause_start:
                self.player.elapsed_time_paused += time.time() - self.player.pause_start
                self.player.pause_start = None
            voice.resume()
            await interaction.response.defer()
            await self.player.update_panel_message()
        else:
            await interaction.response.send_message("❌ Music is not paused.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️", row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        voice = interaction.guild.voice_client
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
            await interaction.response.send_message("⏭️ Song skipped.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)

    @discord.ui.button(label="Replay", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def replay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        if not self.player.current:
            return await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)

        self.player.skip_type = "replay"
        self.player._queue.insert(0, self.player.current.track)
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("🔄 Replaying current song.", ephemeral=True)

    # ROW 1: Sound & Toggles
    @discord.ui.button(label="Vol -", style=discord.ButtonStyle.secondary, emoji="🔉", row=1)
    async def vol_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        self.player.volume = max(0.0, self.player.volume - 0.1)
        if self.player.current:
            self.player.current.volume = self.player.volume
        await interaction.response.defer()
        await self.player.update_panel_message()

    @discord.ui.button(label="Vol +", style=discord.ButtonStyle.secondary, emoji="🔊", row=1)
    async def vol_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        self.player.volume = min(1.0, self.player.volume + 0.1)
        if self.player.current:
            self.player.current.volume = self.player.volume
        await interaction.response.defer()
        await self.player.update_panel_message()

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁", row=1)
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        if not self.player.loop_mode:
            self.player.loop_mode = "single"
        elif self.player.loop_mode == "single":
            self.player.loop_mode = "queue"
        else:
            self.player.loop_mode = None

        self.update_button_styles()
        await interaction.response.defer()
        await self.player.update_panel_message()

    @discord.ui.button(label="Autoplay", style=discord.ButtonStyle.secondary, emoji="♾️", row=1)
    async def autoplay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        self.player.autoplay = not self.player.autoplay
        self.update_button_styles()
        await interaction.response.defer()
        await self.player.update_panel_message()

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️", row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        await self.player.cog.cleanup(interaction.guild)
        await interaction.response.send_message("🛑 Music stopped and bot disconnected.", ephemeral=True)

    # ROW 2: Utility Panels
    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.primary, emoji="🔀", row=2)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_voice(interaction):
            return
        if not self.player._queue:
            return await interaction.response.send_message("❌ The queue is empty.", ephemeral=True)
        random.shuffle(self.player._queue)
        await interaction.response.send_message("🔀 Queue shuffled!", ephemeral=True)

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary, emoji="📜", row=2)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.player._queue and not self.player.current:
            return await interaction.response.send_message("❌ The queue is empty.", ephemeral=True)

        embed = discord.Embed(title=f"Queue for {interaction.guild.name}", color=0x8A2BE2)
        if self.player.current:
            embed.add_field(name="Currently Playing", value=f"[{self.player.current.track.title}]({self.player.current.track.url})", inline=False)

        if self.player._queue:
            q_list = "\n".join(f"{i+1}. [{track.title}]({track.url})" for i, track in enumerate(self.player._queue[:10]))
            if len(self.player._queue) > 10:
                q_list += f"\n*...and {len(self.player._queue)-10} more*"
            embed.add_field(name="Up Next", value=q_list, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Now Playing", style=discord.ButtonStyle.secondary, emoji="🎵", row=2)
    async def now_playing_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.player.update_panel_message()


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: Dict[int, MusicPlayer] = {}

    def get_player(self, ctx):
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player
        return player

    async def cleanup(self, guild):
        """Cleans up voice clients and deletes players."""
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass
        try:
            player = self.players[guild.id]
            await player.disable_panel_view()
            del self.players[guild.id]
        except KeyError:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Clean up if bot is disconnected manually
        if member.id == self.bot.user.id and not after.channel:
            await self.cleanup(member.guild)
            return

        # Auto-disconnect if bot is alone in channel
        voice = member.guild.voice_client
        if voice and voice.channel:
            player = self.players.get(member.guild.id)
            # If 24/7 is enabled, do not auto disconnect
            if player and player.mode_247:
                return

            if len([m for m in voice.channel.members if not m.bot]) == 0:
                await asyncio.sleep(60)
                # Recheck after 60 seconds
                if voice and voice.channel and len([m for m in voice.channel.members if not m.bot]) == 0:
                    player = self.players.get(member.guild.id)
                    if player and not player.mode_247:
                        await self.channel_disconnect_alert(player)
                        await self.cleanup(member.guild)

    async def channel_disconnect_alert(self, player):
        try:
            await player.channel.send("🔇 Auto-disconnected: No users left in the voice channel.")
        except:
            pass

    async def resolve_tracks(self, query: str, requester: discord.Member, loop) -> List[Track]:
        """Resolves a raw query string or URL into a list of Track objects."""
        # Handle Spotify Links
        if "open.spotify.com" in query:
            if not sp:
                raise Exception("Spotify integration is not configured in the bot's .env file. Please add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.")
            
            parsed = urllib.parse.urlparse(query)
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2:
                spotify_type = parts[0]
                spotify_id = parts[1]
                
                if spotify_type == "track":
                    try:
                        track_data = sp.track(spotify_id)
                        title = f"{track_data['name']} - {track_data['artists'][0]['name']}"
                        search_query = f"{track_data['name']} {track_data['artists'][0]['name']} audio"
                        thumbnail = track_data['album']['images'][0]['url'] if track_data['album']['images'] else None
                        duration = int(track_data['duration_ms'] / 1000)
                    except Exception as e:
                        # Fallback: Scrape Spotify web page if API fails (Premium required)
                        import requests, re
                        html = await loop.run_in_executor(None, lambda: requests.get(query).text)
                        title_match = re.search(r'<title>(.*?)</title>', html)
                        if not title_match:
                            raise Exception("Spotify API requires Premium, and web scraper fallback failed.")
                        
                        raw_title = title_match.group(1).replace(" | Spotify", "").replace(" - song and lyrics by ", " - ")
                        title = raw_title
                        search_query = f"{raw_title} audio"
                        
                        # Try to scrape thumbnail
                        thumb_match = re.search(r'<meta property="og:image" content="(.*?)"', html)
                        thumbnail = thumb_match.group(1) if thumb_match else None
                        duration = None # Unknown via basic scraper

                    return [Track(title=title, url=search_query, requester=requester, duration=duration, thumbnail=thumbnail)]
                
                elif spotify_type == "playlist":
                    tracks_list = []
                    try:
                        results = sp.playlist_tracks(spotify_id)
                        items = results['items']
                        while results['next']:
                            results = sp.next(results)
                            items.extend(results['items'])
                    except Exception as e:
                        err_str = str(e).lower()
                        if "premium" in err_str or "token" in err_str or "401" in err_str or "403" in err_str:
                            raise Exception(
                                "\u274c **Spotify API Blocked:** Spotify now requires your Developer Account to have an active **Premium Subscription** to fetch playlists.\n\n"
                                "👉 **Workarounds:**\n"
                                "1. Play single Spotify track links (they bypass this block!)\n"
                                "2. Use YouTube Playlists instead."
                            )
                        raise Exception(f"Failed to load Spotify playlist: {e}")
                        
                    for item in items:
                        if not item or not item.get('track'):
                            continue
                        track_data = item['track']
                        title = f"{track_data['name']} - {track_data['artists'][0]['name']}"
                        search_query = f"{track_data['name']} {track_data['artists'][0]['name']} audio"
                        thumbnail = track_data['album']['images'][0]['url'] if track_data.get('album') and track_data['album'].get('images') else None
                        duration = int(track_data['duration_ms'] / 1000)
                        tracks_list.append(Track(title=title, url=search_query, requester=requester, duration=duration, thumbnail=thumbnail))
                    return tracks_list
                
                elif spotify_type == "album":
                    tracks_list = []
                    album_data = sp.album(spotify_id)
                    album_image = album_data['images'][0]['url'] if album_data['images'] else None
                    
                    try:
                        results = sp.album_tracks(spotify_id)
                        items = results['items']
                        while results['next']:
                            results = sp.next(results)
                            items.extend(results['items'])
                    except Exception as e:
                        err_str = str(e).lower()
                        if "premium" in err_str or "token" in err_str or "401" in err_str or "403" in err_str:
                            raise Exception(
                                "\u274c **Spotify API Blocked:** Spotify now requires your Developer Account to have an active **Premium Subscription** to fetch albums.\n\n"
                                "👉 **Workarounds:**\n"
                                "1. Play single Spotify track links (they bypass this block!)\n"
                                "2. Use YouTube links instead."
                            )
                        raise Exception(f"Failed to load Spotify album: {e}")
                    
                    for track_data in items:
                        if not track_data:
                            continue
                        title = f"{track_data['name']} - {track_data['artists'][0]['name']}"
                        search_query = f"{track_data['name']} {track_data['artists'][0]['name']} audio"
                        duration = int(track_data['duration_ms'] / 1000)
                        tracks_list.append(Track(title=title, url=search_query, requester=requester, duration=duration, thumbnail=album_image))
                    return tracks_list
            raise Exception("Invalid Spotify URL pattern. Supported: tracks, playlists, albums.")

        # Handle YouTube Playlists
        if "youtube.com/playlist" in query or ("youtu.be/" in query and "list=" in query) or ("youtube.com/watch" in query and "list=" in query):
            ytdl_playlist_options = _build_ytdl_opts(noplaylist=False)
            ytdl_playlist_options.update({
                'extract_flat': 'in_playlist',
                'ignoreerrors': True,
            })
            with yt_dlp.YoutubeDL(ytdl_playlist_options) as ytdl_pl:
                data = await loop.run_in_executor(None, lambda: ytdl_pl.extract_info(query, download=False, process=False))
                if not data:
                    raise Exception("Failed to retrieve playlist information.")
                
                entries = [entry for entry in data.get('entries', []) if entry]
                tracks_list = []
                for entry in entries:
                    video_id = entry.get('id')
                    video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else entry.get('url')
                    if not video_url:
                        continue
                    title = entry.get('title') or "YouTube Video"
                    duration = entry.get('duration')
                    tracks_list.append(Track(title=title, url=video_url, requester=requester, duration=duration))
                return tracks_list

        # Single YouTube URL or song name search
        # Normalize any YouTube Music / short links first
        if query.startswith("http") or query.startswith("www."):
            query = normalize_youtube_url(query)

        # Prefix bare text searches with ytsearch1: to force a single best match
        is_url = query.startswith("http://") or query.startswith("https://") or query.startswith("www.")
        search_query = query if is_url else f"ytsearch1:{query}"

        # Method 5: Robust retry logic for metadata searches
        data = None
        for attempt in range(3):
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
                if data:
                    break
            except Exception as e:
                print(f"\u26a0\ufe0f [Search Attempt {attempt+1}/3] yt-dlp search failed: {e}")
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(2)

        if not data:
            raise Exception("No results found. YouTube may be blocking requests from this server. Try a direct YouTube link instead.")

        if 'entries' in data:
            entries = [e for e in data['entries'] if e]
            if not entries:
                raise Exception("No search results found. Try a different search term or paste a YouTube link directly.")
            data = entries[0]

        title = data.get('title')
        video_url = data.get('webpage_url') or data.get('url')
        duration = data.get('duration')
        thumbnail = data.get('thumbnail')

        if not video_url:
            raise Exception("Could not extract a playable URL from the search result. Try a direct YouTube link.")

        return [Track(title=title, url=video_url, requester=requester, duration=duration, thumbnail=thumbnail)]

    # -----------------------------------------------------------------------
    # Slash Commands
    # -----------------------------------------------------------------------

    music_group = app_commands.Group(name="music", description="Advanced Music System")

    @music_group.command(name="ytdlp_test", description="Run the ultimate diagnostic test directly on the server to debug bot blocks.")
    @app_commands.default_permissions(administrator=True)
    async def ytdlp_test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        import subprocess
        
        cookie_arg = []
        if _ACTIVE_COOKIE_FILE and os.path.exists(_ACTIVE_COOKIE_FILE):
            cookie_arg = ["--cookies", _ACTIVE_COOKIE_FILE]
            
        cmd = [
            sys.executable, "-m", "yt_dlp", "-v", 
            "--extractor-args", "youtube:player_client=tv,mweb"
        ] + cookie_arg + ["https://www.youtube.com/watch?v=WR8PyAhn6tQ"]
        
        try:
            result = await self.bot.loop.run_in_executor(
                None, 
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            )
            output = result.stdout + "\n" + result.stderr
        except Exception as e:
            output = f"Execution Failed: {e}"
            
        if len(output) > 1900:
            import io
            file = discord.File(io.BytesIO(output.encode('utf-8')), filename="ytdlp_debug_log.txt")
            await interaction.followup.send("⚠️ The log was too long. It has been attached as a file:", file=file)
        else:
            await interaction.followup.send(f"```text\n{output}\n```")

    @music_group.command(name="play", description="Play a song, playlist, or album from YouTube or Spotify")
    @app_commands.describe(query="A search query, YouTube video/playlist link, or Spotify link")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        
        if not interaction.user.voice:
            return await interaction.followup.send("❌ You are not connected to a voice channel.")
            
        channel = interaction.user.voice.channel
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if not voice:
            try:
                voice = await channel.connect()
            except Exception as e:
                return await interaction.followup.send(f"❌ Could not connect to voice channel: {e}")
        elif voice.channel != channel:
            return await interaction.followup.send("❌ I'm already playing in another channel.")

        # Create dummy context for Player creation
        class DummyCtx:
            bot = self.bot
            guild = interaction.guild
            channel = interaction.channel
            cog = self
            
        player = self.get_player(DummyCtx())

        try:
            resolved_tracks = await self.resolve_tracks(query, interaction.user, self.bot.loop)
        except Exception as e:
            return await interaction.followup.send(f"❌ An error occurred: {e}")

        if not resolved_tracks:
            return await interaction.followup.send("❌ Could not extract any tracks from the query.")

        for track in resolved_tracks:
            player._queue.append(track)

        if len(resolved_tracks) > 1:
            await interaction.followup.send(f"✅ Added **{len(resolved_tracks)}** songs to the queue.")
        else:
            await interaction.followup.send(f"✅ Added to queue: **{resolved_tracks[0].title}**")

    @music_group.command(name="stop", description="Stops the music and disconnects the bot")
    async def stop(self, interaction: discord.Interaction):
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if not voice or not voice.is_connected():
            return await interaction.response.send_message("❌ I am not playing anything.", ephemeral=True)

        await self.cleanup(interaction.guild)
        await interaction.response.send_message("🛑 Playback stopped and bot disconnected.")

    @music_group.command(name="skip", description="Skips the currently playing song")
    async def skip(self, interaction: discord.Interaction):
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if not voice or not voice.is_playing():
            return await interaction.response.send_message("❌ Not playing any music right now.", ephemeral=True)

        voice.stop()
        await interaction.response.send_message("⏭️ Song skipped.")

    @music_group.command(name="pause", description="Pauses the current song")
    async def pause(self, interaction: discord.Interaction):
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if not voice or not voice.is_playing():
            return await interaction.response.send_message("❌ Not playing any music right now.", ephemeral=True)
            
        player = self.players.get(interaction.guild.id)
        if player:
            player.pause_start = time.time()
        voice.pause()
        if player:
            await player.update_panel_message()
        await interaction.response.send_message("⏸️ Music paused.")

    @music_group.command(name="resume", description="Resumes the paused song")
    async def resume(self, interaction: discord.Interaction):
        voice = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if not voice or not voice.is_paused():
            return await interaction.response.send_message("❌ The music is not paused.", ephemeral=True)
            
        player = self.players.get(interaction.guild.id)
        if player and player.pause_start:
            player.elapsed_time_paused += time.time() - player.pause_start
            player.pause_start = None
        voice.resume()
        if player:
            await player.update_panel_message()
        await interaction.response.send_message("▶️ Music resumed.")

    @music_group.command(name="queue", description="Shows the upcoming songs")
    async def queue(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player or (not player._queue and not player.current):
            return await interaction.response.send_message("❌ The queue is empty.", ephemeral=True)

        embed = discord.Embed(title=f"Queue for {interaction.guild.name}", color=0x8A2BE2)
        if player.current:
            embed.add_field(name="Currently Playing", value=f"[{player.current.track.title}]({player.current.track.url})", inline=False)
            
        if player._queue:
            queue_list = "\n".join(f"{i+1}. [{track.title}]({track.url})" for i, track in enumerate(player._queue[:10]))
            if len(player._queue) > 10:
                queue_list += f"\n*...and {len(player._queue)-10} more*"
            embed.add_field(name="Up Next", value=queue_list, inline=False)
            
        await interaction.response.send_message(embed=embed)

    @music_group.command(name="loop", description="Toggles looping: OFF / SINGLE / QUEUE")
    async def loop(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message("❌ I am not playing anything.", ephemeral=True)

        if not player.loop_mode:
            player.loop_mode = "single"
        elif player.loop_mode == "single":
            player.loop_mode = "queue"
        else:
            player.loop_mode = None

        await player.update_panel_message()
        await interaction.response.send_message(f"🔁 Looping mode set to: **{player.loop_mode or 'OFF'}**")

    @music_group.command(name="shuffle", description="Shuffles the current music queue")
    async def shuffle(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player or not player._queue:
            return await interaction.response.send_message("❌ The queue is empty.", ephemeral=True)

        random.shuffle(player._queue)
        await interaction.response.send_message("🔀 Music queue has been shuffled!")

    @music_group.command(name="remove", description="Removes a specific song from the queue by index")
    @app_commands.describe(index="The list number of the song to remove")
    async def remove(self, interaction: discord.Interaction, index: int):
        player = self.players.get(interaction.guild.id)
        if not player or not player._queue:
            return await interaction.response.send_message("❌ The queue is empty.", ephemeral=True)

        if index < 1 or index > len(player._queue):
            return await interaction.response.send_message(f"❌ Invalid index. Please choose a number between 1 and {len(player._queue)}.", ephemeral=True)

        removed_track = player._queue.pop(index - 1)
        await interaction.response.send_message(f"🗑️ Removed **{removed_track.title}** from the queue.")

    @music_group.command(name="clear", description="Clears the entire music queue")
    async def clear(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player or not player._queue:
            return await interaction.response.send_message("❌ The queue is already empty.", ephemeral=True)

        player._queue.clear()
        await interaction.response.send_message("🗑️ Music queue has been cleared.")

    @music_group.command(name="toggle_247", description="Toggles 24/7 mode (keeps bot in voice channel forever)")
    async def toggle_247(self, interaction: discord.Interaction):
        player = self.players.get(interaction.guild.id)
        if not player:
            return await interaction.response.send_message("❌ Active music session not found.", ephemeral=True)

        player.mode_247 = not player.mode_247
        await player.update_panel_message()
        status = "enabled" if player.mode_247 else "disabled"
        await interaction.response.send_message(f"📡 24/7 mode has been **{status}**.")


async def setup_music(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
    print("🎵 Music system loaded with interactive controls!")
