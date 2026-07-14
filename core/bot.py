"""
core/bot.py
============
``AnyaClient`` — the Pyrogram client subclass at the centre of the
application. It owns the long-lived singletons (queue manager, voice
engine, player, database) and exposes them as attributes so plugin
handlers can reach them via ``client.player``, ``client.db``, etc.

A second, userbot-style :class:`~pyrogram.Client` (assistant) is created
from ``SESSION_STRING`` because Telegram bot accounts cannot join voice
chats themselves — PyTgCalls streams through a regular user account that
is a member of the group. If no session string is configured, voice
features are disabled but text commands still work, which keeps local
development frictionless.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pyrogram import Client
from pytgcalls import PyTgCalls

from config import CACHE_DIR, config
from core.player import Player
from core.queue_manager import QueueManager
from core.voice_engine import VoiceEngine
from database import get_database
from database.base import Database

logger = logging.getLogger(__name__)

PLUGINS_ROOT = "plugins"


class AnyaClient(Client):
    """The bot's Pyrogram client, extended with application-level services."""

    def __init__(self) -> None:
        super().__init__(
            name="anya_bot",
            api_id=config.api_id,
            api_hash=config.api_hash,
            bot_token=config.bot_token,
            workdir=str(CACHE_DIR),
            plugins=dict(root=PLUGINS_ROOT),
            sleep_threshold=30,
        )

        self.db: Database = get_database()
        self.queue_manager = QueueManager(max_queue_size=config.max_queue_size)

        self.assistant: Client | None = None
        self.calls: PyTgCalls | None = None
        self.voice_engine: VoiceEngine | None = None
        self.player: Player | None = None

        if config.session_string:
            self.assistant = Client(
                name="anya_assistant",
                api_id=config.api_id,
                api_hash=config.api_hash,
                session_string=config.session_string,
                workdir=str(CACHE_DIR),
                in_memory=True,
            )
        else:
            logger.warning(
                "SESSION_STRING is not set — voice chat streaming is disabled. "
                "Text commands will still function once configured, but /play "
                "cannot join a voice chat without an assistant account."
            )

    async def start(self) -> None:  # noqa: D102 - see class docstring
        await self.db.connect()
        await super().start()

        if self.assistant is not None:
            await self.assistant.start()
            self.calls = PyTgCalls(self.assistant)
            await self.calls.start()
            self.voice_engine = VoiceEngine(self.calls)
            self.player = Player(self.queue_manager, self.voice_engine, self.db)
            logger.info("Voice engine online (assistant account connected).")

        me = await self.get_me()
        logger.info("ᴀɴʏᴀ started as @%s (id=%s)", me.username, me.id)

    async def stop(self, *args, **kwargs) -> None:  # noqa: D102
        logger.info("Shutting down gracefully...")

        if self.calls is not None:
            try:
                await self.calls.stop()
            except Exception:  # noqa: BLE001
                logger.exception("Error stopping PyTgCalls")

        if self.assistant is not None and self.assistant.is_connected:
            await self.assistant.stop()

        await self.db.close()
        await super().stop(*args, **kwargs)
        logger.info("Shutdown complete.")

    def require_player(self) -> Player:
        """Return the active :class:`Player`, raising a friendly error if voice
        features are disabled because no assistant session is configured."""

        if self.player is None:
            raise RuntimeError(
                "Voice playback is unavailable: SESSION_STRING is not configured. "
                "Generate a Pyrogram user session and set it in your environment."
            )
        return self.player
