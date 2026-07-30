"""
music.py — Lavalink/Wavelink Music System for GKR Bot.
Uses Lavalink (via wavelink) for all audio — no yt-dlp bot detection issues.
Supports YouTube, Spotify (search fallback), SoundCloud, playlists, and interactive controls.
"""

import asyncio
import os
import random
import discord
import wavelink
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

LAVALINK_URI      = os.getenv("LAVALINK_URI", "http://localhost:2333")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")

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
    """Build a premium sleek progress bar."""
    if not duration:
        return "━" * length
    progress = min(position / duration, 1.0)
    filled = int(progress * length)
    bar = "━" * filled + "🔘" + "━" * max(0, length - filled - 1)
    return bar

def format_ms(ms: int) -> str:
    """Format milliseconds into MM:SS or HH:MM:SS."""
    if not ms:
        return "0:00"
    seconds = ms // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Control Panel (Buttons)
# ─────────────────────────────────────────────────────────────────────────────

class MusicControlView(discord.ui.View):
    def __init__(self, player: "GuildPlayer"):
        super().__init__(timeout=None)
        self.player = player

    async def _check_voice(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice:
            await interaction.response.send_message(embed=discord.Embed(description="⨯ Join a voice channel first.", color=0xed4245), ephemeral=True)
            return False
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message(embed=discord.Embed(description="⨯ Bot is not connected.", color=0xed4245), ephemeral=True)
            return False
        if interaction.user.voice.channel != vc.channel:
            try:
                await interaction.user.voice.channel.connect(cls=wavelink.Player)
            except Exception as e:
                await interaction.response.send_message(embed=discord.Embed(description=f"⨯ Could not move to your channel: {e}", color=0xed4245), ephemeral=True)
                return False
        return True

    async def refresh_panel(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client if interaction.guild else None
        track = getattr(vc, 'current', None) if vc else None
        embed = self.player.build_embed(vc, track)
        self._update_styles()
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except:
                pass

    def _update_styles(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "loop":
                    child.style = (
                        discord.ButtonStyle.success if self.player.loop_mode else discord.ButtonStyle.secondary
                    )
                if child.custom_id == "247":
                    child.style = (
                        discord.ButtonStyle.success if self.player.mode_247 else discord.ButtonStyle.secondary
                    )

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="prev", row=0)
    async def prev_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        if not self.player.history:
            return await interaction.response.send_message("❌ No previous track.", ephemeral=True)
        vc: wavelink.Player = interaction.guild.voice_client
        self.player.skip_prev = True
        prev_track = self.player.history.pop()
        if vc.playing and vc.current:
            await vc.queue.put_wait(vc.current)
            vc.queue.swap(0, len(vc.queue)-1)
        await vc.play(prev_track)
        await self.refresh_panel(interaction)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="playpause", row=0)
    async def playpause_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc.playing and vc.queue.is_empty:
            return await interaction.response.send_message("❌ Nothing playing.", ephemeral=True)
        await vc.pause(not vc.paused)
        await self.refresh_panel(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="skip", row=0)
    async def skip_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc.playing:
            return await interaction.response.send_message("❌ Nothing to skip.", ephemeral=True)
        await vc.skip(force=True)
        await self.refresh_panel(interaction)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="loop", row=0)
    async def loop_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        modes = [None, "single", "queue"]
        cur = self.player.loop_mode
        self.player.loop_mode = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "single"
        await self.refresh_panel(interaction)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="shuffle", row=0)
    async def shuffle_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        items = list(vc.queue)
        random.shuffle(items)
        vc.queue.clear()
        for it in items:
            await vc.queue.put_wait(it)
        await self.refresh_panel(interaction)
        await interaction.followup.send("🔀 Queue shuffled!", ephemeral=True)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="vol_down", row=1)
    async def vol_down_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        new_vol = max(0, vc.volume - 10)
        await vc.set_volume(new_vol)
        await self.refresh_panel(interaction)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.secondary, custom_id="stop", row=1)
    async def stop_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        self.player.mode_247 = False
        vc.queue.clear()
        await vc.disconnect()
        await interaction.response.send_message("⏹ Stopped and disconnected.", ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="vol_up", row=1)
    async def vol_up_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        new_vol = min(100, vc.volume + 10)
        await vc.set_volume(new_vol)
        await self.refresh_panel(interaction)

    @discord.ui.button(emoji="📡", style=discord.ButtonStyle.secondary, custom_id="247", row=1)
    async def mode_247_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        self.player.mode_247 = not self.player.mode_247
        status = "enabled" if self.player.mode_247 else "disabled"
        await self.refresh_panel(interaction)
        await interaction.followup.send(f"📡 24/7 mode **{status}**.", ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Per-Guild Player State
# ─────────────────────────────────────────────────────────────────────────────

class GuildPlayer:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.loop_mode: Optional[str] = None   # None, "single", "queue"
        self.mode_247: bool = False
        self.panel_message: Optional[discord.Message] = None
        self.text_channel: Optional[discord.TextChannel] = None  # set on /play
        self.history: List[wavelink.Playable] = []
        self.skip_prev: bool = False

    def _get_requester(self, track: wavelink.Playable) -> Optional[str]:
        """Safely extract requester from ExtrasNamespace (wavelink 3.x)."""
        try:
            extras = getattr(track, 'extras', None)
            if extras is None:
                return None
            # ExtrasNamespace — use attribute access, not .get()
            return getattr(extras, 'requester', None)
        except Exception:
            return None

    async def update_panel(self, bot: commands.Bot, track: Optional[wavelink.Playable] = None):
        guild = bot.get_guild(self.guild_id)
        if not guild:
            return
        vc: Optional[wavelink.Player] = guild.voice_client

    def build_embed(self, vc: Optional[wavelink.Player], track: Optional[wavelink.Playable] = None) -> discord.Embed:
        embed = discord.Embed(color=0x2b2d31)  # Premium dark grey/discord color
        embed.set_author(name="GKR Music", icon_url="https://cdn-icons-png.flaticon.com/512/324/324225.png")

        if not vc or not vc.playing or not track:
            embed.description = "The queue is currently empty.\nUse `/play` to add some tracks."
        else:
            loop_str = {"single": "Loop Song", "queue": "Loop Queue"}.get(self.loop_mode, "Normal")
            bar = build_progress_bar(vc.position, track.length)
            
            # Replicate ZENTRA style description
            desc = (
                f"💿 **Playing:**\n"
                f"**{track.title}**\n"
                f"🔗 [Open song link]({track.uri})\n\n"
            )
            
            requester = self._get_requester(track) or "Unknown"
            desc += f"👤 **Played by:** `{requester}`\n"
            desc += f"⚡ **Duration:** `{format_ms(track.length)}`\n"
            desc += f"**Queue Length:** `{vc.queue.count}` • **Volume:** `{vc.volume}%`\n"
            desc += f"**24/7 Mode:** `{'ON' if self.mode_247 else 'OFF'}` • **Mode:** `{loop_str}`\n\n"
            
            status = "⏸️ Paused" if vc.paused else "▶️ Playing"
            desc += f"**Update**\n{status} | {format_ms(vc.position)} {bar}"
            
            embed.description = desc

            if hasattr(track, 'artwork') and track.artwork:
                embed.set_thumbnail(url=track.artwork)
            
        return embed

    async def update_panel(self, bot: commands.Bot, track: Optional[wavelink.Playable] = None):
        guild = bot.get_guild(self.guild_id)
        if not guild:
            return
        vc: Optional[wavelink.Player] = guild.voice_client

        embed = self.build_embed(vc, track)

        view = MusicControlView(self)
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=embed, view=view)
                return
            except Exception:
                self.panel_message = None

        # Use stored text channel first, then find any writable channel
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

    def get_gp(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.guild_players:
            self.guild_players[guild_id] = GuildPlayer(guild_id)
        return self.guild_players[guild_id]

    async def cog_load(self):
        await self._connect_lavalink()

    async def _connect_lavalink(self):
        # Derive if SSL should be used from the URI scheme
        use_ssl = LAVALINK_URI.startswith("https://")
        print(f"[Music] Connecting to Lavalink: {LAVALINK_URI} (ssl={use_ssl})")
        for attempt in range(5):
            try:
                node = wavelink.Node(
                    uri=LAVALINK_URI,
                    password=LAVALINK_PASSWORD,
                )
                await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=100)
                print(f"✅ Lavalink connected → {LAVALINK_URI}")
                return
            except Exception as e:
                print(f"❌ Lavalink connection attempt {attempt+1}/5 failed: {e}")
                if attempt < 4:
                    await asyncio.sleep(10)
        print("❌ All Lavalink connection attempts failed. Music will not work.")

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"🎵 Lavalink node '{payload.node.identifier}' is ready and connected!")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        gp = self.get_gp(payload.player.guild.id)
        await gp.update_panel(self.bot, payload.track)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        """Handle Lavalink track errors gracefully."""
        gp = self.get_gp(payload.player.guild.id)
        print(f"[Music] ⚠️ Track exception: {payload.exception}")
        ch = gp.text_channel
        if ch:
            try:
                await ch.send(
                    "⚠️ **Could not play that track** — YouTube blocked it on the Lavalink server.\n"
                    "Try searching by **song name** instead of a URL, or use SoundCloud links."
                )
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
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
            await player.play(payload.track)
            return
        if gp.loop_mode == "queue" and payload.track:
            await player.queue.put_wait(payload.track)

        # Play next
        if player.queue.is_empty:
            if not gp.mode_247:
                await asyncio.sleep(30)
                if player.queue.is_empty and not player.playing:
                    await player.disconnect()
            await gp.update_panel(self.bot, None)
        else:
            next_track = await player.queue.get_wait()
            await player.play(next_track)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        """Auto-disconnect if alone in VC (unless 24/7 mode)."""
        if member.bot:
            return
        guild = member.guild
        vc: Optional[wavelink.Player] = guild.voice_client
        if not vc:
            return
        gp = self.get_gp(guild.id)
        if gp.mode_247:
            return
        # Check if bot is alone
        members_in_vc = [m for m in vc.channel.members if not m.bot]
        if not members_in_vc:
            await asyncio.sleep(60)
            vc2: Optional[wavelink.Player] = guild.voice_client
            if vc2 and not [m for m in vc2.channel.members if not m.bot]:
                vc2.queue.clear()
                await vc2.disconnect()

    # ── Helper: resolve query to tracks ───────────────────────────────────────

    async def _resolve(self, query: str, requester: discord.Member) -> List[wavelink.Playable]:
        """Resolve a search query or URL to a list of wavelink Playable tracks."""
        tracks = []

        # Spotify link handling (convert to search)
        if sp and "spotify.com" in query:
            try:
                if "/track/" in query:
                    tid = query.split("/track/")[1].split("?")[0]
                    item = sp.track(tid)
                    query = f"{item['name']} {item['artists'][0]['name']}"
                elif "/playlist/" in query:
                    pid = query.split("/playlist/")[1].split("?")[0]
                    results = sp.playlist_tracks(pid, limit=50)
                    for it in results['items']:
                        t = it.get('track')
                        if t:
                            name = t['name']
                            artist = t['artists'][0]['name']
                            search = await wavelink.Playable.search(f"{name} {artist}")
                            if search:
                                tr = search[0]
                                tr.extras.requester = requester.display_name
                                tracks.append(tr)
                    return tracks
                elif "/album/" in query:
                    aid = query.split("/album/")[1].split("?")[0]
                    results = sp.album_tracks(aid, limit=50)
                    for it in results['items']:
                        name = it['name']
                        artist = it['artists'][0]['name']
                        search = await wavelink.Playable.search(f"{name} {artist}")
                        if search:
                            tr = search[0]
                            tr.extras.requester = requester.display_name
                            tracks.append(tr)
                    return tracks
            except Exception as e:
                print(f"[Spotify] Error: {e}")

        # YouTube/URL or plain search
        # Check Lavalink node is actually connected
        nodes = wavelink.Pool.nodes
        if not nodes:
            print("[Music] ❌ No Lavalink nodes connected! Is Lavalink running?")
            return tracks

        # ── URL normalization ──────────────────────────────────────────────────
        # Convert YouTube Music → standard YouTube (Lavalink can't handle music.youtube.com)
        if "music.youtube.com" in query:
            query = query.replace("music.youtube.com", "www.youtube.com")
            print(f"[Music] Normalized YouTube Music URL → {query}")

        # Convert youtu.be short links → full URL
        if "youtu.be/" in query:
            video_id = query.split("youtu.be/")[1].split("?")[0].split("&")[0]
            query = f"https://www.youtube.com/watch?v={video_id}"
            print(f"[Music] Normalized youtu.be → {query}")

        is_url = query.startswith("http://") or query.startswith("https://")
        is_yt_url = is_url and ("youtube.com" in query or "youtu.be" in query)
        print(f"[Music] Searching for: '{query}' (is_url={is_url}, is_yt_url={is_yt_url})")

        results = []

        def _add_track(tr):
            try:
                tr.extras.requester = requester.display_name
            except Exception:
                pass
            tracks.append(tr)

        def _process(res):
            if isinstance(res, wavelink.Playlist):
                for tr in res.tracks:
                    _add_track(tr)
            elif res:
                _add_track(res[0])

        # Try the query directly first
        try:
            results = await wavelink.Playable.search(query)
            print(f"[Music] Direct result count: {len(results) if results else 0}")
        except Exception as e:
            print(f"[Music] Direct search error: {e}")

        # If a YouTube URL failed (plugin not installed), fall back to text search
        if not results and is_yt_url:
            import re
            vid_match = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', query)
            if vid_match:
                # We can't resolve the title without the plugin, so search the ID as text
                fallback_query = vid_match.group(1)
                print(f"[Music] YouTube URL failed. Searching video ID as text: {fallback_query}")
                try:
                    results = await wavelink.Playable.search(fallback_query)
                    print(f"[Music] ID-search result count: {len(results) if results else 0}")
                except Exception as e:
                    print(f"[Music] ID-search error: {e}")

        # Final SoundCloud fallback for text queries
        if not results and not is_url:
            sc_query = f"scsearch:{query}"
            print(f"[Music] Trying SoundCloud fallback: {sc_query}")
            try:
                results = await wavelink.Playable.search(sc_query)
                print(f"[Music] SoundCloud result count: {len(results) if results else 0}")
            except Exception as e:
                print(f"[Music] SoundCloud error: {e}")

        _process(results)
        if not tracks:
            print(f"[Music] ❌ No results from any source for: '{query}'")

        return tracks



    # ── Slash Commands ────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Play a song or playlist from YouTube, Spotify, or SoundCloud.")
    @app_commands.describe(query="YouTube URL, Spotify link, or song name to search")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send(embed=discord.Embed(description="⨯ Join a voice channel first.", color=0xed4245), ephemeral=True)

        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc:
            try:
                vc = await interaction.user.voice.channel.connect(cls=wavelink.Player)
            except Exception as e:
                return await interaction.followup.send(embed=discord.Embed(description=f"⨯ Could not connect: {e}", color=0xed4245), ephemeral=True)
        elif interaction.user.voice.channel != vc.channel:
            try:
                await interaction.user.voice.channel.connect(cls=wavelink.Player)
                # Note: For Wavelink, connecting again to a new channel safely moves the player
            except Exception as e:
                return await interaction.followup.send(embed=discord.Embed(description=f"⨯ Could not move to your channel: {e}", color=0xed4245), ephemeral=True)

        tracks = await self._resolve(query, interaction.user)
        if not tracks:
            return await interaction.followup.send(embed=discord.Embed(description="⨯ No tracks found for that query.", color=0xed4245), ephemeral=True)

        gp = self.get_gp(interaction.guild.id)
        gp.text_channel = interaction.channel

        for tr in tracks:
            await vc.queue.put_wait(tr)

        if not vc.playing:
            next_track = await vc.queue.get_wait()
            await vc.play(next_track)
            embed = discord.Embed(description=f"✦ Now playing **{next_track.title}**", color=0x2b2d31)
            await interaction.followup.send(embed=embed)
        else:
            names = ", ".join(f"**{t.title}**" for t in tracks[:3])
            extra = f" + {len(tracks) - 3} more" if len(tracks) > 3 else ""
            embed = discord.Embed(description=f"✦ Added {names}{extra} to queue", color=0x2b2d31)
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="stop", description="Stop music and disconnect.")
    async def stop(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Not connected.", color=0xed4245), ephemeral=True)
        gp = self.get_gp(interaction.guild.id)
        gp.mode_247 = False
        vc.queue.clear()
        await vc.disconnect()
        await interaction.response.send_message(embed=discord.Embed(description="✦ Stopped and disconnected", color=0x2b2d31))

    @app_commands.command(name="skip", description="Skip the current track.")
    async def skip(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Nothing playing.", color=0xed4245), ephemeral=True)
        await vc.skip(force=True)
        await interaction.response.send_message(embed=discord.Embed(description="✦ Skipped track", color=0x2b2d31))

    @app_commands.command(name="pause", description="Pause the current track.")
    async def pause(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Nothing playing.", color=0xed4245), ephemeral=True)
        await vc.pause(True)
        await interaction.response.send_message(embed=discord.Embed(description="✦ Paused playback", color=0x2b2d31))

    @app_commands.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or not vc.paused:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Not paused.", color=0xed4245), ephemeral=True)
        await vc.pause(False)
        await interaction.response.send_message(embed=discord.Embed(description="✦ Resumed playback", color=0x2b2d31))

    @app_commands.command(name="volume", description="Set the volume (0–100).")
    @app_commands.describe(level="Volume level 0-100")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 0 <= level <= 100:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Volume must be 0–100.", color=0xed4245), ephemeral=True)
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Not connected.", color=0xed4245), ephemeral=True)
        await vc.set_volume(level)
        await interaction.response.send_message(embed=discord.Embed(description=f"✦ Volume set to **{level}%**", color=0x2b2d31))

    @app_commands.command(name="queue", description="Show the music queue.")
    async def queue_cmd(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Not connected.", color=0xed4245), ephemeral=True)

        embed = discord.Embed(title="✦ Queue", color=0x2b2d31)
        if vc.current:
            embed.add_field(name="Now Playing", value=f"[{vc.current.title}]({vc.current.uri})", inline=False)

        q_items = list(vc.queue)[:15]
        if q_items:
            lines = "\n".join(f"`{i+1}.` {t.title}" for i, t in enumerate(q_items))
            embed.add_field(name="Up Next", value=lines, inline=False)
            if vc.queue.count > 15:
                embed.set_footer(text=f"... and {vc.queue.count - 15} more tracks")
        else:
            embed.description = "The queue is empty."

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="nowplaying", description="Show the now playing panel with controls.")
    async def nowplaying(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Nothing is playing.", color=0xed4245), ephemeral=True)

        gp = self.get_gp(interaction.guild.id)
        embed = gp.build_embed(vc, vc.current)
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
        await interaction.response.send_message(embed=discord.Embed(description=f"✦ Loop mode: **{mode_str}**", color=0x2b2d31))

    @app_commands.command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or vc.queue.is_empty:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Queue is empty.", color=0xed4245), ephemeral=True)
        items = list(vc.queue)
        random.shuffle(items)
        vc.queue.clear()
        for it in items:
            await vc.queue.put_wait(it)
        await interaction.response.send_message(embed=discord.Embed(description="✦ Queue shuffled", color=0x2b2d31))

    @app_commands.command(name="remove", description="Remove a track from the queue by position.")
    @app_commands.describe(index="Position in queue (1 = first)")
    async def remove(self, interaction: discord.Interaction, index: int):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or vc.queue.is_empty:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Queue is empty.", color=0xed4245), ephemeral=True)
        items = list(vc.queue)
        if index < 1 or index > len(items):
            return await interaction.response.send_message(embed=discord.Embed(description=f"⨯ Index must be 1–{len(items)}.", color=0xed4245), ephemeral=True)
        removed = items.pop(index - 1)
        vc.queue.clear()
        for it in items:
            await vc.queue.put_wait(it)
        await interaction.response.send_message(embed=discord.Embed(description=f"✦ Removed **{removed.title}**", color=0x2b2d31))

    @app_commands.command(name="clear", description="Clear the entire queue.")
    async def clear(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(embed=discord.Embed(description="⨯ Not connected.", color=0xed4245), ephemeral=True)
        vc.queue.clear()
        await interaction.response.send_message(embed=discord.Embed(description="✦ Queue cleared", color=0x2b2d31))

    @app_commands.command(name="toggle_247", description="Toggle 24/7 mode (bot stays in VC forever).")
    async def toggle_247(self, interaction: discord.Interaction):
        gp = self.get_gp(interaction.guild.id)
        gp.mode_247 = not gp.mode_247
        status = "enabled" if gp.mode_247 else "disabled"
        await interaction.response.send_message(embed=discord.Embed(description=f"✦ 24/7 mode **{status}**", color=0x2b2d31))


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
    print("🎵 Lavalink Music system loaded!")
