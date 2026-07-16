"""
plugins/media_download.py
==========================
Implements ``/save`` — downloads a video from Instagram, TikTok,
Twitter/X, Facebook, Reddit, or any other site yt-dlp supports, and
sends it directly into the chat.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from utils.decorators import restrict_to_group
from utils.formatters import format_duration
from utils.media_downloader import (
    MediaNotFoundError,
    MediaResult,
    MediaTooLongError,
    download_media,
)

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_SECONDS = 20 * 60


@Client.on_message(filters.command(["save", "video"]) & filters.group)
@restrict_to_group
async def save_command(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text(
            "🔗 Usage: /save <Instagram/TikTok/Twitter/etc. link>",
            quote=True,
        )
        return

    url = message.text.split(None, 1)[1].strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.reply_text("⚠️ Please send a valid link.", quote=True)
        return

    status = await message.reply_text("⬇️ Downloading...", quote=True)

    result: MediaResult | None = None
    try:
        result = await download_media(url, max_duration_seconds=MAX_DOWNLOAD_SECONDS)
    except MediaTooLongError as exc:
        await status.edit_text(f"⚠️ {exc}")
        return
    except MediaNotFoundError as exc:
        await status.edit_text(f"❌ Couldn't download that link.\n`{exc}`")
        return
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error downloading url %r", url)
        await status.edit_text("⚠️ Something went wrong. Please try again.")
        return

    try:
        await status.edit_text("📤 Uploading...")
        caption = f"🎬 **{result.title}**\n👤 {result.uploader}"
        if result.duration_seconds:
            caption += f"\n⏱ {format_duration(result.duration_seconds)}"

        if result.is_video:
            await message.reply_video(
                video=str(result.file_path),
                caption=caption,
                duration=result.duration_seconds,
                quote=True,
            )
        else:
            await message.reply_document(
                document=str(result.file_path),
                caption=caption,
                quote=True,
            )
        await status.delete()
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error uploading downloaded media %r", url)
        await status.edit_text("⚠️ Downloaded, but failed to upload the file. Please try again.")
    finally:
        try:
            result.file_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to clean up downloaded file %s", result.file_path)
