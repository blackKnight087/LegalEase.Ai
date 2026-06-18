"""Engine status, watchlist, and matter autopilot API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.engine_status import get_engine_status
from ....core.legal_watchlist import add_watch, check_watch, list_watches, remove_watch
from ....core.matter_autopilot import analyze_matter

router = APIRouter(tags=["engines"])


class WatchCreate(BaseModel):
    watch_type: str = Field(..., description="hearing | gazette | section | custom")
    label: str = Field(..., min_length=2)
    query: str = Field(..., min_length=4)
    matter_id: str = ""


@router.get("/status")
async def engines_status(
    matter_id: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    membership = str(user.get("membership") or "Free")
    uid = str(user["id"])

    def _build() -> Dict[str, Any]:
        status = get_engine_status(uid, matter_id or None, membership=membership)
        status["membership"] = membership
        try:
            from backend.app.core.gemini_usage import usage_summary

            status["usage"] = usage_summary(uid, membership)
        except Exception:
            pass
        return status

    return await run_in_threadpool(_build)


@router.get("/matters/{matter_id}/autopilot")
def matter_autopilot(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    return analyze_matter(str(user["id"]), matter_id)


@router.get("/watchlist")
def watchlist_list(
    matter_id: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    return {"items": list_watches(str(user["id"]), matter_id)}


@router.post("/watchlist")
def watchlist_add(body: WatchCreate, user: Dict[str, Any] = Depends(get_current_user)):
    return add_watch(
        str(user["id"]),
        watch_type=body.watch_type,
        label=body.label,
        query=body.query,
        matter_id=body.matter_id,
    )


@router.delete("/watchlist/{watch_id}")
def watchlist_remove(watch_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    return remove_watch(str(user["id"]), watch_id)


@router.post("/watchlist/{watch_id}/check")
def watchlist_check(watch_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    result = check_watch(str(user["id"]), watch_id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "check failed"))
    return result
