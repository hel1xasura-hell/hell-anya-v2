"""
plugins/start_private.py
=========================
ᴀɴʏᴀ intentionally ignores private chats entirely (see ``plugins.help`` and
``utils.decorators.restrict_to_group``) — except for one case: someone
tapping the bot's "Start" button always lands in a private chat and sends
``/start`` there. Staying completely silent in that specific moment reads
as broken rather than private, so this single handler sends a short
redirect and does nothing else. No other private-chat command is answered.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message

from config import config


@Client.on_message(filters.command("start") & filters.private)
async def start_private_redirect(client: Client, message: Message) -> None:
    await message.reply_text(
        f"👋 I'm **{config.bot_name}**, a private music bot for one specific group.\n\n"
        f"I only respond inside that group — add me there and use `/help` to see what I can do."
    )
