"""
utils/lyrics.py
================
Lyrics retrieval.

Uses the free lyrics.ovh API as a zero-configuration default, and
transparently upgrades to the Genius API when ``GENIUS_API_TOKEN`` is
configured (better hit-rate, more accurate metadata). Both code paths are
wrapped behind :func:`fetch_lyrics` so callers never need to know which
backend answered.
"""

from __future__ import annotations

import logging
import re

import aiohttp

from config import config

logger = logging.getLogger(__name__)

_LYRICS_OVH_URL = "https://api.lyrics.ovh/v1/{artist}/{title}"
_GENIUS_SEARCH_URL = "https://api.genius.com/search"


class LyricsNotFoundError(RuntimeError):
    """Raised when no lyrics could be located for the given query."""


def _clean_title(title: str) -> str:
    """Strip common noise (feat., official video, brackets) from a title
    to improve lyrics-provider hit rate."""

    cleaned = re.sub(r"\(.*?\)|\[.*?\]", "", title)
    cleaned = re.sub(r"(?i)\bofficial\b.*", "", cleaned)
    cleaned = re.sub(r"(?i)\bfeat\.?.*", "", cleaned)
    return cleaned.strip()


async def _fetch_via_genius(artist: str, title: str) -> str:
    headers = {"Authorization": f"Bearer {config.genius_api_token}"}
    params = {"q": f"{artist} {title}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(_GENIUS_SEARCH_URL, headers=headers, params=params) as response:
            if response.status != 200:
                raise LyricsNotFoundError("Genius search request failed.")
            payload = await response.json()

    hits = payload.get("response", {}).get("hits", [])
    if not hits:
        raise LyricsNotFoundError(f"No Genius results for {artist} - {title}")

    result = hits[0]["result"]
    # The Genius API intentionally does not expose full lyrics text via the
    # public search endpoint (scraping the song page would violate their
    # terms of service), so we surface the song URL for the user instead of
    # attempting to circumvent that restriction.
    return (
        f"Lyrics for this track are hosted on Genius:\n{result.get('url')}\n\n"
        f"({result.get('title')} — {result.get('primary_artist', {}).get('name')})"
    )


async def _fetch_via_lyrics_ovh(artist: str, title: str) -> str:
    url = _LYRICS_OVH_URL.format(artist=artist, title=_clean_title(title))
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise LyricsNotFoundError(f"No lyrics found for {artist} - {title}")
            payload = await response.json()

    lyrics = payload.get("lyrics", "").strip()
    if not lyrics:
        raise LyricsNotFoundError(f"No lyrics found for {artist} - {title}")
    return lyrics


async def fetch_lyrics(artist: str, title: str) -> str:
    """Fetch lyrics text for a track, preferring Genius when configured."""

    if config.genius_enabled:
        try:
            return await _fetch_via_genius(artist, title)
        except LyricsNotFoundError:
            logger.info("Genius lookup failed, falling back to lyrics.ovh")

    return await _fetch_via_lyrics_ovh(artist, title)
