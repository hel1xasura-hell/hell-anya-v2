"""plugins/lyrics.py — the standalone ``/lyrics`` command."""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from utils.decorators import restrict_to_group
from utils.formatters import truncate
from utils.lyrics import LyricsNotFoundError, fetch_lyrics


@Client.on_message(filters.command("lyrics") & filters.group)
@restrict_to_group
async def lyrics_command(client: Client, message: Message) -> None:
    player = client.require_player()
    state = player.current_state(message.chat.id)

    if len(message.command) > 1:
        query = message.text.split(None, 1)[1].strip()
        if " - " in query:
            artist, title = query.split(" - ", 1)
        else:
            artist, title = "", query
    elif state.current is not None:
        artist, title = state.current.artist, state.current.title
    else:
        await message.reply_text("Usage: /lyrics <artist - title>, or use it while a track is playing.")
        return

    status = await message.reply_text("📝 Searching for lyrics...")
    try:
        lyrics = await fetch_lyrics(artist, title)
    except LyricsNotFoundError:
        await status.edit_text(f"❌ No lyrics found for **{title}**.")
        return

    await status.edit_text(f"📝 **Lyrics — {title}**\n\n{truncate(lyrics, 3800)}")
        
