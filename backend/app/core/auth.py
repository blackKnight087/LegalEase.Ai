"""JWT auth dependency."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_tokens import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def resolve_membership(user_id: str, jwt_membership: str = "Free") -> str:
    """Prefer live DB membership over JWT payload (SaaS plan changes)."""
    try:
        from legalease_auth import get_membership

        return get_membership(str(user_id), fallback=jwt_membership or "Free")
    except Exception:
        return jwt_membership or "Free"


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict[str, Any]:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "Not authenticated")
    payload = decode_access_token(creds.credentials)
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
