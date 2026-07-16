"""
utils/decorators.py
====================
Security decorators applied to every plugin handler.

ᴀɴʏᴀ is a *private* bot bound to exactly one Telegram group
(``ALLOWED_GROUP_ID``). These decorators enforce that boundary uniformly so
no individual plugin can accidentally skip the check.

Design note
-----------
Pyrogram handlers receive ``(client, message)`` or ``(client, callback_query)``.
Both ``Message`` and ``CallbackQuery`` expose ``.from_user`` and either
``.chat`` (Message) or ``.message.chat`` (CallbackQuery), so the helpers
below normalise access to those attributes before making a decision.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Awaitable, Callable, TypeVar

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import CallbackQuery, Message

from config import config

logger = logging.getLogger(__name__)

_Handler = TypeVar("_Handler", bound=Callable[..., Awaitable[Any]])

_ADMIN_STATUSES = (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


def _extract_chat_and_user(update: Message | CallbackQuery):
    if isinstance(update, CallbackQuery):
        chat = update.message.chat if update.message else None
        user = update.from_user
    else:
        chat = update.chat
        user = update.from_user
    return chat, user


def _describe_action(update: Message | CallbackQuery) -> str:
    """Best-effort human-readable command/action name for the audit log."""

    if isinstance(update, CallbackQuery):
        return f"callback:{update.data}" if update.data else "callback"
    if update.command:
        return "/" + update.command[0]
    return "message"


async def _record_activity(client: Client, update: Message | CallbackQuery) -> None:
    """Write one audit-log entry and refresh the known-users registry.

    Best-effort and silent on failure — the dashboard's visibility into bot
    activity must never be able to break an actual command handler.
    """

    db = getattr(client, "db", None)
    if db is None:
        return

    chat, user = _extract_chat_and_user(update)
    if user is None:
        return

    full_name = " ".join(filter(None, [user.first_name, user.last_name])) or user.username or str(user.id)

    try:
        await db.upsert_user(user.id, user.username or "", full_name)
        await db.log_command(
            chat_id=chat.id if chat else None,
            user_id=user.id,
            username=user.username or "",
            full_name=full_name,
            command=_describe_action(update),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to record activity for dashboard audit log.")


async def _reply(update: Message | CallbackQuery, text: str) -> None:
    """Reply to either a Message or a CallbackQuery in a uniform way."""

    if isinstance(update, CallbackQuery):
        await update.answer(text, show_alert=True)
    else:
        await update.reply_text(text)


def restrict_to_group(handler: _Handler) -> _Handler:
    """Ensure the handler only runs inside the single authorised group.

    * Private chats and channels are silently ignored (no reply — private
      bots should not acknowledge unsolicited use).
    * If the bot detects it has been added to a foreign group chat, it
      automatically leaves.
    """

    @functools.wraps(handler)
    async def wrapper(client: Client, update: Message | CallbackQuery, *args: Any, **kwargs: Any) -> Any:
        chat, _user = _extract_chat_and_user(update)
        if chat is None:
            return None

        if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            # Ignore private chats and channels entirely.
            return None

        if chat.id != config.allowed_group_id:
            logger.warning("Unauthorised group detected (id=%s, title=%s) — leaving.", chat.id, chat.title)
            try:
                await client.leave_chat(chat.id)
            except Exception:  # noqa: BLE001 - best effort cleanup
                logger.exception("Failed to leave unauthorised chat %s", chat.id)
            return None

        await _record_activity(client, update)
        return await handler(client, update, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def owner_only(handler: _Handler) -> _Handler:
    """Restrict a handler to ``OWNER_ID`` exclusively."""

    @functools.wraps(handler)
    async def wrapper(client: Client, update: Message | CallbackQuery, *args: Any, **kwargs: Any) -> Any:
        _chat, user = _extract_chat_and_user(update)
        if user is None or user.id != config.owner_id:
            await _reply(update, "⛔ This command is restricted to the bot owner.")
            return None
        await _record_activity(client, update)
        return await handler(client, update, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def admin_only(handler: _Handler) -> _Handler:
    """Restrict a handler to Telegram group administrators (and the owner).

    The owner always bypasses this check, satisfying the requirement that
    ``OWNER_ID`` has unrestricted access regardless of their in-chat rank.
    """

    @functools.wraps(handler)
    async def wrapper(client: Client, update: Message | CallbackQuery, *args: Any, **kwargs: Any) -> Any:
        chat, user = _extract_chat_and_user(update)
        if chat is None or user is None:
            return None

        if user.id == config.owner_id:
            return await handler(client, update, *args, **kwargs)

        try:
            member = await client.get_chat_member(chat.id, user.id)
        except Exception:  # noqa: BLE001
            logger.exception("Could not resolve chat member status for user %s", user.id)
            await _reply(update, "⚠️ Could not verify your permissions. Try again.")
            return None

        if member.status not in _ADMIN_STATUSES:
            await _reply(update, "⛔ Only group administrators may use playback controls.")
            return None

        return await handler(client, update, *args, **kwargs)

    return wrapper  # type: ignore[return-value]
