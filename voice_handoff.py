"""
voice_handoff.py — Coordinates the ONE voice connection Discord allows per
guild between the Radio cog (plain discord.VoiceClient + FFmpeg) and the
Music cog (wavelink.Player, Lavalink-backed).

Without this, whichever system connected second would either crash trying
to use attributes the other system's client doesn't have
(AttributeError: 'VoiceClient' object has no attribute 'queue' / '.paused',
or 'Player' object has no attribute 'is_connected') or silently kill the
other system's session with no way to resume it.

The flow this module implements:
  1. Before System A connects, it calls `yield_voice_to(bot, guild, "A")`.
     If System B currently owns the connection, B's `suspend_for_handoff()`
     is called — B saves whatever it needs (queue, current track/position
     for music; station/volume for radio) and disconnects cleanly.
  2. System A connects fresh with its own client type and plays normally.
  3. When System A's session naturally ends (queue empties and it's not in
     24/7 mode, or the user explicitly stops it), it calls
     `restore_voice_from(bot, guild, "A")`, which calls B's
     `resume_from_handoff()` if B had been suspended — B reconnects to the
     same channel and picks back up where it left off.

Both `suspend_for_handoff(guild) -> bool` and `resume_from_handoff(guild) ->
bool` are optional cog methods — this module only calls them if present, so
neither cog is required to implement both directions.
"""

from __future__ import annotations

import discord
from typing import Optional


def is_connected(vc) -> bool:
    """Works for both discord.VoiceClient (is_connected()) and
    wavelink.Player (.connected property)."""
    if vc is None:
        return False
    fn = getattr(vc, "is_connected", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            pass
    if hasattr(vc, "connected"):
        return bool(vc.connected)
    return getattr(vc, "channel", None) is not None


def is_playing(vc) -> bool:
    if vc is None:
        return False
    fn = getattr(vc, "is_playing", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            pass
    return bool(getattr(vc, "playing", False))


def is_paused(vc) -> bool:
    if vc is None:
        return False
    fn = getattr(vc, "is_paused", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            pass
    return bool(getattr(vc, "paused", False))


_OTHER_COG = {
    "radio": "MusicCog",
    "music": "Radio System",
}


async def yield_voice_to(bot: discord.Client, guild: discord.Guild, requester: str) -> None:
    """
    Call this right before `requester` ("radio" or "music") connects its own
    voice client in `guild`. Gives the OTHER system a chance to save its
    state and disconnect cleanly first, instead of being killed out from
    under it.
    """
    other = bot.get_cog(_OTHER_COG.get(requester, ""))
    if not other:
        return
    suspend = getattr(other, "suspend_for_handoff", None)
    if suspend:
        try:
            await suspend(guild)
        except Exception as e:
            print(f"[VoiceHandoff] {_OTHER_COG.get(requester)}.suspend_for_handoff failed: {e}")


async def restore_voice_from(bot: discord.Client, guild: discord.Guild, finisher: str) -> bool:
    """
    Call this once `finisher`'s ("radio" or "music") own session has
    naturally ended (queue empty & not 24/7, or explicitly stopped) to hand
    the voice channel back to the other system if it was suspended earlier.
    Returns True if something was actually resumed.
    """
    other = bot.get_cog(_OTHER_COG.get(finisher, ""))
    if not other:
        return False
    resume = getattr(other, "resume_from_handoff", None)
    if not resume:
        return False
    try:
        return bool(await resume(guild))
    except Exception as e:
        print(f"[VoiceHandoff] {_OTHER_COG.get(finisher)}.resume_from_handoff failed: {e}")
        return False
