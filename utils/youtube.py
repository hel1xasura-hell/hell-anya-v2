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
from dataclasses import dataclass

import yt_dlp

from config import YOUTUBE_COOKIES_FILE

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
    
