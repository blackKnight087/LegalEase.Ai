"""Legal Conversion API — IPC↔BNS only (official dataset)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.legal_conversion_engine import (
    convert_section,
    dataset_meta,
    search_mappings,
)

router = APIRouter(tags=["legal-conversion"])

VALID_PAIRS = ("ipc_bns", "crpc_bnss")
DEFAULT_PAIR = "ipc_bns"


class ConvertBody(BaseModel):
    pair: str = Field(DEFAULT_PAIR, description="ipc_bns")
    section: str
    direction: str = Field("forward", description="forward (old→new) or reverse (new→old)")
    matter_id: str = ""


@router.get("/meta")
def conversion_meta():
    return dataset_meta()


@router.get("/search")
def conversion_search(
    q: str = Query(..., min_length=1),
    pair: str = Query(DEFAULT_PAIR),
    limit: int = Query(25, ge=1, le=100),
):
    return search_mappings(pair, q, limit=limit)


@router.get("/convert")
def conversion_get(
    section: str = Query(...),
    pair: str = Query(DEFAULT_PAIR),
    direction: str = Query("forward"),
    user: Dict[str, Any] = Depends(get_current_user),
    matter_id: str = Query(""),
):
    if direction not in ("forward", "reverse"):
        direction = "forward"
    return convert_section(
        pair,
        section,
        direction=direction,
        user_id=user["id"],
        matter_id=matter_id,
    )


@router.post("/convert")
def conversion_post(
    body: ConvertBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    direction = body.direction if body.direction in ("forward", "reverse") else "forward"
    return convert_section(
        body.pair,
        body.section,
        direction=direction,
        user_id=user["id"],
        matter_id=body.matter_id,
    )
