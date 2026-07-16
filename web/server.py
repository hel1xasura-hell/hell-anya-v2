"""
web/server.py
=============
The dashboard's REST API. Runs inside the same process as the bot (same
Railway service), sharing the same asyncio event loop, so control endpoints
can call straight into the live :class:`~core.player.Player` /
:class:`~core.queue_manager.QueueManager` instances — no IPC needed.

Every authenticated request also gets a "source=dashboard" audit log entry,
so actions taken from the web UI show up in the same history as Telegram
commands, tagged with which login performed them.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from config import LOG_DIR, config
from core.models import LoopMode
from web.auth import (
    DashboardCredentials,
    InvalidToken,
    constant_time_equals,
    create_token,
    load_credentials,
    verify_token,
)

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# Populated by ``register_client`` once the bot has finished starting up.
_client: Any = None
_credentials: DashboardCredentials = load_credentials()
_START_TIME = time.time()


def register_client(client: Any) -> None:
    """Give the API access to the running bot's client instance."""

    global _client
    _client = client


def _require_client() -> Any:
    if _client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Bot is still starting up.")
    return _client


def _require_player(client: Any):
    if client.player is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Voice playback is unavailable (no assistant session configured).",
        )
    return client.player


async def _current_username(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if not _credentials.enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Dashboard login is not configured on the server.")
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token.")
    try:
        return verify_token(credentials.credentials, _credentials.secret)
    except InvalidToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


async def _audit(client: Any, username: str, action: str) -> None:
    try:
        await client.db.log_command(
            chat_id=config.allowed_group_id,
            user_id=None,
            username=username,
            full_name=f"dashboard:{username}",
            command=action,
            source="dashboard",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to write dashboard audit entry.")


# -- Request/response models ---------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: float


class VolumeRequest(BaseModel):
    volume: int = Field(ge=0, le=200)


class LoopRequest(BaseModel):
    mode: str  # "off" | "track" | "queue"


class RemoveRequest(BaseModel):
    position: int = Field(ge=1)


class BroadcastRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


# -- App -------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(title="ᴀɴʏᴀ Dashboard API", version="1.0.0")

    cors_origins = os.getenv("DASHBOARD_CORS_ORIGIN", "*")
    origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "uptime_seconds": int(time.time() - _START_TIME)}

    @app.post("/api/auth/login", response_model=LoginResponse)
    async def login(body: LoginRequest) -> LoginResponse:
        if not _credentials.enabled:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Dashboard login is not configured on the server.")
        if not (
            constant_time_equals(body.username, _credentials.username)
            and constant_time_equals(body.password, _credentials.password)
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password.")
        token, expires_at = create_token(body.username, _credentials.secret)
        return LoginResponse(token=token, expires_at=expires_at)

    @app.get("/api/auth/me")
    async def me(username: str = Depends(_current_username)) -> dict[str, str]:
        return {"username": username}

    @app.get("/api/overview")
    async def overview(username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        stats = await client.db.get_stats()
        chat_id = config.allowed_group_id

        now_playing = None
        queue_length = 0
        voice_online = client.player is not None

        if client.player is not None:
            state = client.player.current_state(chat_id)
            queue_length = len(client.player.queues.snapshot(chat_id))
            if state.current is not None:
                now_playing = {
                    **state.current.as_dict(),
                    "elapsed_seconds": state.elapsed_seconds(),
                    "is_paused": state.is_paused,
                    "volume": state.volume,
                    "loop_mode": state.loop_mode.name,
                }

        return {
            "bot_name": config.bot_name,
            "voice_engine_online": voice_online,
            "now_playing": now_playing,
            "queue_length": queue_length,
            "total_plays": stats["total_plays"],
            "top_tracks": stats["top_tracks"],
            "top_users": stats["top_users"],
            "uptime_seconds": int(time.time() - _START_TIME),
        }

    @app.get("/api/queue")
    async def get_queue(username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        player = _require_player(client)
        chat_id = config.allowed_group_id
        state = player.current_state(chat_id)
        pending = player.queues.snapshot(chat_id)
        return {
            "now_playing": {
                **state.current.as_dict(),
                "elapsed_seconds": state.elapsed_seconds(),
                "is_paused": state.is_paused,
                "volume": state.volume,
                "loop_mode": state.loop_mode.name,
            }
            if state.current
            else None,
            "pending": [track.as_dict() for track in pending],
        }

    @app.get("/api/users")
    async def get_users(username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        return {"users": await client.db.get_users()}

    @app.get("/api/commands")
    async def get_commands(
        limit: int = 100, offset: int = 0, username: str = Depends(_current_username)
    ) -> dict[str, Any]:
        client = _require_client()
        limit = max(1, min(limit, 500))
        entries = await client.db.get_audit_log(limit=limit, offset=max(0, offset))
        return {"entries": entries}

    @app.get("/api/logs")
    async def get_logs(lines: int = 200, username: str = Depends(_current_username)) -> dict[str, Any]:
        lines = max(1, min(lines, 2000))
        log_file = LOG_DIR / "anya.log"
        if not log_file.exists():
            return {"lines": []}
        with log_file.open("r", encoding="utf-8", errors="replace") as fh:
            tail = fh.readlines()[-lines:]
        return {"lines": [line.rstrip("\n") for line in tail]}

    @app.post("/api/control/{action}")
    async def control(action: str, username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        player = _require_player(client)
        chat_id = config.allowed_group_id

        if action == "pause":
            await player.pause(chat_id)
        elif action == "resume":
            await player.resume(chat_id)
        elif action == "skip":
            await player.skip(chat_id)
        elif action == "stop":
            await player.stop(chat_id)
        elif action == "shuffle":
            await player.queues.shuffle(chat_id)
        elif action == "clearqueue":
            await player.queues.clear(chat_id)
        elif action == "replay":
            await player.replay(chat_id)
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown control action: {action!r}")

        await _audit(client, username, f"/{action}")
        return {"ok": True}

    @app.post("/api/control/volume")
    async def set_volume(body: VolumeRequest, username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        player = _require_player(client)
        await player.set_volume(config.allowed_group_id, body.volume)
        await _audit(client, username, f"/volume {body.volume}")
        return {"ok": True, "volume": body.volume}

    @app.post("/api/control/loop")
    async def set_loop(body: LoopRequest, username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        player = _require_player(client)
        try:
            mode = LoopMode[body.mode.upper()]
        except KeyError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode must be one of: off, track, queue") from exc
        await player.set_loop(config.allowed_group_id, mode)
        await _audit(client, username, f"/loop {body.mode}")
        return {"ok": True, "mode": mode.name}

    @app.post("/api/control/remove")
    async def remove_track(body: RemoveRequest, username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        player = _require_player(client)
        removed = await player.queues.remove_at(config.allowed_group_id, body.position)
        if removed is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No track at position {body.position}.")
        await _audit(client, username, f"/remove {body.position}")
        return {"ok": True, "removed": removed.as_dict()}

    @app.post("/api/broadcast")
    async def broadcast(body: BroadcastRequest, username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        await client.send_message(config.allowed_group_id, body.message)
        await _audit(client, username, f"broadcast: {body.message[:200]}")
        return {"ok": True}

    @app.post("/api/restart")
    async def restart(username: str = Depends(_current_username)) -> dict[str, Any]:
        client = _require_client()
        await _audit(client, username, "/restart")
        logger.info("Restart requested from dashboard by %s.", username)

        async def _delayed_restart() -> None:
            await asyncio.sleep(0.5)  # let the HTTP response flush first
            os.execv(sys.executable, [sys.executable, *sys.argv])

        asyncio.create_task(_delayed_restart())
        return {"ok": True, "message": "Restarting..."}

    return app


async def serve(client: Any) -> None:
    """Run the dashboard API forever. Intended to be launched as a background
    ``asyncio`` task from ``main.py``, sharing the bot's event loop.

    Binds to ``$PORT`` (Railway injects this for the service's public HTTP
    port) or 8080 for local development. If neither DASHBOARD_USERNAME nor
    DASHBOARD_PASSWORD is set, the server still starts (so /api/health works
    for platform health checks) but every authenticated route returns 503.
    """

    import uvicorn
    import uvicorn.server as uvicorn_server_module

    # main.py already installs SIGINT/SIGTERM handlers for graceful shutdown
    # of the Telegram client. uvicorn.Server.serve() installs its own on the
    # same signals by default, which would silently take over and break that
    # shutdown path since both run in this one process/event loop. Disabling
    # uvicorn's signal handling here is the documented way to embed it
    # inside a larger application.
    uvicorn_server_module.HANDLED_SIGNALS = ()

    register_client(client)
    app = create_app()

    port = int(os.getenv("PORT", "8080"))
    uv_config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(uv_config)

    if _credentials.enabled:
        logger.info("Dashboard API starting on port %s (login enabled for user %r).", port, _credentials.username)
    else:
        logger.warning("Dashboard API starting on port %s with login DISABLED.", port)

    await server.serve()
