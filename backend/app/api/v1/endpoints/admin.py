"""Superadmin API — users, audit, usage."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ....core.admin_auth import require_superadmin
from ....core.admin_service import (
    get_system_health,
    get_usage_summary,
    list_users,
    set_user_plan,
    set_user_suspended,
)
from ....core.audit_service import list_audit_events

router = APIRouter(tags=["admin"])


class PlanOverrideRequest(BaseModel):
    plan: str = Field(..., pattern="^(Free|Pro|Legal Pro)$")


@router.get("/users")
def admin_users(
    q: str = Query("", alias="q"),
    limit: int = Query(50, le=200),
    _admin: Dict[str, Any] = Depends(require_superadmin),
):
    return {"users": list_users(query=q, limit=limit)}


@router.post("/users/{user_id}/suspend")
def admin_suspend(
    user_id: str,
    admin: Dict[str, Any] = Depends(require_superadmin),
):
    set_user_suspended(user_id, True, admin_id=str(admin["id"]))
    return {"ok": True, "suspended": True}


@router.post("/users/{user_id}/unsuspend")
def admin_unsuspend(
    user_id: str,
    admin: Dict[str, Any] = Depends(require_superadmin),
):
    set_user_suspended(user_id, False, admin_id=str(admin["id"]))
    return {"ok": True, "suspended": False}


@router.post("/users/{user_id}/plan")
def admin_plan(
    user_id: str,
    body: PlanOverrideRequest,
    admin: Dict[str, Any] = Depends(require_superadmin),
):
    ok = set_user_plan(user_id, body.plan, admin_id=str(admin["id"]))
    return {"ok": ok, "plan": body.plan}


@router.get("/audit")
def admin_audit(
    limit: int = Query(100, le=500),
    user_id: Optional[str] = None,
    _admin: Dict[str, Any] = Depends(require_superadmin),
):
    return {"events": list_audit_events(limit=limit, user_id=user_id)}


@router.get("/usage")
def admin_usage(_admin: Dict[str, Any] = Depends(require_superadmin)):
    return get_usage_summary()


@router.get("/health")
def admin_health(_admin: Dict[str, Any] = Depends(require_superadmin)):
    return get_system_health()
