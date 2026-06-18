"""Phase 1 — Document automation & clause library API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.clause_repo import create_template, get_template, list_templates, render_template
from ....core.practice_schema import ensure_practice_schema, seed_builtin_templates_if_empty

router = APIRouter(tags=["templates"])


class TemplateCreate(BaseModel):
    template_name: str = Field(..., min_length=2)
    practice_area: str = "General"
    raw_markdown_structure: str = Field(..., min_length=20)
    variable_json_map: Optional[List[str]] = None


class TemplateRender(BaseModel):
    variables: Dict[str, str] = Field(default_factory=dict)


@router.get("")
def templates_list(
    practice_area: str = "",
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_practice_schema()
    seed_builtin_templates_if_empty()
    return {"templates": list_templates(user["id"], practice_area=practice_area)}


@router.post("")
def templates_create(
    body: TemplateCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_practice_schema()
    return create_template(
        user["id"],
        template_name=body.template_name,
        practice_area=body.practice_area,
        raw_markdown_structure=body.raw_markdown_structure,
        variable_json_map=body.variable_json_map,
    )


@router.get("/{template_id}")
def templates_get(
    template_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    seed_builtin_templates_if_empty()
    tpl = get_template(user["id"], template_id)
    if not tpl:
        raise HTTPException(404, "Template not found")
    return tpl


@router.post("/{template_id}/generate")
def templates_generate(
    template_id: str,
    body: TemplateRender,
    user: Dict[str, Any] = Depends(get_current_user),
):
    out = render_template(user["id"], template_id, body.variables)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out

