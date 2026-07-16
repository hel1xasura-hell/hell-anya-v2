"""
utils/youtube.py
=================
YouTube search and stream-extraction, powered by ``yt-dlp``.

All ``yt-dlp`` calls are blocking, so they are dispatched to the default
executor via ``asyncio.to_thread`` to avoid stalling the event loop —
this matters a lot for a bot that must stay responsive to Telegram
updates while a search is in flight.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from config import CACHE_DIR, YOUTUBE_COOKIES_FILE

logger = logging.getLogger(__name__)

_YDL_SEARCH_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "extract_flat": False,
    "skip_download": True,
}

_YDL_URL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
}

if YOUTUBE_COOKIES_FILE is not None:
    _YDL_SEARCH_OPTS["cookiefile"] = str(YOUTUBE_COOKIES_FILE)
    _YDL_URL_OPTS["cookiefile"] = str(YOUTUBE_COOKIES_FILE)
    logger.info("YouTube cookies configured — using %s for extraction.", YOUTUBE_COOKIES_FILE)
else:
    logger.info("No YouTube cookies configured (YOUTUBE_COOKIES_B64 unset).")


class TrackNotFoundError(RuntimeError):
    """Raised when a search or URL lookup yields no usable result."""


class TrackTooLongError(RuntimeError):
    """Raised when a resolved track exceeds the configured download limit."""


@dataclass(slots=True)
class YouTubeResult:
    """Normalised metadata extracted from a YouTube video."""

    title: str
    artist: str
    duration_seconds: int
    stream_url: str
    thumbnail_url: str
    webpage_url: str
    http_headers: dict[str, str]


def _extract_sync(query_or_url: str, is_url: bool) -> dict:
    opts = _YDL_URL_OPTS if is_url else _YDL_SEARCH_OPTS
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query_or_url, download=False)
        if info is None:
            raise TrackNotFoundError(f"No results for: {query_or_url}")
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise TrackNotFoundError(f"No results for: {query_or_url}")
            info = entries[0]
        return info


async def search_or_resolve(query: str) -> YouTubeResult:
    """Resolve ``query`` — a search phrase or a direct YouTube URL — to a
    playable :class:`YouTubeResult`.
    """

    is_url = query.startswith("http://") or query.startswith("https://")
    try:
        info = await asyncio.to_thread(_extract_sync, query, is_url)
    except yt_dlp.utils.DownloadError as exc:
        raise TrackNotFoundError(str(exc)) from exc

    stream_url = info.get("url")
    http_headers = info.get("http_headers") or {}
    if not stream_url:
        # Some extractors nest formats; fall back to the best audio format.
        formats = info.get("formats") or []
        audio_formats = [f for f in formats if f.get("acodec") not in (None, "none")]
        if audio_formats:
            chosen = audio_formats[-1]
            stream_url = chosen["url"]
            http_headers = chosen.get("http_headers") or http_headers
    if not stream_url:
        raise TrackNotFoundError("Could not resolve a playable stream URL.")

    return YouTubeResult(
        title=info.get("title", "Unknown Title"),
        artist=info.get("uploader") or info.get("channel") or "Unknown Artist",
        duration_seconds=int(info.get("duration") or 0),
        stream_url=stream_url,
        thumbnail_url=info.get("thumbnail", ""),
        webpage_url=info.get("webpage_url", query),
        http_headers=dict(http_headers),
    )


@dataclass(slots=True)
class DownloadResult:
    """A YouTube track that has been downloaded and converted to a local file."""

    file_path: Path
    title: str
    artist: str
    duration_seconds: int
    thumbnail_url: str
    webpage_url: str


def _download_sync(query_or_url: str, job_id: str) -> dict:
    is_url = query_or_url.startswith("http://") or query_or_url.startswith("https://")
    outtmpl = str(CACHE_DIR / f"dl_{job_id}.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": outtmpl,
        "default_search": "ytsearch1",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    if YOUTUBE_COOKIES_FILE is not None:
        opts["cookiefile"] = str(YOUTUBE_COOKIES_FILE)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query_or_url, download=True)
        if info is None:
            raise TrackNotFoundError(f"No results for: {query_or_url}")
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise TrackNotFoundError(f"No results for: {query_or_url}")
            info = entries[0]
        return info


async def download_track(query: str, max_duration_seconds: int = 1200) -> DownloadResult:
    """Download ``query`` (a search phrase or YouTube URL) as an MP3 file.

    Raises :class:`TrackTooLongError` if the resolved video's duration
    exceeds ``max_duration_seconds`` (default 20 minutes) — this guards
    against accidentally downloading multi-hour mixes/streams. Raises
    :class:`TrackNotFoundError` if nothing playable was found.
    """

    job_id = uuid.uuid4().hex[:10]

    try:
        info = await asyncio.to_thread(_download_sync, query, job_id)
    except yt_dlp.utils.DownloadError as exc:
        raise TrackNotFoundError(str(exc)) from exc

    duration = int(info.get("duration") or 0)

    file_path = CACHE_DIR / f"dl_{job_id}.mp3"
    if not file_path.exists():
        # Fall back to scanning for whatever the postprocessor actually named it.
        matches = list(CACHE_DIR.glob(f"dl_{job_id}.*"))
        if not matches:
            raise TrackNotFoundError("Download completed but the output file could not be located.")
        file_path = matches[0]

    if duration and duration > max_duration_seconds:
        file_path.unlink(missing_ok=True)
        minutes = max_duration_seconds // 60
        raise TrackTooLongError(f"That track is too long to download (limit: {minutes} minutes).")

    return DownloadResult(
        file_path=file_path,
        title=info.get("title", "Unknown Title"),
        artist=info.get("uploader") or info.get("channel") or "Unknown Artist",
        duration_seconds=duration,
        thumbnail_url=info.get("thumbnail", ""),
        webpage_url=info.get("webpage_url", query),
    )
    
