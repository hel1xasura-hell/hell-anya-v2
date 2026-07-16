"""plugins/help.py — ``/help`` and ``/start``."""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from config import config
from utils.decorators import restrict_to_group

_HELP_TEXT = f"""
✨ **{config.bot_name} — Command Reference**

**Playback**
`/play <query|link>` — search or queue a song
`/pause` `/resume` `/skip` `/stop` `/end`
`/queue` `/clearqueue` `/remove <n>`
`/shuffle` `/loop` `/volume <0-200>`
`/replay` `/seek <seconds>` `/nowplaying`

**Download**
`/download <query|link>` — send the actual audio file into the chat
`/save <link>` — download an Instagram/TikTok/Twitter/etc. video into the chat

**Translate**
`/tr uzb <text>` — translate to Uzbek
`/tr eng <text>` — translate to English
`/tr ind <text>` — translate to Indonesian
(reply to a message with just `/tr <lang>` to translate it)

**Info**
`/lyrics [artist - title]`
`/settings`
`/ping`

**Owner Only**
`/restart` `/update` `/stats` `/logs` `/eval` `/broadcast`

Playback controls (aside from `/play`, `/queue`, `/nowplaying`, `/lyrics`) require
group administrator permissions.
""".strip()


@Client.on_message(filters.command(["help", "start"]) & filters.group)
@restrict_to_group
async def help_command(client: Client, message: Message) -> None:
    await message.reply_text(_HELP_TEXT)
    
