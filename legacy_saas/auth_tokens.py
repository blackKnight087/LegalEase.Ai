"""Lightweight signed tokens for the React API (no Streamlit session)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any, Dict, Optional

_DEV_SECRET = "legalease-dev-change-in-production"
SECRET = os.getenv("LEGALEASE_API_SECRET") or os.getenv("JWT_SECRET") or _DEV_SECRET
TOKEN_TTL_SEC = int(os.getenv("LEGALEASE_TOKEN_TTL", str(7 * 24 * 3600)))


def _ensure_secret_configured() -> None:
    if SECRET != _DEV_SECRET:
        return
    if os.getenv("SAAS_PRODUCTION", "0").lower() in ("1", "true", "yes"):
        raise RuntimeError(
            "JWT_SECRET or LEGALEASE_API_SECRET must be set in production (min 32 chars)"
        )


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return urlsafe_b64decode(s + pad)


def create_access_token(user: Dict[str, Any]) -> str:
    _ensure_secret_configured()
    payload = {
        "sub": user["id"],
        "username": user.get("username", ""),
        "membership": user.get("membership", "Free"),
        "role": user.get("role", "user"),
        "exp": int(time.time()) + TOKEN_TTL_SEC,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    _ensure_secret_configured()
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (json.JSONDecodeError, ValueError):
        return None
    if payload.get("exp", 0) < int(time.time()):
        return None
    return payload
