"""
plugins/translate.py
=====================
Implements ``/tr`` — translates text between English (including
romanized "Hinglish"), Indonesian, and Uzbek.

Usage:
    /tr uzb <text>   — translate into Uzbek
    /tr eng <text>   — translate into English
    /tr ind <text>   — translate into Indonesian

Source language is auto-detected, so any supported source language
works without specifying it. If used as a reply to another message
(with no text argument), that message's text is translated instead.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from utils.decorators import restrict_to_group
from utils.translator import TARGET_LANGUAGES, TranslationError, translate_text

logger = logging.getLogger(__name__)

_LANG_LABELS = {"uzb": "🇺🇿 Uzbek", "eng": "🇬🇧 English", "ind": "🇮🇩 Indonesian"}


@Client.on_message(filters.command("tr") & filters.group)
@restrict_to_group
async def translate_command(client: Client, message: Message) -> None:
    args = message.command[1:]

    if not args:
        await message.reply_text(
            "🌐 Usage: `/tr <uzb|eng|ind> <text>`\n"
            "e.g. `/tr uzb hello there` — or reply to a message with `/tr eng`",
            quote=True,
        )
        return

    target_key = args[0].lower()
    if target_key not in TARGET_LANGUAGES:
        await message.reply_text(
            "⚠️ Unknown target language. Use one of: `uzb`, `eng`, `ind`.",
            quote=True,
        )
        return

    text = " ".join(args[1:]).strip()
    if not text and message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text

    if not text:
        await message.reply_text(
            "🌐 Give me some text, or reply to a message with this command.",
            quote=True,
        )
        return

    status = await message.reply_text("🌐 Translating...", quote=True)

    try:
        translated = await translate_text(text, target_key)
    except TranslationError as exc:
        await status.edit_text(f"❌ Translation failed.\n`{exc}`")
        return
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error translating text")
        await status.edit_text("⚠️ Something went wrong. Please try again.")
        return

    label = _LANG_LABELS.get(target_key, target_key)
    await status.edit_text(f"{label}\n{translated}")
