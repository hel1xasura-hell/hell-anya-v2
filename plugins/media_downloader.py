"""
utils/media_downloader.py
==========================
Generic media downloader powered by ``yt-dlp``, covering any site it has
an extractor for — Instagram, TikTok, Twitter/X, Facebook, Reddit, and
more — in addition to YouTube. This mirrors the download path in
``utils/youtube.py`` but keeps the original video track (rather than
extracting audio-only), since links from these platforms are almost
always short-form video.
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


class MediaNotFoundError(RuntimeError):
    """Raised when a URL can't be resolved or downloaded."""


class MediaTooLongError(RuntimeError):
    """Raised when resolved media exceeds the configured duration limit."""


@dataclass(slots=True)
class MediaResult:
    """A downloaded piece of media, ready to be uploaded to Telegram."""

    file_path: Path
    title: str
    uploader: str
    duration_seconds: int
    webpage_url: str
    is_video: bool


def _download_sync(url: str, job_id: str) -> dict:
    outtmpl = str(CACHE_DIR / f"media_{job_id}.%(ext)s")
    opts = {
        "format": "bestvideo*+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": outtmpl,
    }
    # yt-dlp only sends cookies to the domain that actually owns them, so
    # reusing the same cookies file is harmless for non-YouTube sites. It
    # simply won't help unless you later add cookies for those sites too.
    if YOUTUBE_COOKIES_FILE is not None:
        opts["cookiefile"] = str(YOUTUBE_COOKIES_FILE)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise MediaNotFoundError(f"Could not resolve: {url}")
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise MediaNotFoundError(f"Could not resolve: {url}")
            info = entries[0]
        return info


async def download_media(url: str, max_duration_seconds: int = 1200) -> MediaResult:
    """Download whatever ``url`` points to (Instagram/TikTok/Twitter/etc.).

    Raises :class:`MediaTooLongError` if the resolved duration exceeds
    ``max_duration_seconds``, and :class:`MediaNotFoundError` if yt-dlp
    can't resolve or download anything from the link.
    """

    job_id = uuid.uuid4().hex[:10]

    try:
        info = await asyncio.to_thread(_download_sync, url, job_id)
    except yt_dlp.utils.DownloadError as exc:
        raise MediaNotFoundError(str(exc)) from exc

    duration = int(info.get("duration") or 0)

    matches = list(CACHE_DIR.glob(f"media_{job_id}.*"))
    if not matches:
        raise MediaNotFoundError("Download completed but the output file could not be located.")
    file_path = matches[0]

    if duration and duration > max_duration_seconds:
        file_path.unlink(missing_ok=True)
        minutes = max_duration_seconds // 60
        raise MediaTooLongError(f"That video is too long to download (limit: {minutes} minutes).")

    return MediaResult(
        file_path=file_path,
        title=info.get("title") or "Untitled",
        uploader=info.get("uploader") or info.get("channel") or "Unknown",
        duration_seconds=duration,
        webpage_url=info.get("webpage_url", url),
        is_video=file_path.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov"),
    )
