"""Drafting Studio — smart draft wizard + templates (KB pipeline not used)."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.drafting_studio import (
    generate_smart_draft,
    get_smart_draft_questions,
    list_smart_draft_types,
)

router = APIRouter(tags=["drafting"])


class SmartDraftGenerate(BaseModel):
    draft_type: str
    answers: Dict[str, str] = Field(default_factory=dict)
    use_ai_polish: bool = False


@router.get("/smart-draft/types")
def smart_draft_types(user: Dict[str, Any] = Depends(get_current_user)):
    _ = user
    return {"types": list_smart_draft_types()}


@router.get("/smart-draft/{draft_type}/questions")
def smart_draft_questions(
    draft_type: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    _ = user
    out = get_smart_draft_questions(draft_type)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/smart-draft/generate")
def smart_draft_generate(
    body: SmartDraftGenerate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    out = generate_smart_draft(
        user["id"],
        body.draft_type,
        body.answers,
        use_ai_polish=body.use_ai_polish,
    )
    if out.get("error"):
        raise HTTPException(400, out["error"])
    return out
