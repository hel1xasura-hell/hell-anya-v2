"""
plugins/owner.py
=================
Sensitive, owner-only commands: /restart, /update, /stats, /logs, /eval,
/broadcast. Every handler is wrapped in :func:`utils.decorators.owner_only`,
which checks ``from_user.id == OWNER_ID`` regardless of the chat's
administrator roster.
"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import traceback

from pyrogram import Client, filters
from pyrogram.types import Message

from config import LOG_DIR, config
from utils.decorators import owner_only

logger = logging.getLogger(__name__)


@Client.on_message(filters.command("restart"))
@owner_only
async def restart_command(client: Client, message: Message) -> None:
    await message.reply_text("🔄 Restarting...")
    logger.info("Restart requested by owner.")
    os.execv(sys.executable, [sys.executable, *sys.argv])


@Client.on_message(filters.command("update"))
@owner_only
async def update_command(client: Client, message: Message) -> None:
    status = await message.reply_text("⬇️ Pulling latest changes...")
    try:
        result = subprocess.run(
            ["git", "pull"], capture_output=True, text=True, timeout=60, check=False
        )
        output = (result.stdout + result.stderr).strip() or "No output."
        await status.edit_text(f"✅ Update complete.\n\n```\n{output[:3500]}\n```")
    except FileNotFoundError:
        await status.edit_text("⚠️ `git` is not available in this environment (e.g. some container deployments).")
    except subprocess.TimeoutExpired:
        await status.edit_text("⚠️ `git pull` timed out.")


@Client.on_message(filters.command("stats"))
@owner_only
async def stats_command(client: Client, message: Message) -> None:
    stats = await client.db.get_stats()
    top_tracks = "\n".join(f"• {title} — {count} plays" for title, count in stats["top_tracks"]) or "No data yet."

    active_chats = 1 if client.player else 0
    text = (
        "📊 **ᴀɴʏᴀ Statistics**\n\n"
        f"🎵 Total plays: `{stats['total_plays']}`\n"
        f"🔊 Voice engine: {'online' if client.player else 'offline'}\n\n"
        f"**Top Tracks**\n{top_tracks}"
    )
    await message.reply_text(text)


@Client.on_message(filters.command("logs"))
@owner_only
async def logs_command(client: Client, message: Message) -> None:
    log_file = LOG_DIR / "anya.log"
    if not log_file.exists():
        await message.reply_text("⚠️ No log file found yet.")
        return
    await message.reply_document(document=str(log_file), caption="🪵 Latest logs.")


@Client.on_message(filters.command("eval"))
@owner_only
async def eval_command(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text("Usage: /eval <python expression>")
        return

    code = message.text.split(None, 1)[1]
    sandbox = {"client": client, "message": message, "config": config}

    stdout_capture = io.StringIO()
    try:
        old_stdout = sys.stdout
        sys.stdout = stdout_capture
        try:
            result = eval(code, sandbox)  # noqa: S307 - explicitly owner-gated, intentional feature
            if hasattr(result, "__await__"):
                result = await result
        finally:
            sys.stdout = old_stdout

        output = stdout_capture.getvalue()
        response = f"```\n{output}\n```" if output else ""
        response += f"\n**Result:** `{result!r}`" if result is not None else ""
        await message.reply_text(response.strip() or "✅ Executed (no output).")
    except Exception:  # noqa: BLE001 - intentional broad catch for a debugging tool
        await message.reply_text(f"❌ **Error:**\n```\n{traceback.format_exc()[-3500:]}\n```")


@Client.on_message(filters.command("broadcast"))
@owner_only
async def broadcast_command(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text("Usage: /broadcast <message>")
        return

    text = message.text.split(None, 1)[1]
    try:
        await client.send_message(config.allowed_group_id, f"📢 **Announcement**\n\n{text}")
        await message.reply_text("✅ Broadcast sent.")
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(f"⚠️ Broadcast failed: {exc}")

