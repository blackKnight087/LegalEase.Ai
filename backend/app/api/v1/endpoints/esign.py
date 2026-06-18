"""E-signature API."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.esign_service import create_signing_request, get_signing_request, mark_signed
from ....core.saas_schema import ensure_saas_schema

router = APIRouter(tags=["esign"])


class SignRequestCreate(BaseModel):
    document_title: str = Field(..., min_length=2)
    document_body: str = Field(..., min_length=10)
    signer_name: str = Field(..., min_length=2)
    signer_email: str = Field(..., min_length=5)
    matter_id: str = ""


@router.post("/requests")
def esign_create(
    body: SignRequestCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    return create_signing_request(
        user["id"],
        document_title=body.document_title,
        document_body=body.document_body,
        signer_name=body.signer_name,
        signer_email=body.signer_email,
        matter_id=body.matter_id,
    )


@router.get("/requests/{request_id}")
def esign_get(
    request_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = get_signing_request(user["id"], request_id)
    if not out:
        raise HTTPException(404, "Signing request not found")
    return out


@router.post("/mock/{request_id}/complete")
def esign_mock_complete(request_id: str):
    """Dev-only mock completion (no auth)."""
    ensure_saas_schema()
    return mark_signed(request_id)
