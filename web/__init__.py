"""
web/
====
Optional HTTP dashboard API for ᴀɴʏᴀ.

This package is completely decoupled from the Telegram bot logic: it reads
the same ``client`` instance (queue, player, database) that the plugins use,
and exposes it over a small authenticated REST API so a static frontend
(e.g. hosted on GitHub Pages) can display live data and issue control
commands.

Nothing in ``core/`` or ``plugins/`` imports from this package — if FastAPI
is ever unavailable or the dashboard is disabled, the bot itself is
completely unaffected.
"""
