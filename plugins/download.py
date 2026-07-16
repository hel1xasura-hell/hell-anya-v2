"""
plugins/download.py
====================
Implements ``/download`` — resolves a search phrase or YouTube link and
sends the actual audio file into the chat, as opposed to ``/play`` which
streams it into the group voice chat without saving anything.

Reuses the same ``yt-dlp`` + cookies setup as ``utils/youtube.py``'s
streaming path, so no extra configuration is required beyond what's
already set for ``/play``.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from utils.decorators import restrict_to_group
from utils.formatters import format_duration
from utils.youtube import (
    DownloadResult,
    TrackNotFoundError,
    TrackTooLongError,
    download_track,
)

logger = logging.getLogger(__name__)

# Guard against accidentally downloading multi-hour mixes/live streams.
MAX_DOWNLOAD_SECONDS = 20 * 60


@Client.on_message(filters.command(["download", "song"]) & filters.group)
@restrict_to_group
async def download_command(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text(
            "🎵 Usage: /download <song name or YouTube link>",
            quote=True,
        )
        return

    query = message.text.split(None, 1)[1].strip()
    status = await message.reply_text("⬇️ Downloading from YouTube...", quote=True)

    result: DownloadResult | None = None
    try:
        result = await download_track(query, max_duration_seconds=MAX_DOWNLOAD_SECONDS)
    except TrackTooLongError as exc:
        await status.edit_text(f"⚠️ {exc}")
        return
    except TrackNotFoundError as exc:
        await status.edit_text(f"❌ Couldn't find that track.\n`{exc}`")
        return
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error downloading query %r", query)
        await status.edit_text("⚠️ Something went wrong while downloading. Please try again.")
        return

    try:
        await status.edit_text("📤 Uploading...")
        await message.reply_audio(
            audio=str(result.file_path),
            title=result.title,
            performer=result.artist,
            duration=result.duration_seconds,
            caption=(
                f"🎶 **{result.title}**\n"
                f"👤 {result.artist}\n"
                f"⏱ {format_duration(result.duration_seconds)}"
            ),
            quote=True,
        )
        await status.delete()
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error uploading downloaded track %r", query)
        await status.edit_text("⚠️ Downloaded, but failed to upload the file. Please try again.")
    finally:
        try:
            result.file_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to clean up downloaded file %s", result.file_path)
