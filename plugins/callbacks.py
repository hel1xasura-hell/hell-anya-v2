"""
plugins/callbacks.py
=====================
Handles taps on the inline keyboard attached to now-playing / queue
messages. All callback data is namespaced (``ctrl:*``, ``vol:*``) and
routed here from a single entry point.

Per the project spec, only administrators may operate playback controls;
this is enforced with :func:`utils.decorators.admin_only`, which also
transparently allows the bot owner regardless of rank.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from core.models import LoopMode
from utils.decorators import admin_only, restrict_to_group
from utils.formatters import format_duration, truncate
from utils.keyboards import playback_controls, volume_controls
from utils.lyrics import LyricsNotFoundError, fetch_lyrics

_LOOP_CYCLE = {LoopMode.OFF: LoopMode.TRACK, LoopMode.TRACK: LoopMode.QUEUE, LoopMode.QUEUE: LoopMode.OFF}
_LOOP_LABEL = {LoopMode.OFF: "Off", LoopMode.TRACK: "Current Track", LoopMode.QUEUE: "Whole Queue"}


@Client.on_callback_query(filters.regex(r"^ctrl:"))
@restrict_to_group
@admin_only
async def playback_callback(client: Client, callback: CallbackQuery) -> None:
    action = callback.data.split(":", 1)[1]
    player = client.require_player()
    chat_id = callback.message.chat.id
    state = player.current_state(chat_id)

    if action == "close":
        await callback.message.delete()
        return

    if state.current is None and action not in ("queue",):
        await callback.answer("Nothing is currently playing.", show_alert=True)
        return

    if action == "pause":
        await player.pause(chat_id)
        await callback.answer("Paused")
    elif action == "resume":
        await player.resume(chat_id)
        await callback.answer("Resumed")
    elif action == "skip":
        next_track = await player.skip(chat_id)
        await callback.answer(f"Skipped to {next_track.title}" if next_track else "Queue finished")
    elif action == "stop":
        await player.stop(chat_id)
        await callback.answer("Stopped")
        await callback.message.edit_caption("⏹ Playback stopped.")
        return
    elif action == "queue":
        pending = player.queues.snapshot(chat_id)
        if not pending:
            await callback.answer("The queue is empty.", show_alert=True)
        else:
            preview = "\n".join(f"{i}. {truncate(t.title, 35)}" for i, t in enumerate(pending[:10], 1))
            await callback.answer(preview or "Empty", show_alert=True)
        return
    elif action == "lyrics":
        await callback.answer("Fetching lyrics...")
        current = player.current_state(chat_id).current
        if current is None:
            return
        try:
            lyrics = await fetch_lyrics(current.artist, current.title)
            await callback.message.reply_text(f"📝 **Lyrics — {current.title}**\n\n{truncate(lyrics, 3500)}")
        except LyricsNotFoundError:
            await callback.message.reply_text("❌ Lyrics not found for this track.")
        return
    elif action == "loop":
        new_mode = _LOOP_CYCLE[state.loop_mode]
        await player.set_loop(chat_id, new_mode)
        await callback.answer(f"Loop: {_LOOP_LABEL[new_mode]}")
    elif action == "shuffle":
        await player.queues.shuffle(chat_id)
        await callback.answer("Queue shuffled")
    elif action == "volume":
        await callback.message.edit_reply_markup(volume_controls(state.volume))
        await callback.answer()
        return
    elif action == "back":
        await callback.message.edit_reply_markup(playback_controls(state.is_paused, state.loop_mode))
        await callback.answer()
        return
    else:
        await callback.answer()
        return

    updated_state = player.current_state(chat_id)
    try:
        await callback.message.edit_reply_markup(playback_controls(updated_state.is_paused, updated_state.loop_mode))
    except Exception:  # noqa: BLE001 - message content may not have changed, which Pyrogram rejects
        pass


@Client.on_callback_query(filters.regex(r"^vol:"))
@restrict_to_group
@admin_only
async def volume_callback(client: Client, callback: CallbackQuery) -> None:
    action = callback.data.split(":", 1)[1]
    player = client.require_player()
    chat_id = callback.message.chat.id
    state = player.current_state(chat_id)

    if action == "noop":
        await callback.answer()
        return

    delta = 10 if action == "up" else -10
    new_volume = max(0, min(200, state.volume + delta))
    await player.set_volume(chat_id, new_volume)
    try:
        await callback.message.edit_reply_markup(volume_controls(new_volume))
    except Exception:  # noqa: BLE001 - happens at the 0%/200% caps where the keyboard doesn't change
        pass
    await callback.answer(f"Volume: {new_volume}%")
