"""
utils/logger.py
================
Centralised, colourised logging for ᴀɴʏᴀ.

A single call to :func:`setup_logging` configures the root logger with a
Rich console handler (pretty, colourised, human-friendly) and a rotating
file handler (plain text, machine-parseable) writing into ``logs/``.

Every module in the project should obtain its logger via
``logging.getLogger(__name__)`` after this has been called once at startup.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from rich.logging import RichHandler

from config import LOG_DIR

_LOG_FILE = LOG_DIR / "anya.log"
_FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger exactly once.

    Safe to call multiple times; subsequent calls are no-ops so importing
    this module from several places never duplicates log handlers.
    """

    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(level)

    console_handler = RichHandler(
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
        log_time_format="[%X]",
    )
    console_handler.setLevel(level)

    file_handler = RotatingFileHandler(
        filename=_LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Silence noisy third-party loggers while keeping our own verbose.
    for noisy in ("pyrogram", "pytgcalls", "aiohttp", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Convenience accessor identical to ``logging.getLogger`` for clarity."""

    return logging.getLogger(name)
