"""Phase 4 — Research query expansion & logging API."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.research_service import (
    expand_research_query,
    list_research_history,
    log_research_query,
    record_research_feedback,
)
from ....core.saas_schema import ensure_saas_schema

router = APIRouter(tags=["research"])


class ResearchExpand(BaseModel):
    query: str = Field(..., min_length=3)
    matter_id: str = ""


class ResearchLog(BaseModel):
    query: str = Field(..., min_length=3)
    selected_mode: str = "KNOWLEDGE_BASE"
    matter_id: str = ""
    retrieval_confidence: float = 0.0


class ResearchFeedback(BaseModel):
    query_id: str
    signal: int = Field(0, ge=-1, le=1)
    rephrased_query: str = ""


@router.post("/expand")
def research_expand(
    body: ResearchExpand,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return expand_research_query(body.query, user["id"])


@router.post("/log")
def research_log(
    body: ResearchLog,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return log_research_query(
        user["id"],
        body.query,
        selected_mode=body.selected_mode,
        matter_id=body.matter_id,
        retrieval_confidence=body.retrieval_confidence,
    )


@router.get("/history")
def research_history(
    limit: int = 50,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return {"queries": list_research_history(user["id"], limit=limit)}


@router.post("/feedback")
def research_feedback(
    body: ResearchFeedback,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return record_research_feedback(
        user["id"],
        body.query_id,
        body.signal,
        rephrased_query=body.rephrased_query,
    )
