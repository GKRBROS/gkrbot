"""
voice_announce.py — Voice Channel Announcer Cog

Join any specific voice channel, OR every voice channel under a category,
and speak a TTS announcement out loud in any supported language.

Uses Microsoft Edge neural voices (edge-tts) — free, no API key, real
speech quality (not the old robotic translate_tts endpoint).

Requirements:
    pip install edge-tts PyNaCl imageio-ffmpeg
    ffmpeg installed and on PATH (or bundled via imageio-ffmpeg)

Load it like any other cog, e.g. in your bot's setup:
    await bot.load_extension("voice_announce")
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import shutil
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("gkr_voice_announce")

# ---------------------------------------------------------------------------
# Language -> Edge neural voice map. Add more from `edge-tts --list-voices`.
# ---------------------------------------------------------------------------
VOICES = {
    "en": ("English (US)", "en-US-AriaNeural"),
    "en-gb": ("English (UK)", "en-GB-SoniaNeural"),
    "es": ("Spanish", "es-ES-ElviraNeural"),
    "fr": ("French", "fr-FR-DeniseNeural"),
    "de": ("German", "de-DE-KatjaNeural"),
    "ja": ("Japanese", "ja-JP-NanamiNeural"),
    "hi": ("Hindi", "hi-IN-SwaraNeural"),
    "ml": ("Malayalam", "ml-IN-SobhanaNeural"),
    "ta": ("Tamil", "ta-IN-PallaviNeural"),
    "ko": ("Korean", "ko-KR-SunHiNeural"),
    "ar": ("Arabic", "ar-SA-ZariyahNeural"),
    "ru": ("Russian", "ru-RU-SvetlanaNeural"),
    "it": ("Italian", "it-IT-ElsaNeural"),
    "pt": ("Portuguese", "pt-BR-FranciscaNeural"),
    "zh": ("Chinese (Mandarin)", "zh-CN-XiaoxiaoNeural"),
}

LANGUAGE_CHOICES = [app_commands.Choice(name=name, value=code) for code, (name, _) in VOICES.items()]


def get_ffmpeg_executable() -> str:
    """Find the path to the ffmpeg executable on system or bundled via imageio_ffmpeg."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


async def synthesize(text: str, lang: str, rate: str = "+0%") -> Optional[io.BytesIO]:
    """Render text to MP3 bytes in memory using an Edge neural voice."""
    _, voice_id = VOICES.get(lang, VOICES["en"])
    clean = text.strip()[:1000]
    if not clean:
        return None
    # Manglish/Hinglish typed in Latin letters (e.g. "evideya", "sugam")
    # gets converted to native script here, since the neural voice only
    # reads the script it's built for.
    try:
        from manglish_translit import transliterate_colloquial
        clean = transliterate_colloquial(clean, lang)
    except ImportError:
        pass
    try:
        import edge_tts
        communicate = edge_tts.Communicate(clean, voice_id, rate=rate)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        if buf.tell() == 0:
            return None
        buf.seek(0)
        return buf
    except ImportError:
        logger.error("edge-tts not installed. Run: pip install edge-tts")
        return None
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        return None


class VoiceAnnounceCog(commands.Cog, name="Voice Announcer"):
    """Speak announcements into voice channels on demand."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # one lock per guild so two announcements can't fight over the same voice client
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]

    async def _play_in_channel(
        self,
        channel: discord.VoiceChannel,
        audio_buf: io.BytesIO,
    ) -> tuple[bool, str]:
        """Connect to `channel`, play the given MP3 buffer, then disconnect."""
        vc: Optional[discord.VoiceClient] = None
        try:
            vc = await channel.connect(timeout=15, reconnect=False, self_deaf=True)
        except discord.ClientException:
            # already connected somewhere in this guild — move instead
            vc = channel.guild.voice_client
            if vc is None:
                return False, "Could not connect to voice."
            await vc.move_to(channel)
        except Exception as e:
            return False, f"Connection failed: {e}"

        try:
            if vc.is_playing():
                vc.stop()
            audio_buf.seek(0)
            ffmpeg_exe = get_ffmpeg_executable()
            source = discord.FFmpegPCMAudio(audio_buf, pipe=True, executable=ffmpeg_exe)
            done = asyncio.Event()

            def _after(err):
                if err:
                    logger.error(f"Playback error in #{channel.name}: {err}")
                self.bot.loop.call_soon_threadsafe(done.set)

            vc.play(source, after=_after)
            await asyncio.wait_for(done.wait(), timeout=60)
            return True, "ok"
        except asyncio.TimeoutError:
            return False, "Playback timed out."
        except Exception as e:
            return False, f"Playback failed: {e}"
        finally:
            if vc is not None and vc.is_connected():
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass

    announce_group = app_commands.Group(
        name="announce",
        description="🔊 Speak a voice announcement into Discord voice channels.",
        default_permissions=discord.Permissions(mute_members=True),
    )

    @announce_group.command(name="channel", description="Announce a message in one specific voice channel.")
    @app_commands.describe(
        channel="The voice channel to speak in",
        text="What to say (max 1000 characters)",
        language="Language / accent to speak in",
        speed="Speaking speed, e.g. -20% slower, +20% faster (default +0%)",
    )
    @app_commands.choices(language=LANGUAGE_CHOICES)
    async def announce_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        text: str,
        language: Optional[app_commands.Choice[str]] = None,
        speed: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        lang_code = language.value if language else "en"
        rate = speed.strip() if speed else "+0%"

        audio_buf = await synthesize(text, lang_code, rate)
        if not audio_buf:
            await interaction.followup.send(
                "❌ Could not synthesize speech. Is `edge-tts` installed on the host?", ephemeral=True
            )
            return

        async with self._lock(interaction.guild_id or 0):
            ok, msg = await self._play_in_channel(channel, audio_buf)

        if ok:
            await interaction.followup.send(f"🔊 Announced in **{channel.name}**.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)

    @announce_group.command(name="category", description="Announce a message in every voice channel under a category.")
    @app_commands.describe(
        category="The category whose voice channels should hear the announcement",
        text="What to say (max 1000 characters)",
        language="Language / accent to speak in",
        speed="Speaking speed, e.g. -20% slower, +20% faster (default +0%)",
    )
    @app_commands.choices(language=LANGUAGE_CHOICES)
    async def announce_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        text: str,
        language: Optional[app_commands.Choice[str]] = None,
        speed: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        lang_code = language.value if language else "en"
        rate = speed.strip() if speed else "+0%"

        voice_channels = [c for c in category.channels if isinstance(c, discord.VoiceChannel)]
        if not voice_channels:
            await interaction.followup.send("❌ That category has no voice channels.", ephemeral=True)
            return

        audio_buf = await synthesize(text, lang_code, rate)
        if not audio_buf:
            await interaction.followup.send(
                "❌ Could not synthesize speech. Is `edge-tts` installed on the host?", ephemeral=True
            )
            return
        raw_audio = audio_buf.getvalue()  # reused per-channel; a Discord voice connection is per-guild, so this runs sequentially

        results = []
        async with self._lock(interaction.guild_id or 0):
            for vch in voice_channels:
                ok, msg = await self._play_in_channel(vch, io.BytesIO(raw_audio))
                results.append(f"{'✅' if ok else '❌'} {vch.name}" + ("" if ok else f" — {msg}"))

        await interaction.followup.send(
            f"🔊 Announced in **{len(voice_channels)}** channel(s) under **{category.name}**:\n" + "\n".join(results),
            ephemeral=True,
        )

    @announce_group.command(name="stop", description="Force the bot to leave its current voice channel in this server.")
    async def announce_stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc and vc.is_connected():
            await vc.disconnect(force=True)
            await interaction.response.send_message("🔇 Disconnected.", ephemeral=True)
        else:
            await interaction.response.send_message("I'm not in a voice channel here.", ephemeral=True)

    @announce_channel.error
    @announce_category.error
    @announce_stop.error
    async def on_announce_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ You need the **Mute Members** permission to use this."
        else:
            logger.error(f"Announce command error: {error}")
            msg = f"❌ Something went wrong: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceAnnounceCog(bot))
    print("🔊 Voice Announcer cog loaded!")