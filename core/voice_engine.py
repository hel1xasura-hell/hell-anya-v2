"""
core/voice_engine.py
=====================
Thin, well-documented wrapper around PyTgCalls.

Every interaction with the voice-chat layer goes through
:class:`VoiceEngine` so that plugins never touch ``PyTgCalls`` directly.
This keeps upgrade paths (PyTgCalls API changes between major versions
fairly often) contained to a single file, and lets us centralise error
translation, inactivity tracking and automatic-leave logic.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from pytgcalls import PyTgCalls
from pytgcalls.exceptions import NoActiveGroupCall
from pytgcalls.types import MediaStream, Update

from config import config

logger = logging.getLogger(__name__)

OnStreamEndCallback = Callable[[int], Awaitable[None]]


class NoActiveVoiceChatError(RuntimeError):
    """Raised when a chat has no active voice chat to join."""


@dataclass(slots=True)
class InactivityTracker:
    """Tracks per-chat idle time so we can auto-leave stale voice chats."""

    tasks: dict[int, asyncio.Task] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.tasks = {}

    def cancel(self, chat_id: int) -> None:
        task = self.tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()


class VoiceEngine:
    """Facade over PyTgCalls providing join/play/pause/resume/stop/volume/seek."""

    def __init__(self, calls_client: PyTgCalls) -> None:
        self._calls = calls_client
        self._on_stream_end: OnStreamEndCallback | None = None
        self._inactivity = InactivityTracker()
        self._calls.on_update()(self._handle_update)

    def set_stream_end_callback(self, callback: OnStreamEndCallback) -> None:
        """Register the coroutine invoked when a track finishes naturally."""

        self._on_stream_end = callback

    async def _handle_update(self, _client: PyTgCalls, update: Update) -> None:
        # PyTgCalls has relocated/renamed its stream-end event class across
        # releases (e.g. StreamAudioEnded, StreamEnded). Matching on the
        # runtime class name rather than importing a specific class keeps
        # this working across versions without needing to track that
        # internal reshuffling here.
        update_type_name = type(update).__name__
        is_stream_end = "StreamEnded" in update_type_name or "StreamAudioEnded" in update_type_name

        if is_stream_end and self._on_stream_end is not None:
            chat_id = getattr(update, "chat_id", None)
            if chat_id is not None:
                await self._on_stream_end(chat_id)
        else:
            logger.debug("Unhandled PyTgCalls update type: %s", update_type_name)

    @staticmethod
    def _build_header_args(http_headers: dict | None) -> str:
        """Format headers as an ffmpeg ``-headers`` argument.

        Without matching headers (User-Agent, Referer, etc. as negotiated by
        yt-dlp), YouTube's CDN often accepts the connection but serves an
        empty/silent stream — the join succeeds and no error is raised, it
        just never produces audio. Forwarding yt-dlp's own headers to
        ffmpeg is the standard fix for that.
        """

        if not http_headers:
            return ""
        header_lines = "".join(f"{key}: {value}\r\n" for key, value in http_headers.items())
        return f'-headers "{header_lines}"'

    async def join_and_play(
        self,
        chat_id: int,
        stream_url: str,
        volume: int = 100,
        http_headers: dict | None = None,
    ) -> None:
        """Join the chat's voice chat (if needed) and start streaming ``stream_url``."""

        try:
            await self._calls.play(
                chat_id,
                MediaStream(
                    stream_url,
                    video_flags=MediaStream.Flags.IGNORE,
                    ffmpeg_parameters=self._build_header_args(http_headers) or None,
                ),
            )
            await self.set_volume(chat_id, volume)
        except NoActiveGroupCall as exc:
            raise NoActiveVoiceChatError(str(exc)) from exc

    async def change_stream(self, chat_id: int, stream_url: str, http_headers: dict | None = None) -> None:
        """Switch the currently playing stream without leaving the call."""

        await self._calls.play(
            chat_id,
            MediaStream(
                stream_url,
                video_flags=MediaStream.Flags.IGNORE,
                ffmpeg_parameters=self._build_header_args(http_headers) or None,
            ),
        )

    async def pause(self, chat_id: int) -> None:
        await self._calls.pause(chat_id)

    async def resume(self, chat_id: int) -> None:
        await self._calls.resume(chat_id)

    async def leave(self, chat_id: int) -> None:
        self._inactivity.cancel(chat_id)
        try:
            await self._calls.leave_call(chat_id)
        except Exception:  # noqa: BLE001 - leaving is always best-effort
            logger.debug("leave_call raised for chat %s (likely already left)", chat_id, exc_info=True)

    async def set_volume(self, chat_id: int, volume: int) -> None:
        volume = max(0, min(200, volume))
        await self._calls.change_volume_call(chat_id, volume)

    async def seek(self, chat_id: int, stream_url: str, seconds: int, http_headers: dict | None = None) -> None:
        """Restart the stream at a given offset (PyTgCalls has no native seek
        for arbitrary remote streams, so we re-invoke ffmpeg with -ss)."""

        header_args = self._build_header_args(http_headers)
        ffmpeg_parameters = f"-ss {seconds} {header_args}".strip()
        await self._calls.play(
            chat_id,
            MediaStream(
                stream_url,
                video_flags=MediaStream.Flags.IGNORE,
                ffmpeg_parameters=ffmpeg_parameters,
            ),
        )

    def schedule_inactivity_leave(self, chat_id: int, delay_seconds: int, on_timeout: Callable[[int], Awaitable[None]]) -> None:
        """(Re)schedule an automatic leave after ``delay_seconds`` of silence."""

        self._inactivity.cancel(chat_id)

        async def _timer() -> None:
            try:
                await asyncio.sleep(delay_seconds)
                await on_timeout(chat_id)
            except asyncio.CancelledError:
                pass

        self._inactivity.tasks[chat_id] = asyncio.create_task(_timer())

    def cancel_inactivity_leave(self, chat_id: int) -> None:
        self._inactivity.cancel(chat_id)
        
