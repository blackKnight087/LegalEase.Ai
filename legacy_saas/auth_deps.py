"""FastAPI auth dependency."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_tokens import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict[str, Any]:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "Not authenticated")
    payload = decode_access_token(creds.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(401, "Invalid or expired token")
    return {
        "id": payload["sub"],
        "username": payload.get("username", ""),
        "membership": payload.get("membership", "Free"),
        "role": payload.get("role", "user"),
    }
