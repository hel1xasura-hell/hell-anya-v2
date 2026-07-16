"""
database/base.py
=================
Abstract persistence contract.

Everything above this layer (plugins, core) talks to ``Database`` only —
never to a concrete storage engine. Swapping the JSON-file backend
(:mod:`database.json_store`) for, say, MongoDB or PostgreSQL later means
writing one new class that satisfies this interface; nothing else in the
project changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Database(ABC):
    """Storage contract used throughout ᴀɴʏᴀ."""

    @abstractmethod
    async def connect(self) -> None:
        """Initialise the underlying storage engine (open files, pools...)."""

    @abstractmethod
    async def close(self) -> None:
        """Release any resources held by the storage engine."""

    # -- Generic settings -------------------------------------------------

    @abstractmethod
    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Return a global bot setting, or ``default`` if unset."""

    @abstractmethod
    async def set_setting(self, key: str, value: Any) -> None:
        """Persist a global bot setting."""

    # -- Chat-scoped settings ----------------------------------------------

    @abstractmethod
    async def get_chat_setting(self, chat_id: int, key: str, default: Any = None) -> Any:
        """Return a per-chat setting (e.g. volume, loop mode)."""

    @abstractmethod
    async def set_chat_setting(self, chat_id: int, key: str, value: Any) -> None:
        """Persist a per-chat setting."""

    # -- Favourites ---------------------------------------------------------

    @abstractmethod
    async def add_favorite(self, user_id: int, title: str, url: str) -> None:
        """Add a track to a user's favourites list."""

    @abstractmethod
    async def get_favorites(self, user_id: int) -> list[dict[str, str]]:
        """Return a user's saved favourite tracks."""

    @abstractmethod
    async def remove_favorite(self, user_id: int, url: str) -> bool:
        """Remove a favourite by URL. Returns ``True`` if something was removed."""

    # -- Statistics -----------------------------------------------------------

    @abstractmethod
    async def record_play(self, chat_id: int, user_id: int, title: str) -> None:
        """Record a play event for statistics."""

    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
        """Return aggregate usage statistics."""

    # -- Audit log (dashboard) ------------------------------------------------

    @abstractmethod
    async def log_command(
        self,
        chat_id: int | None,
        user_id: int | None,
        username: str,
        full_name: str,
        command: str,
        source: str = "telegram",
    ) -> None:
        """Append one entry to the command audit trail."""

    @abstractmethod
    async def get_audit_log(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Return the most recent audit log entries, newest first."""

    # -- Known users (dashboard) ------------------------------------------------

    @abstractmethod
    async def upsert_user(self, user_id: int, username: str, full_name: str) -> None:
        """Record/refresh a user's identity and last-seen timestamp."""

    @abstractmethod
    async def get_users(self) -> list[dict[str, Any]]:
        """Return every known user with basic activity metadata."""
  
