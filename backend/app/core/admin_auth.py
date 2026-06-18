"""Superadmin / admin authorization."""
from __future__ import annotations

import os
from typing import Any, Dict

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.core.auth import get_current_user

_optional_bearer = HTTPBearer(auto_error=False)
from backend.app.core.database import connect_data_db


def _superadmin_usernames() -> set:
    raw = os.getenv("SUPERADMIN_USERNAMES", "admin").strip()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def is_superadmin(user: Dict[str, Any]) -> bool:
    role = str(user.get("role") or "user").lower()
    if role in ("admin", "superadmin"):
        return True
    uname = str(user.get("username") or "").lower()
    return uname in _superadmin_usernames()


def user_is_suspended(user_id: str) -> bool:
    conn = connect_data_db()
    try:
        row = conn.execute(
            "SELECT suspended FROM users WHERE id = ? LIMIT 1",
            (str(user_id),),
        ).fetchone()
        return bool(row and row[0])
    except Exception:
        return False
    finally:
        conn.close()


def require_superadmin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user_is_suspended(str(user["id"])):
        raise HTTPException(403, "Account suspended")
    if not is_superadmin(user):
        raise HTTPException(403, "Admin access required")
    return user


def require_metrics_access(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
) -> Dict[str, Any]:
    """Production: superadmin only. Dev: open without auth."""
    from backend.app.core.production_config import production_mode

    if not production_mode():
        return {}
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "Not authenticated")
    from auth_tokens import decode_access_token

    payload = decode_access_token(creds.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(401, "Invalid or expired token")
    user = {
        "id": payload["sub"],
        "username": payload.get("username", ""),
        "role": payload.get("role", "user"),
    }
    if not is_superadmin(user):
        raise HTTPException(403, "Admin access required")
    return user
