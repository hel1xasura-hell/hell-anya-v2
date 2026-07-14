"""
database/json_store.py
=======================
Default :class:`~database.base.Database` implementation backed by a single
JSON file on disk, guarded by an ``asyncio.Lock`` to keep concurrent
read/modify/write cycles safe.

This backend requires zero external services, which keeps the bot
deployable on Railway's free tier with no database add-on. It is fully
adequate for a single-group bot's settings, favourites and statistics.
For multi-tenant or high-volume use, swap in a new :class:`Database`
implementation (e.g. PostgreSQL via ``asyncpg``) without touching any
plugin code.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from database.base import Database

logger = logging.getLogger(__name__)

_DEFAULT_STATE: dict[str, Any] = {
    "settings": {},
    "chat_settings": {},
    "favorites": {},
    "stats": {
        "total_plays": 0,
        "tracks": {},
        "users": {},
    },
}


class JSONDatabase(Database):
    """A minimal, dependency-free JSON document store."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._state: dict[str, Any] = {}

    async def connect(self) -> None:
        async with self._lock:
            if self._path.exists():
                try:
                    self._state = json.loads(self._path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    logger.warning("Database file was corrupt — reinitialising.")
                    self._state = json.loads(json.dumps(_DEFAULT_STATE))
            else:
                self._state = json.loads(json.dumps(_DEFAULT_STATE))
                self._flush_unlocked()
        logger.info("JSON database ready at %s", self._path)

    async def close(self) -> None:
        async with self._lock:
            self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        """Write current state to disk. Caller must hold ``self._lock``."""

        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self._state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self._path)

    # -- Generic settings -----------------------------------------------------

    async def get_setting(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._state["settings"].get(key, default)

    async def set_setting(self, key: str, value: Any) -> None:
        async with self._lock:
            self._state["settings"][key] = value
            self._flush_unlocked()

    # -- Chat-scoped settings ---------------------------------------------------

    async def get_chat_setting(self, chat_id: int, key: str, default: Any = None) -> Any:
        async with self._lock:
            chat_bucket = self._state["chat_settings"].get(str(chat_id), {})
            return chat_bucket.get(key, default)

    async def set_chat_setting(self, chat_id: int, key: str, value: Any) -> None:
        async with self._lock:
            bucket = self._state["chat_settings"].setdefault(str(chat_id), {})
            bucket[key] = value
            self._flush_unlocked()

    # -- Favourites -------------------------------------------------------------

    async def add_favorite(self, user_id: int, title: str, url: str) -> None:
        async with self._lock:
            bucket = self._state["favorites"].setdefault(str(user_id), [])
            if not any(item["url"] == url for item in bucket):
                bucket.append({"title": title, "url": url})
            self._flush_unlocked()

    async def get_favorites(self, user_id: int) -> list[dict[str, str]]:
        async with self._lock:
            return list(self._state["favorites"].get(str(user_id), []))

    async def remove_favorite(self, user_id: int, url: str) -> bool:
        async with self._lock:
            bucket = self._state["favorites"].get(str(user_id), [])
            new_bucket = [item for item in bucket if item["url"] != url]
            removed = len(new_bucket) != len(bucket)
            if removed:
                self._state["favorites"][str(user_id)] = new_bucket
                self._flush_unlocked()
            return removed

    # -- Statistics ---------------------------------------------------------------

    async def record_play(self, chat_id: int, user_id: int, title: str) -> None:
        async with self._lock:
            stats = self._state["stats"]
            stats["total_plays"] += 1
            stats["tracks"][title] = stats["tracks"].get(title, 0) + 1
            stats["users"][str(user_id)] = stats["users"].get(str(user_id), 0) + 1
            self._flush_unlocked()

    async def get_stats(self) -> dict[str, Any]:
        async with self._lock:
            stats = self._state["stats"]
            top_tracks = sorted(stats["tracks"].items(), key=lambda kv: kv[1], reverse=True)[:5]
            top_users = sorted(stats["users"].items(), key=lambda kv: kv[1], reverse=True)[:5]
            return {
                "total_plays": stats["total_plays"],
                "top_tracks": top_tracks,
                "top_users": top_users,
            }
