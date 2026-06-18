from __future__ import annotations

import os
from typing import Dict, Optional

from fastapi import HTTPException

from .matter_repo import get_matter_access_context, has_matter_access
from .observability import emit_event

STRICT_SCOPE_ENFORCEMENT = os.getenv("MATTER_STRICT_SCOPE_ENFORCEMENT", "1").lower() in (
    "1",
    "true",
    "yes",
)
STRICT_ROLE_WRITE_ENFORCEMENT = os.getenv("MATTER_STRICT_ROLE_WRITE", "1").lower() in (
    "1",
    "true",
    "yes",
)


def resolve_matter_context(user_id: str, matter_id: str) -> Dict[str, str]:
    ctx = get_matter_access_context(user_id, matter_id)
    if not ctx:
        emit_event("matter_access_denied", request_user_id=str(user_id), matter_id=str(matter_id))
        raise HTTPException(404, "Matter not found")
    return ctx


def require_matter_write_access(ctx: Dict[str, str]) -> None:
    if not STRICT_ROLE_WRITE_ENFORCEMENT:
        return
    if (ctx.get("role") or "viewer") not in {"owner", "lawyer"}:
        emit_event(
            "matter_write_denied",
            request_user_id=str(ctx.get("request_user_id") or ""),
            owner_user_id=str(ctx.get("owner_user_id") or ""),
            role=str(ctx.get("role") or ""),
        )
        raise HTTPException(403, "Insufficient matter role for write action")


def normalize_chat_scope(mode: str, matter_id: Optional[str]) -> Optional[str]:
    """Matter scope for retrieval — hybrid/deep_case only. KB mode always uses global index."""
    scoped_modes = {"hybrid", "deep_case"}
    mid = (matter_id or "").strip()
    if mode in scoped_modes and mid:
        return mid
    return None


def normalize_matter_ai_scope(
    matter_id: Optional[str],
    matter_mode: Optional[str],
) -> Optional[str]:
    """Matter AI workspace — witness/evidence/hearing queries use matter index only."""
    from backend.app.core.kb_retrieval_router import is_matter_ai_mode

    mid = (matter_id or "").strip()
    if mid and is_matter_ai_mode(matter_mode):
        return mid
    return None


def validate_chat_scope(user_id: str, mode: str, matter_id: Optional[str]) -> Optional[str]:
    scoped = normalize_chat_scope(mode, matter_id)
    if not scoped:
        return None
    if STRICT_SCOPE_ENFORCEMENT and not has_matter_access(user_id, scoped):
        emit_event(
            "chat_scope_denied",
            request_user_id=str(user_id),
            mode=str(mode),
            matter_id=str(scoped),
        )
        raise HTTPException(404, "Matter not found")
    return scoped
