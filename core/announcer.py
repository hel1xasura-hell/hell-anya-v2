"""
core/announcer.py
==================
Bridges :class:`~core.player.Player` lifecycle events to actual Telegram
messages. Registered once at startup (see ``main.py``), this guarantees a
now-playing card is posted for *every* track start — whether triggered by
``/play``, ``/skip``, or the queue auto-advancing when a track ends
naturally — without duplicating that logic across plugins.
"""

from __future__ import annotations

import logging

from pyrogram import Client

from config import config
from core.models import Track
from utils.formatters import format_duration
from utils.keyboards import playback_controls
from utils.thumbnail import generate_now_playing_card

logger = logging.getLogger(__name__)


def register_announcer(client: Client) -> None:
    """Attach now-playing / queue-finished announcers to ``client.player``."""

    player = client.player
    if player is None:
        return

    async def announce_track_start(chat_id: int, track: Track, _position: int) -> None:
        try:
            state = player.current_state(chat_id)
            card_path = await generate_now_playing_card(
                title=track.title,
                artist=track.artist,
                duration_seconds=track.duration_seconds,
                elapsed_seconds=0,
                thumbnail_url=track.thumbnail_url,
                requested_by=track.requested_by_name,
                queue_position=0,
            )
            await client.send_photo(
                chat_id,
                photo=str(card_path),
                caption=(
                    f"🎶 **Now Playing**\n\n"
                    f"**{track.title}**\n"
                    f"👤 {track.artist}\n"
                    f"⏱ {format_duration(track.duration_seconds)}\n"
                    f"🙋 Requested by {track.requested_by_name}"
                ),
                reply_markup=playback_controls(state.is_paused, state.loop_mode),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to announce now-playing card for chat %s", chat_id)

    async def announce_queue_finished(chat_id: int) -> None:
        try:
            await client.send_message(chat_id, "✅ Queue finished — left the voice chat. Use /play to start a new session.")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to announce queue-finished for chat %s", chat_id)

    player.on_track_start(announce_track_start)
    player.on_queue_finished(announce_queue_finished)
    logger.info("Announcer wired to player events.")
