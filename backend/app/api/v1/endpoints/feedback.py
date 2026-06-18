"""Feedback learning review queue API."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ....core.admin_auth import require_superadmin
from ....core.auth import get_current_user
from ....core.feedback_learning import (
    ensure_feedback_learning_schema,
    list_review_queue,
    review_item,
)

router = APIRouter(tags=["feedback-learning"])


class ReviewAction(BaseModel):
    action: str = Field(..., description="approve | reject")
    notes: str = ""


@router.get("/queue")
def feedback_queue_list(
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(require_superadmin),
):
    _ = user
    ensure_feedback_learning_schema()
    return {"items": list_review_queue(status=status, limit=limit)}


@router.get("/queue/mine")
def feedback_queue_mine(
    status: str = Query("pending"),
    limit: int = Query(20, ge=1, le=100),
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_feedback_learning_schema()
    return {
        "items": list_review_queue(
            status=status, limit=limit, user_id=str(user["id"])
        )
    }


@router.post("/queue/{queue_id}/review")
def feedback_queue_review(
    queue_id: str,
    body: ReviewAction,
    user: Dict[str, Any] = Depends(require_superadmin),
):
    out = review_item(
        queue_id,
        str(user["id"]),
        action=body.action,
        notes=body.notes,
    )
    if not out.get("ok"):
        raise HTTPException(404, out.get("error", "not found"))
    return out
