"""
utils/translator.py
====================
Text translation for ``/tr``, powered by ``deep-translator``'s Google
Translate backend. No API key required. Source language is
auto-detected, so English, romanized "Hinglish", Indonesian, and Uzbek
input are all handled transparently by a single call.
"""

from __future__ import annotations

import asyncio
import logging

from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)


class TranslationError(RuntimeError):
    """Raised when a translation request fails."""


# Command keyword -> ISO 639-1 code used by Google Translate.
TARGET_LANGUAGES: dict[str, str] = {
    "uzb": "uz",
    "eng": "en",
    "ind": "id",
}


def _translate_sync(text: str, target_code: str) -> str:
    return GoogleTranslator(source="auto", target=target_code).translate(text)


async def translate_text(text: str, target_key: str) -> str:
    """Translate ``text`` into the language identified by ``target_key``.

    ``target_key`` must be one of :data:`TARGET_LANGUAGES`'s keys
    (``"uzb"``, ``"eng"``, ``"ind"``). Raises :class:`TranslationError`
    on any failure or empty input/output.
    """

    target_code = TARGET_LANGUAGES.get(target_key.lower())
    if target_code is None:
        raise TranslationError(f"Unsupported target language: {target_key}")

    text = text.strip()
    if not text:
        raise TranslationError("No text to translate.")

    try:
        result = await asyncio.to_thread(_translate_sync, text, target_code)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Translation failed for target=%s", target_code)
        raise TranslationError(str(exc)) from exc

    if not result:
        raise TranslationError("Translation returned an empty result.")

    return result
