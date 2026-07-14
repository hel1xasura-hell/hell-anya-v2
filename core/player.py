"""
core/player.py
===============
The playback orchestrator: the single object that ties together the
:class:`~core.queue_manager.QueueManager`, the
:class:`~core.voice_engine.VoiceEngine` and the
:class:`~database.base.Database`.

Plugins call methods on a shared :class:`Player` instance rather than
touching PyTgCalls or the queue manager directly — this is the seam that
keeps ``plugins/`` thin and testable.
"""

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from config import config
from core.models import LoopMode, PlaybackState, Track
from core.queue_manager import QueueManager
from core.voice_engine import NoActiveVoiceChatError, VoiceEngine
from database.base import Database

logger = logging.getLogger(__name__)

TrackAnnouncer = Callable[[int, Track, int], Awaitable[None]]
"""Signature: (chat_id, track, queue_position_when_started) -> None"""


class Player:
    """High-level playback API used by every plugin."""

    def __init__(self, queue_manager: QueueManager, voice_engine: VoiceEngine, database: Database) -> None:
        self.queues = queue_manager
        self.voice = voice_engine
        self.db = database
        self._on_track_start: TrackAnnouncer | None = None
        self._on_queue_finished: Callable[[int], Awaitable[None]] | None = None
        self.voice.set_stream_end_callback(self._handle_stream_ended)

    def on_track_start(self, callback: TrackAnnouncer) -> None:
        """Register the coroutine used to announce a new "now playing" card."""

        self._on_track_start = callback

    def on_queue_finished(self, callback: Callable[[int], Awaitable[None]]) -> None:
        """Register the coroutine invoked once the queue is fully drained."""

        self._on_queue_finished = callback

    async def play_or_enqueue(self, chat_id: int, track: Track) -> tuple[bool, int]:
        """Play ``track`` immediately if nothing is playing, else enqueue it.

        Returns ``(started_immediately, position)``.
        """

        chat_queue = self.queues.get(chat_id)
        if chat_queue.state.current is None:
            await self._start_track(chat_id, track)
            return True, 0

        position = await self.queues.enqueue(chat_id, track)
        return False, position

    async def _start_track(self, chat_id: int, track: Track) -> None:
        chat_queue = self.queues.get(chat_id)
        state = chat_queue.state

        try:
            await self.voice.join_and_play(
                chat_id,
                track.stream_url,
                volume=state.volume or config.default_volume,
                http_headers=track.http_headers,
            )
        except NoActiveVoiceChatError:
            raise

        state.current = track
        state.started_at = time.time()
        state.paused_at = None
        state.is_paused = False
        self.voice.cancel_inactivity_leave(chat_id)

        await self.db.record_play(chat_id, track.requested_by_id, track.title)

        if self._on_track_start is not None:
            await self._on_track_start(chat_id, track, 0)

    async def _handle_stream_ended(self, chat_id: int) -> None:
        await self.skip(chat_id, announce_skip=False)

    async def skip(self, chat_id: int, announce_skip: bool = True) -> Track | None:
        """Advance to the next track, or stop and schedule auto-leave if empty."""

        next_track = await self.queues.pop_next(chat_id)
        if next_track is None:
            chat_queue = self.queues.get(chat_id)
            chat_queue.state = PlaybackState()
            await self.voice.leave(chat_id)
            if self._on_queue_finished is not None:
                await self._on_queue_finished(chat_id)
            return None

        await self._start_track(chat_id, next_track)
        return next_track

    async def pause(self, chat_id: int) -> None:
        chat_queue = self.queues.get(chat_id)
        await self.voice.pause(chat_id)
        chat_queue.state.is_paused = True
        chat_queue.state.paused_at = time.time()
        self.voice.schedule_inactivity_leave(chat_id, config.inactivity_timeout_seconds, self._handle_inactivity_timeout)

    async def _handle_inactivity_timeout(self, chat_id: int) -> None:
        logger.info("Auto-leaving chat %s after %ss of inactivity.", chat_id, config.inactivity_timeout_seconds)
        await self.stop(chat_id)
        if self._on_queue_finished is not None:
            await self._on_queue_finished(chat_id)

    async def resume(self, chat_id: int) -> None:
        chat_queue = self.queues.get(chat_id)
        state = chat_queue.state
        await self.voice.resume(chat_id)
        self.voice.cancel_inactivity_leave(chat_id)
        if state.is_paused and state.paused_at and state.started_at:
            paused_duration = time.time() - state.paused_at
            state.started_at += paused_duration
        state.is_paused = False
        state.paused_at = None

    async def stop(self, chat_id: int) -> None:
        """Stop playback and clear the queue entirely (used by /stop and /end)."""

        await self.queues.clear(chat_id)
        self.queues.reset(chat_id)
        await self.voice.leave(chat_id)

    async def set_volume(self, chat_id: int, volume: int) -> None:
        chat_queue = self.queues.get(chat_id)
        volume = max(0, min(200, volume))
        chat_queue.state.volume = volume
        await self.voice.set_volume(chat_id, volume)
        await self.db.set_chat_setting(chat_id, "volume", volume)

    async def set_loop(self, chat_id: int, mode: LoopMode) -> None:
        chat_queue = self.queues.get(chat_id)
        chat_queue.state.loop_mode = mode
        await self.db.set_chat_setting(chat_id, "loop_mode", mode.name)

    async def replay(self, chat_id: int) -> Track | None:
        """Restart the currently playing track from the beginning."""

        chat_queue = self.queues.get(chat_id)
        current = chat_queue.state.current
        if current is None:
            return None
        await self._start_track(chat_id, current)
        return current

    async def seek(self, chat_id: int, seconds: int) -> Track | None:
        chat_queue = self.queues.get(chat_id)
        current = chat_queue.state.current
        if current is None:
            return None
        await self.voice.seek(chat_id, current.stream_url, seconds, http_headers=current.http_headers)
        chat_queue.state.started_at = time.time() - seconds
        return current

    def current_state(self, chat_id: int) -> PlaybackState:
        return self.queues.get(chat_id).state
    
