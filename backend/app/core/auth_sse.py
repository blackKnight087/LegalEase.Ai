"""Flexible auth for SSE streams (Bearer header or access_token query param)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_tokens import decode_access_token

from .auth import resolve_membership

_bearer = HTTPBearer(auto_error=False)


def _user_from_token(token: str) -> Dict[str, Any]:
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(401, "Invalid or expired token")
    uid = payload["sub"]
    try:
        from backend.app.core.admin_auth import user_is_suspended

        if user_is_suspended(uid):
            raise HTTPException(403, "Account suspended")
    except HTTPException:
        raise
    except Exception:
        pass
    jwt_membership = payload.get("membership", "Free")
    org_id = ""
    try:
        from backend.app.core.org_service import get_primary_org_id

        org_id = get_primary_org_id(uid)
    except Exception:
        pass
    return {
        "id": uid,
        "username": payload.get("username", ""),
        "membership": resolve_membership(uid, jwt_membership),
        "role": payload.get("role", "user"),
        "org_id": org_id,
    }


def get_current_user_sse(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    access_token: str = Query("", description="JWT for EventSource (no Bearer header)"),
) -> Dict[str, Any]:
    if creds and creds.scheme.lower() == "bearer":
        return _user_from_token(creds.credentials)
    if access_token.strip():
        return _user_from_token(access_token.strip())
    raise HTTPException(401, "Not authenticated")
