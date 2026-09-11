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
import aiohttp
import difflib
import re
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List
from gkr_ui import C, embed_error, embed_success, embed_info, BOT_NAME
from dotenv import load_dotenv

load_dotenv()

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
        vc: Optional[wavelink.Player] = interaction.guild.voice_client if interaction.guild else None
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
    """Legacy text progress bar - removed to reduce API usage and improve aesthetics."""
    return ""

MUSIC_VISUALIZER_GIF = "https://media.discordapp.net/attachments/778226616638898177/1539672796253265971/combined_music_visualizer.gif?ex=6a872b88&is=6a85da08&hm=156453eba45e90d506f944c7bca13d8f078d092fccf1a86b4d1ed693fb4c7c21&="

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
    """Request India's Discord voice region for the channel used by music."""
    try:
        if channel.rtc_region != "india":
            await channel.edit(rtc_region="india", reason="Set music voice region to India")
            print(f"[Music] Voice region set to India for {channel.name}")
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"[Music] Could not set India voice region for {channel.name}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Control Panel (Buttons - Clean & Modern Spotify/Discord Theme)
# ─────────────────────────────────────────────────────────────────────────────

class MusicControlView(discord.ui.View):
    def __init__(self, player: "GuildPlayer"):
        super().__init__(timeout=None)
        self.player = player
        self._update_styles()

    async def _check_voice(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice:
            await interaction.response.send_message(embed=embed_error("Join a voice channel first."), ephemeral=True)
            return False
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message(embed=embed_error("Bot is not connected."), ephemeral=True)
            return False
        if interaction.user.voice.channel != vc.channel:
            # Move the bot to the user's channel instead of creating a new connection
            try:
                await vc.move_to(interaction.user.voice.channel)
            except Exception as e:
                await interaction.response.send_message(embed=embed_error(f"Could not move to your channel: {e}"), ephemeral=True)
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
            except Exception:
                pass

    def _update_styles(self):
        vc = getattr(self.player, 'voice_client', None)
        is_paused = getattr(vc, 'paused', False) if vc else False

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "playpause":
                    child.label = "▷" if is_paused else "❚❚"
                    child.style = discord.ButtonStyle.primary
                elif child.custom_id == "loop":
                    child.style = discord.ButtonStyle.success if self.player.loop_mode else discord.ButtonStyle.secondary
                elif child.custom_id == "filter":
                    child.style = discord.ButtonStyle.primary if self.player.current_filter != "Normal" else discord.ButtonStyle.secondary
                elif child.custom_id == "247":
                    child.style = discord.ButtonStyle.success if self.player.mode_247 else discord.ButtonStyle.secondary

    # ── Row 0: Core Playback (Primary Highlighted Controls) ───────────────────

    @discord.ui.button(label="◁◁", style=discord.ButtonStyle.secondary, custom_id="prev", row=0)
    async def prev_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        if not self.player.history:
            return await interaction.response.send_message(embed=embed_error("No previous track in history."), ephemeral=True)
        vc: wavelink.Player = interaction.guild.voice_client
        self.player.skip_prev = True
        prev_track = self.player.history.pop()
        if vc.playing and vc.current:
            await vc.queue.put_wait(vc.current)
            vc.queue.swap(0, len(vc.queue) - 1)
        await vc.play(prev_track)
        await self.refresh_panel(interaction)

    @discord.ui.button(label="❚❚", style=discord.ButtonStyle.primary, custom_id="playpause", row=0)
    async def playpause_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc.playing and vc.queue.is_empty:
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
        
        self.player.voice_client = vc
        await self.refresh_panel(interaction)

    @discord.ui.button(label="▷▷", style=discord.ButtonStyle.secondary, custom_id="skip", row=0)
    async def skip_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc.playing:
            return await interaction.response.send_message(embed=embed_error("Nothing to skip."), ephemeral=True)
        await vc.skip(force=True)
        await self.refresh_panel(interaction)

    @discord.ui.button(label="⇄", style=discord.ButtonStyle.secondary, custom_id="shuffle", row=0)
    async def shuffle_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        if vc.queue.is_empty:
            return await interaction.response.send_message(embed=embed_info("Queue", "Queue is empty, nothing to shuffle."), ephemeral=True)
        items = list(vc.queue)
        random.shuffle(items)
        vc.queue.clear()
        for it in items:
            await vc.queue.put_wait(it)
        # refresh_panel uses edit_message; use followup for the notification
        try:
            await interaction.response.edit_message(embed=self.player.build_embed(vc, vc.current), view=self)
        except Exception:
            await interaction.response.defer()
        await interaction.followup.send(embed=embed_success("Queue Shuffled", "Queue order randomized! ⇄"), ephemeral=True)

    @discord.ui.button(label="↻", style=discord.ButtonStyle.secondary, custom_id="loop", row=0)
    async def loop_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        modes = [None, "single", "queue"]
        cur = self.player.loop_mode
        self.player.loop_mode = modes[(modes.index(cur) + 1) % len(modes)] if cur in modes else "single"
        await self.refresh_panel(interaction)

    # ── Row 1: Seeking, Volume & Favorites ────────────────────────────────────

    @discord.ui.button(label="«", style=discord.ButtonStyle.secondary, custom_id="rewind", row=1)
    async def rewind_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc.playing:
            return await interaction.response.send_message(embed=embed_error("Nothing playing."), ephemeral=True)
        new_pos = max(0, vc.position - 10000)
        await vc.seek(new_pos)
        await self.refresh_panel(interaction)

    @discord.ui.button(label="˗", style=discord.ButtonStyle.secondary, custom_id="vol_down", row=1)
    async def vol_down_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        new_vol = max(0, vc.volume - 10)
        await vc.set_volume(new_vol)
        await self.refresh_panel(interaction)

    @discord.ui.button(label="♡", style=discord.ButtonStyle.secondary, custom_id="fav", row=1)
    async def fav_btn(self, interaction: discord.Interaction, _):
        vc: wavelink.Player = interaction.guild.voice_client if interaction.guild else None
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
            fav_embed.set_footer(text=f"Saved from {interaction.guild.name}  •  {BOT_NAME} Music")
            await interaction.user.send(embed=fav_embed)
            await interaction.response.send_message(embed=embed_success("Saved to DMs!", f"Sent **{track.title}** to your DMs! ❤️"), ephemeral=True)
        except Exception:
            await interaction.response.send_message(embed=embed_success("Favorite", f"Liked **{track.title}**!"), ephemeral=True)

    @discord.ui.button(label="➕", style=discord.ButtonStyle.secondary, custom_id="vol_up", row=1)
    async def vol_up_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        new_vol = min(150, vc.volume + 10)
        await vc.set_volume(new_vol)
        await self.refresh_panel(interaction)

    @discord.ui.button(label="»", style=discord.ButtonStyle.secondary, custom_id="forward", row=1)
    async def forward_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        if not vc.playing or not vc.current:
            return await interaction.response.send_message(embed=embed_error("Nothing playing."), ephemeral=True)
        new_pos = min(vc.current.length, vc.position + 10000)
        await vc.seek(new_pos)
        await self.refresh_panel(interaction)

    # ── Row 2: Lyrics, Filters, Queue, 24/7 & Disconnect ──────────────────────

    @discord.ui.button(label="🎙", style=discord.ButtonStyle.secondary, custom_id="lyrics", row=2)
    async def lyrics_btn(self, interaction: discord.Interaction, _):
        vc: wavelink.Player = interaction.guild.voice_client if interaction.guild else None
        if not vc or not vc.current:
            return await interaction.response.send_message(embed=embed_error("Nothing is currently playing."), ephemeral=True)
            
        track = vc.current
        gp = self.get_gp(interaction.guild.id)
        
        lyrics_text = getattr(gp, 'lyrics_cache', {}).get(track.identifier, "")
        
        if not lyrics_text:
            lyrics_text = f"*No lyrics found for **{track.title}**.*"
            
        lyrics_embed = discord.Embed(
            title=f"🎤 Lyrics — {track.title}",
            description=lyrics_text[:3900],
            color=C.BRAND
        )
        lyrics_embed.set_footer(text=f"Artist: {track.author or 'Unknown'}")
        await interaction.response.send_message(embed=lyrics_embed, ephemeral=True)

    @discord.ui.button(label="🎚", style=discord.ButtonStyle.secondary, custom_id="filter", row=2)
    async def filter_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        gp = self.player
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


    @discord.ui.button(label="☰", style=discord.ButtonStyle.secondary, custom_id="queue", row=2)
    async def queue_btn(self, interaction: discord.Interaction, _):
        vc: wavelink.Player = interaction.guild.voice_client if interaction.guild else None
        if not vc or (vc.queue.is_empty and not vc.current):
            return await interaction.response.send_message(embed=embed_info("Queue", "The queue is currently empty."), ephemeral=True)
        lines = []
        if vc.current:
            lines.append(f"**Now Playing:** `{vc.current.title}` ({format_ms(vc.current.length)})")
        if not vc.queue.is_empty:
            lines.append("\n**Up Next:**")
            for i, t in enumerate(list(vc.queue)[:10], 1):
                lines.append(f"`{i}.` **{t.title}** ({format_ms(t.length)})")
            if vc.queue.count > 10:
                lines.append(f"\n*...and {vc.queue.count - 10} more tracks in queue*")
        q_embed = discord.Embed(
            title=f"📜 Music Queue — {interaction.guild.name}",
            description="\n".join(lines),
            color=C.BRAND
        )
        q_embed.set_footer(text=f"Total: {vc.queue.count + (1 if vc.current else 0)} songs")
        await interaction.response.send_message(embed=q_embed, ephemeral=True)

    @discord.ui.button(label="⚡ 24/7", style=discord.ButtonStyle.secondary, custom_id="247", row=2)
    async def mode_247_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        self.player.mode_247 = not self.player.mode_247
        status = "enabled" if self.player.mode_247 else "disabled"
        # Refresh panel first, then notify via followup (avoids double-response crash)
        try:
            vc2 = interaction.guild.voice_client
            await interaction.response.edit_message(
                embed=self.player.build_embed(vc2, getattr(vc2, 'current', None)),
                view=self
            )
        except Exception:
            await interaction.response.defer()
        await interaction.followup.send(
            embed=embed_info("24/7 Mode", f"24/7 playback **{status}**! ⚡"),
            ephemeral=True
        )

    @discord.ui.button(label="✕", style=discord.ButtonStyle.danger, custom_id="stop", row=2)
    async def stop_btn(self, interaction: discord.Interaction, _):
        if not await self._check_voice(interaction): return
        vc: wavelink.Player = interaction.guild.voice_client
        self.player.mode_247 = False
        if vc.channel:
            await set_voice_channel_status(interaction.client, vc.channel.id, "")
        vc.queue.clear()
        await vc.disconnect()
        await interaction.response.send_message(embed=embed_success("Stopped", "Music stopped and disconnected."), ephemeral=True)


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

    def _get_requester(self, track: wavelink.Playable) -> Optional[str]:
        """Safely extract requester from ExtrasNamespace (wavelink 3.x)."""
        try:
            extras = getattr(track, 'extras', None)
            if extras is None:
                return None
            return getattr(extras, 'requester', None)
        except Exception:
            return None

    def build_embed(self, vc: Optional[wavelink.Player], track: Optional[wavelink.Playable] = None) -> discord.Embed:
        embed = discord.Embed(color=C.BRAND)
        # Use bot's own avatar as the author icon (always valid)
        bot_avatar = None
        try:
            import discord as _d
            # pull the bot user off the vc guild client if available
            if vc and vc.guild:
                bot_member = vc.guild.me
                if bot_member and bot_member.display_avatar:
                    bot_avatar = bot_member.display_avatar.url
        except Exception:
            pass
        embed.set_author(name=f"{BOT_NAME.upper()} MUSIC PLAYER", icon_url=bot_avatar)

        if not vc or not vc.playing or not track:
            embed.description = (
                "**No track currently playing.**\n\n"
                "Use `/play <song or link>` or `/random` to start streaming!"
            )
            embed.set_footer(text=f"Queue: 0 tracks · {BOT_NAME} Studio Audio")
            return embed

        self.voice_client = vc
        loop_str = {"single": "🔂 Single", "queue": "🔁 Queue"}.get(self.loop_mode, "Off")
        status_badge = "⏸️ **Paused**" if vc.paused else "🟢 **Playing**"
        requester = self._get_requester(track) or "User"
        duration = format_ms(track.length)

        # ── Polished Modern Dark Typography & Hierarchy ───────────────────────
        desc = (
            f"## [{track.title}]({track.uri})\n"
            f"*by* **{track.author or 'Unknown Artist'}**\n\n"
            f"🔊 `{vc.volume}%`  ·  🎛️ `{self.current_filter}`  ·  🔁 `{loop_str}`  ·  ⚡ `{'24/7 ON' if self.mode_247 else '24/7 OFF'}`\n\n"
            f"🎧 Requested by **{requester}**  ·  {status_badge}"
        )
        embed.description = desc

        # Top Right Thumbnail: High-resolution Artwork / Thumbnail
        artwork = getattr(track, 'artwork_url', None) or getattr(track, 'thumbnail', None)
        if not artwork and hasattr(track, 'identifier') and track.identifier and len(track.identifier) == 11:
            artwork = f"https://i.ytimg.com/vi/{track.identifier}/hqdefault.jpg"
        if artwork:
            embed.set_thumbnail(url=artwork)

        # Bottom Center Visualizer: Stitched Continuous Looping GIF
        embed.set_image(url=MUSIC_VISUALIZER_GIF)

        embed.set_footer(text=f"Queue · {vc.queue.count} tracks   |   Source · {BOT_NAME} Studio Audio")
        return embed

    async def update_panel(self, bot: commands.Bot, track: Optional[wavelink.Playable] = None):
        guild = bot.get_guild(self.guild_id)
        if not guild:
            return
        vc: Optional[wavelink.Player] = guild.voice_client
        self.voice_client = vc

        embed = self.build_embed(vc, track)
        view = MusicControlView(self)

        if self.panel_message:
            try:
                await self.panel_message.edit(embed=embed, view=view)
                return
            except Exception:
                self.panel_message = None

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
            await player.play(payload.track)
            return
        if gp.loop_mode == "queue" and payload.track:
            await player.queue.put_wait(payload.track)

        # Play next — pop directly from queue (no get_wait latency)
        if player.queue.is_empty:
            if player.channel:
                await set_voice_channel_status(self.bot, player.channel.id, "")
            await gp.update_panel(self.bot, None)
            if not gp.mode_247:
                await asyncio.sleep(30)
                if player.queue.is_empty and not player.playing:
                    try:
                        if player.channel:
                            await set_voice_channel_status(self.bot, player.channel.id, "")
                        await player.disconnect()
                    except Exception:
                        pass
        else:
            try:
                next_track = player.queue.get()
                await player.play(next_track)
            except Exception:
                # Fallback to get_wait if get() is not available
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
                if vc2.channel:
                    await set_voice_channel_status(self.bot, vc2.channel.id, "")
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
            "instrumental", "whistle", "flute", "violin", "guitar", "piano",
            "saxophone", "sitar", "veena", "bgm", "background music",
            "ost", "karaoke", "cover", "remix", "slowed", "reverb",
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
    def _rank_tracks(query: str, tracks: List[wavelink.Playable]) -> dict:
        """
        Score candidates and return single best result or ambiguous list.
        Scoring formula:
          FINAL = relevance*0.35 + title*0.25 + artist*0.15 + canonical*0.10
                + official*0.07 + popularity*0.04 + duration*0.04
                - non_music_hard_reject
                - shorts_penalty
                - alternate_version_penalty * 0.60
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
            if MusicCog._is_shorts(uri, raw_title) and not any(v in ("short", "shorts") for v in version_tags):
                # Shorts only allowed if duration > 60s (some legit music is < 90s)
                if length_ms < 60_000:
                    print(f"[Rank] 🚫 Hard-rejected (Shorts): '{raw_title}'")
                    continue
            # Reject extremely long tracks (> 20 min) unless explicitly a mix/compilation
            if length_ms > 1_200_000 and not any(w in norm_query for w in ("mix", "compilation", "playlist", "mashup", "hour")):
                continue

            norm_t = MusicCog._normalize_query(raw_title)
            norm_a = MusicCog._normalize_query(raw_author)

            # ── 1. Title Relevance (0.0–1.0) ─────────────────────────────────
            title_sim = difflib.SequenceMatcher(None, norm_title_intent, norm_t).ratio()
            token_rel = MusicCog._token_relevance(norm_title_intent, norm_t, norm_a)
            relevance_score = (title_sim * 0.6 + token_rel * 0.4)

            # Exact core title word in candidate title (big boost)
            if norm_title_intent and norm_title_intent in norm_t:
                relevance_score = min(1.0, relevance_score + 0.3)

            # ── 2. Artist Match (0.0–1.0) ─────────────────────────────────────
            artist_score = 0.0
            if norm_artist_intent:
                artist_sim = difflib.SequenceMatcher(None, norm_artist_intent, norm_a).ratio()
                artist_token = MusicCog._token_relevance(norm_artist_intent, norm_a, norm_t)
                artist_score = (artist_sim * 0.6 + artist_token * 0.4)
                if norm_artist_intent in norm_a:
                    artist_score = min(1.0, artist_score + 0.3)
            else:
                # No artist in query — use token overlap of full query vs title
                artist_score = MusicCog._token_relevance(norm_query, norm_t, norm_a) * 0.5

            # ── 3. Canonical Version Score (0.0–1.0) ──────────────────────────
            # Penalize alternate versions unless user explicitly asked for them
            alt_penalty = MusicCog._alternate_version_penalty(raw_title, raw_author, version_tags)
            canonical_score = max(0.0, 1.0 - alt_penalty)

            # If user DID ask for a version, boost tracks that match it
            if version_tags:
                combined_lc = (raw_title + " " + raw_author).lower()
                version_match = sum(1 for v in version_tags if v in combined_lc)
                canonical_score = min(1.0, version_match / len(version_tags))

            # ── 4. Official Score (0.0–1.0) ───────────────────────────────────
            official_score = MusicCog._official_score(raw_title, raw_author)

            # ── 5. Popularity Proxy (0.0–1.0) ─────────────────────────────────
            # Search engine returns results roughly sorted by views/relevance.
            # Use rank position as a soft popularity proxy (diminishing returns).
            popularity_score = max(0.0, 1.0 - (rank_idx * 0.08))

            # ── 6. Duration Score (0.0–1.0) ───────────────────────────────────
            # Standard songs: 2:00–6:00 min. Bonus for that range.
            if 100_000 <= length_ms <= 360_000:
                duration_score = 1.0
            elif 60_000 <= length_ms < 100_000:
                duration_score = 0.5   # could be legit short song
            elif length_ms < 60_000:
                duration_score = 0.1   # ringtone / snippet
            else:
                # > 6 min: could be album version, slightly lower
                duration_score = max(0.0, 1.0 - (length_ms - 360_000) / 2_000_000)

            # ── Shorts Penalty ─────────────────────────────────────────────────
            shorts_penalty = 0.5 if MusicCog._is_shorts(uri, raw_title) else 0.0

            # ── FINAL SCORE ────────────────────────────────────────────────────
            final = (
                relevance_score  * 0.35
                + relevance_score  * 0.25  # title component doubled (dominant)
                + artist_score     * 0.15
                + canonical_score  * 0.10
                + official_score   * 0.07
                + popularity_score * 0.04
                + duration_score   * 0.04
                - shorts_penalty
                - (alt_penalty * 0.60)  # strong penalty for unwanted alternate versions
            )

            # Critical guard: if relevance is near zero, this result is wrong.
            # Don't let official/popularity scores rescue an irrelevant result.
            if relevance_score < 0.10 and not norm_artist_intent:
                final = min(final, 0.05)

            scored.append((final, rank_idx, track, {
                "relevance": round(relevance_score, 3),
                "artist": round(artist_score, 3),
                "canonical": round(canonical_score, 3),
                "official": round(official_score, 3),
                "popularity": round(popularity_score, 3),
                "duration": round(duration_score, 3),
                "final": round(final, 3),
            }))

        if not scored:
            # All candidates were rejected — return first non-stream as emergency fallback
            for tr in tracks:
                if not getattr(tr, "is_stream", False):
                    print(f"[Rank] ⚠️ All candidates rejected, emergency fallback to: '{tr.title}'")
                    return {"type": "single", "track": tr}
            return {"type": "error", "message": "No playable results found"}

        # Sort by final score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # ── Structured Logging ────────────────────────────────────────────────
        print(f"\n━━━━━━━━ SEARCH RANKING ━━━━━━━━")
        print(f"QUERY: \"{raw_query}\"")
        for i, (final, ri, tr, dbg) in enumerate(scored[:5]):
            print(f"\n  #{i+1} [{ri}] {tr.title[:60]} — {tr.author or 'N/A'}")
            print(f"       relevance={dbg['relevance']} artist={dbg['artist']} "
                  f"canonical={dbg['canonical']} official={dbg['official']} "
                  f"popularity={dbg['popularity']} FINAL={dbg['final']}")
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
                return {"type": "single", "track": best_track}

            elif best_final >= 0.45 and gap >= 0.06:
                # Moderate confidence with a clear gap over second place
                print(f"[Rank] ✅ MODERATE confidence ({best_final:.3f}, gap={gap:.3f}), auto-playing: \"{best_track.title}\"")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                return {"type": "single", "track": best_track}

            elif best_final < 0.30:
                # Low confidence — let user choose
                print(f"[Rank] ❓ LOW confidence ({best_final:.3f}), showing menu")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                candidates = [t for _, _, t, _ in scored[:5]]
                return {"type": "ambiguous", "tracks": candidates}

            else:
                # Mid-range score with close competitors — show menu
                print(f"[Rank] ❓ AMBIGUOUS ({best_final:.3f}, gap={gap:.3f}), showing menu")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                candidates = [t for _, _, t, _ in scored[:5]]
                return {"type": "ambiguous", "tracks": candidates}
        else:
            print(f"[Rank] ✅ Only 1 candidate, auto-playing: \"{best_track.title}\"")
            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        return {"type": "single", "track": best_track}


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
        explicit_prefixes = ("ytsearch:", "ytmsearch:", "spsearch:", "scsearch:", "dzsearch:", "amsearch:")
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
                ("scsearch", f"scsearch:{clean_q}"),
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
            ("scsearch", clean_query),
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
        """Resolve one search and trust _rank_tracks for the final decision."""
        import time

        if not wavelink.Pool.nodes:
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

        provider = "ytmsearch"
        search_text = original_query
        prefixes = ("ytsearch:", "ytmsearch:", "spsearch:", "scsearch:", "dzsearch:", "amsearch:")
        if query.lower().startswith(prefixes):
            provider, search_text = query.split(":", 1)

        filler = re.compile(
            r"\b(full song|full video song|official song|official music video|official audio|"
            r"official video|music video|audio|video|song|track|music|mp3|hd|4k)\b",
            re.IGNORECASE,
        )
        search_text = re.sub(r"\s+", " ", filler.sub("", search_text)).strip() or search_text

        started = time.time()
        try:
            results = await wavelink.Playable.search(search_text, source=provider)
            finished = time.time()
            print(f"[Music] {provider}: {len(results) if results else 0} results ({finished - started:.2f}s)")
            if gp:
                gp.metrics["load_start"] = started
                gp.metrics["load_end"] = finished
        except Exception as exc:
            print(f"[Music] {provider} failed: {exc}")
            return {"type": "error", "message": "Music search failed. Try again or use Artist - Song."}

        if not results:
            return {"type": "error", "message": "No playable music was found."}

        ranked = self._rank_tracks(search_text, list(results))
        if ranked.get("type") == "single":
            return {"type": "single", "track": tag(ranked["track"])}
        if ranked.get("type") == "ambiguous":
            return {"type": "ambiguous", "tracks": [tag(track) for track in ranked["tracks"]]}
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

        # 2. Connect
        gp.metrics["voice_start"] = time.time()
        vc = interaction.guild.voice_client
        if not vc:
            await set_india_voice_region(user_channel)
            vc = await user_channel.connect(cls=wavelink.Player, self_deaf=True)
        elif vc.channel != user_channel:
            await set_india_voice_region(user_channel)
            await vc.move_to(user_channel)
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
            
            await vc.set_volume(100)
            await vc.play(first_track)
            import asyncio
            asyncio.create_task(self._wait_for_audio_flow(vc, gp))
            
            embed = embed_success("⏳ Loading", f"Starting **{first_track.title}**...")
            if len(tracks) > 1:
                embed.set_footer(text=f"+{len(tracks)-1} more in queue")
            if interaction.response.is_done(): await interaction.edit_original_response(embed=embed, view=None)
            else: await interaction.response.send_message(embed=embed)
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
        vc: Optional[wavelink.Player] = interaction.guild.voice_client

        if not vc:
            try:
                await set_india_voice_region(user_channel)
                vc = await user_channel.connect(cls=wavelink.Player)
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
            "scsearch:trending music"
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
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(embed=embed_error("Not connected."), ephemeral=True)
        gp = self.get_gp(interaction.guild.id)
        gp.mode_247 = False
        if vc.channel:
            await set_voice_channel_status(self.bot, vc.channel.id, "")
        vc.queue.clear()
        await vc.disconnect()
        await interaction.response.send_message(embed=embed_success("Stopped", "Stopped and disconnected."))

    @app_commands.command(name="skip", description="Skip the current track.")
    async def skip(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=embed_error("Nothing playing."), ephemeral=True)
        await vc.skip(force=True)
        await interaction.response.send_message(embed=embed_success("Skipped", "Skipped track."))

    @app_commands.command(name="pause", description="Pause the current track.")
    async def pause(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=embed_error("Nothing playing."), ephemeral=True)
        await vc.pause(True)
        if vc.channel and vc.current:
            await set_voice_channel_status(self.bot, vc.channel.id, f"⏸️ Paused: {vc.current.title[:85]}")
        await interaction.response.send_message(embed=embed_success("Paused", "Paused playback."))

    @app_commands.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
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
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(embed=embed_error("Not connected."), ephemeral=True)
        await vc.set_volume(level)
        await interaction.response.send_message(embed=embed_success("Volume", f"Volume set to **{level}%**"))

    @app_commands.command(name="filter", description="Open the audio filter control panel.")
    async def filter_cmd(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
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
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
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
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
        if not vc or not vc.playing:
            return await interaction.response.send_message(embed=embed_error("Nothing is currently playing."), ephemeral=True)

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
        await interaction.response.send_message(embed=embed_info("Loop Mode", f"Loop mode: **{mode_str}**"))

    @app_commands.command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, interaction: discord.Interaction):
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
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
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
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
        vc: Optional[wavelink.Player] = interaction.guild.voice_client
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
