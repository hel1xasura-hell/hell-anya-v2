"""
main.py
=======
Application entrypoint for ᴀɴʏᴀ.

Responsibilities:
    * Configure logging before anything else runs.
    * Construct and start :class:`~core.bot.AnyaClient`.
    * Wire the announcer so playback events become Telegram messages.
    * Install signal handlers for graceful shutdown (SIGINT/SIGTERM), which
      matters on Railway: the platform sends SIGTERM on redeploys and
      expects the process to exit cleanly within a short grace period.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from utils.logger import setup_logging

setup_logging()
logger = logging.getLogger("anya.main")


async def run() -> None:
    # Imported after logging is configured so early log lines from these
    # modules (e.g. config validation) are formatted correctly.
    from core.announcer import register_announcer
    from core.bot import AnyaClient
    from web.server import serve as serve_dashboard

    client = AnyaClient()
    await client.start()

    if client.player is not None:
        register_announcer(client)

    dashboard_task = asyncio.create_task(serve_dashboard(client))

    stop_event = asyncio.Event()

    def _request_shutdown(*_args: object) -> None:
        logger.info("Shutdown signal received.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # add_signal_handler is unavailable on some platforms (e.g. Windows).
            signal.signal(sig, _request_shutdown)

    logger.info("ᴀɴʏᴀ is now running. Press Ctrl+C to stop.")
    await stop_event.wait()

    dashboard_task.cancel()
    await client.stop()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")


if __name__ == "__main__":
    main()
