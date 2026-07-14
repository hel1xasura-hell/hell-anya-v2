"""
config.py
=========
Centralised, typed configuration for ᴀɴʏᴀ.

Every runtime setting is sourced from environment variables (see
``.env.example``). This module validates presence/format at import time so
the bot fails fast with a clear error instead of crashing deep inside a
plugin during a live voice chat.

No secret is ever hardcoded here — this file only *reads* the environment.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
import os

# Load .env for local development. On Railway, real environment variables
# are injected directly and this call is a harmless no-op.
load_dotenv(override=False)

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
CACHE_DIR: Final[Path] = BASE_DIR / "cache"
LOG_DIR: Final[Path] = BASE_DIR / "logs"
ASSETS_DIR: Final[Path] = BASE_DIR / "assets"
FONTS_DIR: Final[Path] = ASSETS_DIR / "fonts"
IMAGES_DIR: Final[Path] = ASSETS_DIR / "images"

for _directory in (CACHE_DIR, LOG_DIR, ASSETS_DIR, FONTS_DIR, IMAGES_DIR):
    _directory.mkdir(parents=True, exist_ok=True)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


def _require_str(name: str) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise ConfigError(f"Missing required environment variable: {name}")
    return value.strip()


def _require_int(name: str) -> int:
    raw = _require_str(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer, got: {raw!r}") from exc


def _optional_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value else default


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable application configuration, populated once at startup."""

    bot_token: str
    api_id: int
    api_hash: str
    session_string: str
    owner_id: int
    allowed_group_id: int
    log_channel: int | None

    # Optional third-party integrations (feature-gated, never required)
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    genius_api_token: str = ""
    youtube_cookies_b64: str = ""

    # Behavioural tuning
    inactivity_timeout_seconds: int = 300
    default_volume: int = 100
    max_queue_size: int = 50
    bot_name: str = "ᴀɴʏᴀ"

    @property
    def spotify_enabled(self) -> bool:
        return bool(self.spotify_client_id and self.spotify_client_secret)

    @property
    def genius_enabled(self) -> bool:
        return bool(self.genius_api_token)


def load_config() -> Config:
    """Read and validate all environment variables into a :class:`Config`.

    Exits the process with a readable error if anything mandatory is
    missing — this is intentional: a partially configured bot should never
    silently start and fail later mid-command.
    """

    try:
        return Config(
            bot_token=_require_str("BOT_TOKEN"),
            api_id=_require_int("API_ID"),
            api_hash=_require_str("API_HASH"),
            session_string=_optional_str("SESSION_STRING"),
            owner_id=_require_int("OWNER_ID"),
            allowed_group_id=_require_int("ALLOWED_GROUP_ID"),
            log_channel=_optional_int("LOG_CHANNEL"),
            spotify_client_id=_optional_str("SPOTIFY_CLIENT_ID"),
            spotify_client_secret=_optional_str("SPOTIFY_CLIENT_SECRET"),
            genius_api_token=_optional_str("GENIUS_API_TOKEN"),
            youtube_cookies_b64=_optional_str("YOUTUBE_COOKIES_B64"),
            inactivity_timeout_seconds=_optional_int("INACTIVITY_TIMEOUT_SECONDS") or 300,
            default_volume=_optional_int("DEFAULT_VOLUME") or 100,
            max_queue_size=_optional_int("MAX_QUEUE_SIZE") or 50,
        )
    except ConfigError as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        raise


config: Final[Config] = load_config()


def _materialise_cookies_file() -> Path | None:
    """Decode ``YOUTUBE_COOKIES_B64`` (if set) to a Netscape-format cookies
    file on disk, once, at startup. Returns the file path, or ``None`` if no
    cookies were configured."""

    if not config.youtube_cookies_b64:
        return None

    import base64

    cookies_path = CACHE_DIR / "youtube_cookies.txt"
    try:
        raw = base64.b64decode(config.youtube_cookies_b64)
        cookies_path.write_bytes(raw)
        cookies_path.chmod(0o600)
        return cookies_path
    except Exception as exc:  # noqa: BLE001
        print(f"[CONFIG WARNING] Failed to decode YOUTUBE_COOKIES_B64: {exc}", file=sys.stderr)
        return None


YOUTUBE_COOKIES_FILE: Final[Path | None] = _materialise_cookies_file()
