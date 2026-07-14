"""
core/models.py
===============
Plain dataclasses describing the domain: a queued track and the current
playback state of a chat. Keeping these free of any Pyrogram/PyTgCalls
dependency makes them trivial to unit test and to (de)serialise.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto


class LoopMode(Enum):
    """Repeat behaviour for the current chat's queue."""

    OFF = auto()
    TRACK = auto()
    QUEUE = auto()


class SourceType(Enum):
    """Where a track's playable stream originates from."""

    YOUTUBE = auto()
    SPOTIFY = auto()
    DIRECT_URL = auto()


@dataclass(slots=True)
class Track:
    """A single queued or playing song."""

    title: str
    artist: str
    duration_seconds: int
    stream_url: str
    thumbnail_url: str
    webpage_url: str
    requested_by_id: int
    requested_by_name: str
    source: SourceType = SourceType.YOUTUBE
    added_at: float = field(default_factory=time.time)
    http_headers: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "duration_seconds": self.duration_seconds,
            "stream_url": self.stream_url,
            "thumbnail_url": self.thumbnail_url,
            "webpage_url": self.webpage_url,
            "requested_by_id": self.requested_by_id,
            "requested_by_name": self.requested_by_name,
            "source": self.source.name,
        }


@dataclass(slots=True)
class PlaybackState:
    """Runtime playback state tracked per authorised chat."""

    current: Track | None = None
    started_at: float | None = None
    paused_at: float | None = None
    volume: int = 100
    loop_mode: LoopMode = LoopMode.OFF
    is_paused: bool = False

    def elapsed_seconds(self) -> int:
        """Best-effort elapsed playback time, accounting for pauses."""

        if self.started_at is None:
            return 0
        reference = self.paused_at if self.is_paused and self.paused_at else time.time()
        return max(0, int(reference - self.started_at))
    
