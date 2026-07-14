"""plugins/settings.py — ``/settings``: view and adjust per-chat preferences."""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import config
from utils.decorators import admin_only, restrict_to_group


def _settings_text(volume: int, loop_mode: str) -> str:
    return (
        f"⚙️ **{config.bot_name} Settings**\n\n"
        f"🔊 Default Volume: `{volume}%`\n"
        f"🔁 Loop Mode: `{loop_mode}`\n"
        f"⏳ Inactivity Timeout: `{config.inactivity_timeout_seconds}s`\n"
        f"📦 Max Queue Size: `{config.max_queue_size}`\n\n"
        f"Use the buttons below or the dedicated `/volume` and `/loop` commands to adjust playback settings."
    )


@Client.on_message(filters.command("settings") & filters.group)
@restrict_to_group
@admin_only
async def settings_command(client: Client, message: Message) -> None:
    chat_id = message.chat.id
    volume = await client.db.get_chat_setting(chat_id, "volume", config.default_volume)
    loop_mode = await client.db.get_chat_setting(chat_id, "loop_mode", "OFF")

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔊 Adjust Volume", callback_data="ctrl:volume")],
            [InlineKeyboardButton("🔁 Cycle Loop Mode", callback_data="ctrl:loop")],
            [InlineKeyboardButton("✖️ Close", callback_data="ctrl:close")],
        ]
    )

    await message.reply_text(_settings_text(volume, loop_mode), reply_markup=keyboard)
