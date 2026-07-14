"""
core/queue_manager.py
======================
Manages one playback queue + state object per chat.

ᴀɴʏᴀ is scoped to a single authorised group, so in practice only one
``ChatQueue`` will ever be active — but modelling it per-chat-id keeps the
implementation honest and trivially extensible if the single-group
restriction is ever relaxed.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

from core.models import LoopMode, PlaybackState, Track


@dataclass(slots=True)
class ChatQueue:
    """The pending tracks and playback state for one chat."""

    tracks: list[Track] = field(default_factory=list)
    state: PlaybackState = field(default_factory=PlaybackState)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class QueueManager:
    """Registry of :class:`ChatQueue` instances keyed by chat id."""

    def __init__(self, max_queue_size: int = 50) -> None:
        self._max_queue_size = max_queue_size
        self._queues: dict[int, ChatQueue] = {}

    def get(self, chat_id: int) -> ChatQueue:
        """Return (creating if necessary) the queue for a chat."""

        if chat_id not in self._queues:
            self._queues[chat_id] = ChatQueue()
        return self._queues[chat_id]

    async def enqueue(self, chat_id: int, track: Track) -> int:
        """Append a track. Returns its 1-based position in the queue."""

        chat_queue = self.get(chat_id)
        async with chat_queue.lock:
            if len(chat_queue.tracks) >= self._max_queue_size:
                raise OverflowError(f"Queue is full (max {self._max_queue_size} tracks).")
            chat_queue.tracks.append(track)
            return len(chat_queue.tracks)

    async def pop_next(self, chat_id: int) -> Track | None:
        """Pop and return the next track to play, honouring loop mode."""

        chat_queue = self.get(chat_id)
        async with chat_queue.lock:
            state = chat_queue.state

            if state.loop_mode is LoopMode.TRACK and state.current is not None:
                return state.current

            if not chat_queue.tracks:
                return None

            next_track = chat_queue.tracks.pop(0)

            if state.loop_mode is LoopMode.QUEUE and state.current is not None:
                chat_queue.tracks.append(state.current)

            return next_track

    async def clear(self, chat_id: int) -> int:
        """Remove all pending tracks. Returns the number cleared."""

        chat_queue = self.get(chat_id)
        async with chat_queue.lock:
            count = len(chat_queue.tracks)
            chat_queue.tracks.clear()
            return count

    async def remove_at(self, chat_id: int, position: int) -> Track | None:
        """Remove the track at 1-based ``position``. Returns it, or ``None``."""

        chat_queue = self.get(chat_id)
        async with chat_queue.lock:
            index = position - 1
            if 0 <= index < len(chat_queue.tracks):
                return chat_queue.tracks.pop(index)
            return None

    async def shuffle(self, chat_id: int) -> None:
        chat_queue = self.get(chat_id)
        async with chat_queue.lock:
            random.shuffle(chat_queue.tracks)

    def snapshot(self, chat_id: int) -> list[Track]:
        """Return a shallow copy of the pending queue (no lock — read-only UI use)."""

        return list(self.get(chat_id).tracks)

    def is_empty(self, chat_id: int) -> bool:
        return len(self.get(chat_id).tracks) == 0

    def reset(self, chat_id: int) -> None:
        """Fully reset a chat's queue and playback state (used on /end)."""

        self._queues[chat_id] = ChatQueue()
