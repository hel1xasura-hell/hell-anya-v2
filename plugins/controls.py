"""
plugins/controls.py
====================
All direct playback-management commands that are not ``/play`` itself:
pause, resume, skip, stop, end, queue, clearqueue, remove, shuffle, loop,
volume, replay, seek, nowplaying and ping.
"""

from __future__ import annotations

import time

from pyrogram import Client, filters
from pyrogram.types import Message

from core.models import LoopMode
from utils.decorators import admin_only, restrict_to_group
from utils.formatters import format_duration, progress_bar, truncate
from utils.keyboards import playback_controls
from utils.thumbnail import generate_now_playing_card

_LOOP_CYCLE = {LoopMode.OFF: LoopMode.TRACK, LoopMode.TRACK: LoopMode.QUEUE, LoopMode.QUEUE: LoopMode.OFF}


def _no_track_reply() -> str:
    return "ℹ️ Nothing is currently playing."


@Client.on_message(filters.command("pause") & filters.group)
@restrict_to_group
@admin_only
async def pause_command(client: Client, message: Message) -> None:
    player = client.require_player()
    state = player.current_state(message.chat.id)
    if state.current is None:
        await message.reply_text(_no_track_reply())
        return
    await player.pause(message.chat.id)
    await message.reply_text("⏸ Playback paused.")


@Client.on_message(filters.command("resume") & filters.group)
@restrict_to_group
@admin_only
async def resume_command(client: Client, message: Message) -> None:
    player = client.require_player()
    state = player.current_state(message.chat.id)
    if state.current is None:
        await message.reply_text(_no_track_reply())
        return
    await player.resume(message.chat.id)
    await message.reply_text("▶️ Playback resumed.")


@Client.on_message(filters.command("skip") & filters.group)
@restrict_to_group
@admin_only
async def skip_command(client: Client, message: Message) -> None:
    player = client.require_player()
    state = player.current_state(message.chat.id)
    if state.current is None:
        await message.reply_text(_no_track_reply())
        return
    next_track = await player.skip(message.chat.id)
    if next_track is None:
        await message.reply_text("⏭ Skipped. Queue is now empty — leaving the voice chat.")
    else:
        await message.reply_text(f"⏭ Skipped. Now playing **{next_track.title}**.")


@Client.on_message(filters.command("stop") & filters.group)
@restrict_to_group
@admin_only
async def stop_command(client: Client, message: Message) -> None:
    player = client.require_player()
    await player.stop(message.chat.id)
    await message.reply_text("⏹ Playback stopped and queue cleared.")


@Client.on_message(filters.command("end") & filters.group)
@restrict_to_group
@admin_only
async def end_command(client: Client, message: Message) -> None:
    player = client.require_player()
    await player.stop(message.chat.id)
    await message.reply_text("👋 Session ended. Left the voice chat.")


@Client.on_message(filters.command("queue") & filters.group)
@restrict_to_group
async def queue_command(client: Client, message: Message) -> None:
    player = client.require_player()
    state = player.current_state(message.chat.id)
    pending = player.queues.snapshot(message.chat.id)

    if state.current is None:
        await message.reply_text("📭 The queue is empty and nothing is playing.")
        return

    lines = [f"🎶 **Now Playing:** {truncate(state.current.title, 45)}"]
    if pending:
        lines.append("\n**Up Next:**")
        for index, track in enumerate(pending[:15], start=1):
            lines.append(f"`{index}.` {truncate(track.title, 40)} — {format_duration(track.duration_seconds)}")
        if len(pending) > 15:
            lines.append(f"…and {len(pending) - 15} more.")
    else:
        lines.append("\nQueue is empty — this is the last track.")

    await message.reply_text("\n".join(lines))


@Client.on_message(filters.command("clearqueue") & filters.group)
@restrict_to_group
@admin_only
async def clearqueue_command(client: Client, message: Message) -> None:
    player = client.require_player()
    count = await player.queues.clear(message.chat.id)
    await message.reply_text(f"🧹 Cleared {count} track(s) from the queue.")


@Client.on_message(filters.command("remove") & filters.group)
@restrict_to_group
@admin_only
async def remove_command(client: Client, message: Message) -> None:
    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.reply_text("Usage: /remove <position>")
        return

    player = client.require_player()
    position = int(message.command[1])
    removed = await player.queues.remove_at(message.chat.id, position)
    if removed is None:
        await message.reply_text(f"⚠️ No track at position {position}.")
    else:
        await message.reply_text(f"🗑 Removed **{removed.title}** from the queue.")


@Client.on_message(filters.command("shuffle") & filters.group)
@restrict_to_group
@admin_only
async def shuffle_command(client: Client, message: Message) -> None:
    player = client.require_player()
    if player.queues.is_empty(message.chat.id):
        await message.reply_text("ℹ️ The queue is empty — nothing to shuffle.")
        return
    await player.queues.shuffle(message.chat.id)
    await message.reply_text("🔀 Queue shuffled.")


@Client.on_message(filters.command("loop") & filters.group)
@restrict_to_group
@admin_only
async def loop_command(client: Client, message: Message) -> None:
    player = client.require_player()
    state = player.current_state(message.chat.id)
    new_mode = _LOOP_CYCLE[state.loop_mode]
    await player.set_loop(message.chat.id, new_mode)
    labels = {LoopMode.OFF: "Off", LoopMode.TRACK: "Current Track", LoopMode.QUEUE: "Whole Queue"}
    await message.reply_text(f"🔁 Loop mode set to: **{labels[new_mode]}**")


@Client.on_message(filters.command("volume") & filters.group)
@restrict_to_group
@admin_only
async def volume_command(client: Client, message: Message) -> None:
    player = client.require_player()
    if len(message.command) < 2 or not message.command[1].isdigit():
        state = player.current_state(message.chat.id)
        await message.reply_text(f"🔊 Current volume: **{state.volume}%**\nUsage: /volume <0-200>")
        return

    volume = int(message.command[1])
    if not 0 <= volume <= 200:
        await message.reply_text("⚠️ Volume must be between 0 and 200.")
        return

    await player.set_volume(message.chat.id, volume)
    await message.reply_text(f"🔊 Volume set to **{volume}%**")


@Client.on_message(filters.command("replay") & filters.group)
@restrict_to_group
@admin_only
async def replay_command(client: Client, message: Message) -> None:
    player = client.require_player()
    track = await player.replay(message.chat.id)
    if track is None:
        await message.reply_text(_no_track_reply())
    else:
        await message.reply_text(f"🔁 Replaying **{track.title}** from the beginning.")


@Client.on_message(filters.command("seek") & filters.group)
@restrict_to_group
@admin_only
async def seek_command(client: Client, message: Message) -> None:
    if len(message.command) < 2 or not message.command[1].lstrip("-").isdigit():
        await message.reply_text("Usage: /seek <seconds>")
        return

    player = client.require_player()
    seconds = int(message.command[1])
    track = await player.seek(message.chat.id, seconds)
    if track is None:
        await message.reply_text(_no_track_reply())
    else:
        await message.reply_text(f"⏩ Seeked to {format_duration(seconds)} in **{track.title}**.")


@Client.on_message(filters.command("nowplaying") & filters.group)
@restrict_to_group
async def nowplaying_command(client: Client, message: Message) -> None:
    player = client.require_player()
    state = player.current_state(message.chat.id)
    if state.current is None:
        await message.reply_text(_no_track_reply())
        return

    track = state.current
    elapsed = state.elapsed_seconds()
    card_path = await generate_now_playing_card(
        title=track.title,
        artist=track.artist,
        duration_seconds=track.duration_seconds,
        elapsed_seconds=elapsed,
        thumbnail_url=track.thumbnail_url,
        requested_by=track.requested_by_name,
        queue_position=0,
    )
    await message.reply_photo(
        photo=str(card_path),
        caption=(
            f"🎶 **Now Playing**\n\n**{track.title}**\n👤 {track.artist}\n"
            f"{progress_bar(elapsed, track.duration_seconds)} {format_duration(elapsed)}/{format_duration(track.duration_seconds)}\n"
            f"🙋 Requested by {track.requested_by_name}"
        ),
        reply_markup=playback_controls(state.is_paused, state.loop_mode),
    )


@Client.on_message(filters.command("ping") & filters.group)
@restrict_to_group
async def ping_command(client: Client, message: Message) -> None:
    start = time.perf_counter()
    reply = await message.reply_text("🏓 Pinging...")
    latency_ms = (time.perf_counter() - start) * 1000
    await reply.edit_text(f"🏓 **Pong!** `{latency_ms:.2f} ms`")

