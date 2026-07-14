"""
utils/spotify.py
=================
Spotify integration, implemented as an abstract *metadata provider* rather
than a playback source — Spotify's API does not grant access to raw audio,
so the pattern here is:

    1. Parse the Spotify track URL and fetch its metadata (title, artist,
       duration) via the Spotify Web API (client-credentials flow).
    2. Hand that metadata to :mod:`utils.youtube` to locate an equivalent
       playable source.
    3. Queue the YouTube-resolved track, tagged with ``SourceType.SPOTIFY``
       so the UI can still show "via Spotify" provenance if desired.

This keeps the "provider" concept generic: adding another metadata-only
service later (Apple Music, Deezer...) means adding one function here and
one branch in ``plugins/play.py`` — no changes to the player or queue.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass

import aiohttp

from config import config

logger = logging.getLogger(__name__)

_TRACK_URL_RE = re.compile(r"open\.spotify\.com/track/([a-zA-Z0-9]+)")
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_TRACK_API = "https://api.spotify.com/v1/tracks/{track_id}"


class SpotifyNotConfiguredError(RuntimeError):
    """Raised when a Spotify link is used without API credentials configured."""


class SpotifyLookupError(RuntimeError):
    """Raised when the Spotify API call fails or the link is invalid."""


@dataclass(slots=True)
class SpotifyTrackMetadata:
    title: str
    artist: str
    duration_seconds: int
    album_art_url: str
    spotify_url: str


class SpotifyProvider:
    """Client-credentials-flow wrapper around the Spotify Web API."""

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    @staticmethod
    def is_spotify_url(url: str) -> bool:
        return bool(_TRACK_URL_RE.search(url))

    async def _get_token(self, session: aiohttp.ClientSession) -> str:
        if self._access_token and time.time() < self._expires_at - 30:
            return self._access_token

        if not config.spotify_enabled:
            raise SpotifyNotConfiguredError(
                "Spotify support requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET."
            )

        credentials = f"{config.spotify_client_id}:{config.spotify_client_secret}".encode()
        encoded = base64.b64encode(credentials).decode()

        async with session.post(
            _TOKEN_URL,
            headers={"Authorization": f"Basic {encoded}"},
            data={"grant_type": "client_credentials"},
        ) as response:
            if response.status != 200:
                raise SpotifyLookupError(f"Spotify auth failed with status {response.status}")
            payload = await response.json()

        self._access_token = payload["access_token"]
        self._expires_at = time.time() + payload.get("expires_in", 3600)
        return self._access_token

    async def fetch_track_metadata(self, spotify_url: str) -> SpotifyTrackMetadata:
        """Resolve a Spotify track URL to its metadata."""

        match = _TRACK_URL_RE.search(spotify_url)
        if not match:
            raise SpotifyLookupError("Not a recognised Spotify track URL.")
        track_id = match.group(1)

        async with aiohttp.ClientSession() as session:
            token = await self._get_token(session)
            async with session.get(
                _TRACK_API.format(track_id=track_id),
                headers={"Authorization": f"Bearer {token}"},
            ) as response:
                if response.status != 200:
                    raise SpotifyLookupError(f"Spotify track lookup failed with status {response.status}")
                data = await response.json()

        artists = ", ".join(a["name"] for a in data.get("artists", []))
        images = data.get("album", {}).get("images", [])
        album_art = images[0]["url"] if images else ""

        return SpotifyTrackMetadata(
            title=data.get("name", "Unknown Title"),
            artist=artists or "Unknown Artist",
            duration_seconds=int(data.get("duration_ms", 0)) // 1000,
            album_art_url=album_art,
            spotify_url=spotify_url,
        )


spotify_provider = SpotifyProvider()
