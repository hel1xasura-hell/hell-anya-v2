"""
plugins/group_guard.py
=======================
Reacts the instant ᴀɴʏᴀ is added to any chat that is not the single
authorised group: it leaves immediately, without waiting for a command to
be issued. This is the proactive counterpart to the per-command
``restrict_to_group`` decorator used everywhere else.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import ChatMemberUpdated

from config import config

logger = logging.getLogger(__name__)


@Client.on_chat_member_updated(filters.group)
async def guard_unauthorised_group(client: Client, update: ChatMemberUpdated) -> None:
    """Leave any group that is not ``ALLOWED_GROUP_ID`` the moment we notice
    membership there — covers the case of being added directly."""

    me = await client.get_me()
    new_member = update.new_chat_member
    if new_member is None or new_member.user.id != me.id:
        return

    if new_member.status not in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        return

    if update.chat.id != config.allowed_group_id:
        logger.warning(
            "ᴀɴʏᴀ was added to an unauthorised chat — leaving immediately. "
            "Detected chat id=%s (title=%s) but ALLOWED_GROUP_ID is set to %s. "
            "If this IS the group you intend to use, set ALLOWED_GROUP_ID=%s in your environment.",
            update.chat.id,
            update.chat.title,
            config.allowed_group_id,
            update.chat.id,
        )
        try:
            await client.leave_chat(update.chat.id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to leave unauthorised chat %s", update.chat.id)
    else:
        logger.info("ᴀɴʏᴀ confirmed active in the authorised group (id=%s).", update.chat.id)


@Client.on_message(filters.new_chat_members)
async def guard_new_chat_members(client: Client, message) -> None:  # type: ignore[no-untyped-def]
    """Fallback path: some clients deliver additions as a service message
    rather than (or in addition to) a ``chat_member`` update."""

    me = await client.get_me()
    if not any(member.id == me.id for member in message.new_chat_members):
        return

    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if message.chat.id != config.allowed_group_id:
        logger.warning(
            "ᴀɴʏᴀ added via service message to an unauthorised chat — leaving. "
            "Detected chat id=%s but ALLOWED_GROUP_ID is set to %s. "
            "If this IS the group you intend to use, set ALLOWED_GROUP_ID=%s in your environment.",
            message.chat.id,
            config.allowed_group_id,
            message.chat.id,
        )
        try:
            await client.leave_chat(message.chat.id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to leave unauthorised chat %s", message.chat.id)
