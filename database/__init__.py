"""
database package
=================
Exposes :func:`get_database`, a factory returning the singleton
:class:`~database.base.Database` instance used across the application.

Swapping storage engines happens in exactly one place: this factory.
"""

from __future__ import annotations

from config import CACHE_DIR
from database.base import Database
from database.json_store import JSONDatabase

_instance: Database | None = None


def get_database() -> Database:
    """Return the process-wide database singleton, creating it on first use."""

    global _instance
    if _instance is None:
        _instance = JSONDatabase(CACHE_DIR / "anya_store.json")
    return _instance


__all__ = ["Database", "get_database"]
