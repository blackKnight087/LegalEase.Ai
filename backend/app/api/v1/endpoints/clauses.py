"""Phase 1 — Clause library API."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.clause_repo import (
    adjust_clause_confidence,
    list_clauses,
    record_clause_edit_delta,
    upsert_clause,
)
from ....core.practice_schema import ensure_practice_schema, seed_default_clauses_if_empty

router = APIRouter(tags=["clauses"])


class ClauseCreate(BaseModel):
    clause_tag: str = Field(..., min_length=2)
    clause_text_content: str = Field(..., min_length=10)
    practice_area: str = "General"
    confidence_weight: float = 1.0


class ClauseFeedback(BaseModel):
    baseline: str = Field(..., min_length=10)
    accepted: str = Field(..., min_length=10)
    clause_tag: str = "CUSTOM_EDIT"
    practice_area: str = "Corporate"
    signal: int = Field(0, ge=-1, le=1)


@router.get("")
def clauses_list(
    practice_area: str = "",
    tag: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_practice_schema()
    seed_default_clauses_if_empty()
    return {"clauses": list_clauses(user["id"], practice_area=practice_area, tag=tag)}


@router.post("")
def clauses_create(
    body: ClauseCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_practice_schema()
    return upsert_clause(
        user["id"],
        clause_tag=body.clause_tag,
        clause_text_content=body.clause_text_content,
        practice_area=body.practice_area,
        confidence_weight=body.confidence_weight,
    )


@router.post("/feedback")
def clauses_feedback(
    body: ClauseFeedback,
    user: Dict[str, Any] = Depends(get_current_user),
):
    if body.signal > 0:
        adjust_clause_confidence(
            user["id"], body.clause_tag, delta=0.1, practice_area=body.practice_area
        )
        return {"recorded": True, "signal": "positive"}
    if body.signal < 0 or body.baseline != body.accepted:
        return record_clause_edit_delta(
            user["id"],
            baseline=body.baseline,
            accepted=body.accepted,
            practice_area=body.practice_area,
            clause_tag=body.clause_tag,
        )
    return {"recorded": False}
