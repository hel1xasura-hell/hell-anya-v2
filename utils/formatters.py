"""
utils/formatters.py
====================
Small, dependency-free presentation helpers shared by plugins and the
thumbnail engine: duration strings, textual progress bars, and safe
truncation for Telegram captions.
"""

from __future__ import annotations


def format_duration(seconds: int) -> str:
    """Format a duration in seconds as ``H:MM:SS`` or ``M:SS``."""

    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def progress_bar(elapsed: int, total: int, length: int = 12) -> str:
    """Render a Unicode progress bar, e.g. ``▰▰▰▰▱▱▱▱▱▱▱▱``."""

    if total <= 0:
        filled = 0
    else:
        filled = min(length, round((elapsed / total) * length))
    return "▰" * filled + "▱" * (length - filled)


def truncate(text: str, max_length: int = 60) -> str:
    """Truncate text with an ellipsis, respecting word boundaries loosely."""

    text = text.strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def human_readable_count(count: int) -> str:
    """Format large integers as ``1.2K`` / ``3.4M`` style strings."""

    if count < 1_000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1_000:.1f}K"
    return f"{count / 1_000_000:.1f}M"
      
