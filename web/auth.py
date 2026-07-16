"""
web/auth.py
===========
Minimal signed-token authentication for the dashboard API.

Deliberately dependency-free (no PyJWT): a token is
``base64url(json payload) "." base64url(HMAC-SHA256 signature)``. This is
enough for a single-admin dashboard and keeps the attack surface small and
auditable.

Required environment variables (set these on Railway, never commit them):

* ``DASHBOARD_USERNAME`` — the login username.
* ``DASHBOARD_PASSWORD`` — the login password.
* ``DASHBOARD_SECRET``   — random signing secret. If unset, a secret is
  generated at process start (logged once as a warning); this works fine
  but invalidates all sessions on every restart/redeploy, so setting a
  fixed value is strongly recommended for production use.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TOKEN_TTL_SECONDS = 12 * 60 * 60  # 12 hours


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


@dataclass(frozen=True, slots=True)
class DashboardCredentials:
    username: str
    password: str
    secret: str
    enabled: bool


def load_credentials() -> DashboardCredentials:
    username = os.getenv("DASHBOARD_USERNAME", "").strip()
    password = os.getenv("DASHBOARD_PASSWORD", "").strip()
    secret = os.getenv("DASHBOARD_SECRET", "").strip()

    enabled = bool(username and password)
    if not enabled:
        logger.warning(
            "DASHBOARD_USERNAME / DASHBOARD_PASSWORD are not set — the web "
            "dashboard API is disabled. Set both environment variables to "
            "enable it."
        )
    if enabled and not secret:
        secret = secrets.token_urlsafe(32)
        logger.warning(
            "DASHBOARD_SECRET is not set — using a randomly generated "
            "secret for this process only. Every existing dashboard login "
            "will be invalidated on the next restart. Set a fixed "
            "DASHBOARD_SECRET to avoid this."
        )

    return DashboardCredentials(username=username, password=password, secret=secret, enabled=enabled)


class InvalidToken(Exception):
    """Raised when a bearer token is missing, malformed, expired, or forged."""


def create_token(username: str, secret: str) -> tuple[str, float]:
    """Return ``(token, expires_at_unix_ts)``."""

    expires_at = time.time() + TOKEN_TTL_SECONDS
    payload = json.dumps({"sub": username, "exp": expires_at}, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload)
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{payload_b64}.{signature_b64}", expires_at


def verify_token(token: str, secret: str) -> str:
    """Return the username embedded in a valid token, or raise :class:`InvalidToken`."""

    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError as exc:
        raise InvalidToken("Malformed token.") from exc

    expected_signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    try:
        actual_signature = _b64url_decode(signature_b64)
    except Exception as exc:  # noqa: BLE001
        raise InvalidToken("Malformed token signature.") from exc

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise InvalidToken("Token signature mismatch.")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:  # noqa: BLE001
        raise InvalidToken("Malformed token payload.") from exc

    if payload.get("exp", 0) < time.time():
        raise InvalidToken("Token has expired.")

    username = payload.get("sub")
    if not username:
        raise InvalidToken("Token missing subject.")

    return username


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
