"""Workspace dashboard API."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ....core.auth import get_current_user
from ....services.dashboard_service import get_dashboard_full

router = APIRouter(tags=["dashboard"])


@router.get("/full")
async def dashboard_full(user: Dict[str, Any] = Depends(get_current_user)):
    uid = str(user["id"])
    return await run_in_threadpool(
        get_dashboard_full,
        uid,
        username=str(user.get("username") or ""),
        membership=str(user.get("membership") or ""),
    )
