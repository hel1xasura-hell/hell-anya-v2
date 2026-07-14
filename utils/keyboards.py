"""
utils/keyboards.py
===================
Builders for the inline keyboards attached to playback-related messages.
Callback data is namespaced with a ``ctrl:`` prefix and parsed centrally
in ``plugins/callbacks.py``.
"""

from __future__ import annotations

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.models import LoopMode


def playback_controls(is_paused: bool, loop_mode: LoopMode) -> InlineKeyboardMarkup:
    """The primary control row shown under every now-playing card."""

    pause_button = (
        InlineKeyboardButton("▶️ Resume", callback_data="ctrl:resume")
        if is_paused
        else InlineKeyboardButton("⏸ Pause", callback_data="ctrl:pause")
    )

    loop_label = {
        LoopMode.OFF: "🔁 Loop: Off",
        LoopMode.TRACK: "🔂 Loop: Track",
        LoopMode.QUEUE: "🔁 Loop: Queue",
    }[loop_mode]

    return InlineKeyboardMarkup(
        [
            [pause_button, InlineKeyboardButton("⏭ Skip", callback_data="ctrl:skip"), InlineKeyboardButton("⏹ Stop", callback_data="ctrl:stop")],
            [InlineKeyboardButton("📜 Queue", callback_data="ctrl:queue"), InlineKeyboardButton("📝 Lyrics", callback_data="ctrl:lyrics")],
            [InlineKeyboardButton(loop_label, callback_data="ctrl:loop"), InlineKeyboardButton("🔀 Shuffle", callback_data="ctrl:shuffle")],
            [InlineKeyboardButton("🔊 Volume", callback_data="ctrl:volume"), InlineKeyboardButton("✖️ Close", callback_data="ctrl:close")],
        ]
    )


def volume_controls(current_volume: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➖", callback_data="vol:down"),
                InlineKeyboardButton(f"{current_volume}%", callback_data="vol:noop"),
                InlineKeyboardButton("➕", callback_data="vol:up"),
            ],
            [InlineKeyboardButton("« Back", callback_data="ctrl:back")],
        ]
    )


def close_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Close", callback_data="ctrl:close")]])
