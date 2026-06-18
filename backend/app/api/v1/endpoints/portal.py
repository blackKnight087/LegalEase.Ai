"""Client portal — public read-only matter view."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.client_portal_service import (
    create_portal_access,
    get_client_portal_view,
    record_portal_client_upload,
    record_portal_signature,
)
from ....core.saas_schema import ensure_saas_schema

router = APIRouter(tags=["portal"])


class PortalCreate(BaseModel):
    matter_id: str
    client_email: str = Field(..., min_length=5)
    days_valid: int = Field(30, ge=1, le=365)


@router.post("/access")
def portal_create_access(
    body: PortalCreate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ensure_saas_schema()
    out = create_portal_access(
        user["id"],
        body.matter_id,
        body.client_email,
        days_valid=body.days_valid,
    )
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.get("/view/{token}")
def portal_view(token: str):
    """Public — no auth. Token is the secret."""
    ensure_saas_schema()
    out = get_client_portal_view(token)
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


class PortalSignBody(BaseModel):
    signer_name: str = ""
    intent: str = "acknowledge"


@router.post("/sign/{token}")
def portal_sign(token: str, body: PortalSignBody):
    """Public client e-sign stub — records signature intent on the matter."""
    out = record_portal_signature(
        token,
        signer_name=body.signer_name,
        intent=body.intent,
    )
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out


@router.post("/upload/{token}")
async def portal_upload(token: str, file: UploadFile = File(...)):
    """Public client upload — records matter note for lawyer review."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "File exceeds 25 MB limit.")
    out = record_portal_client_upload(
        token,
        file.filename or "document",
        size_bytes=len(data),
    )
    if out.get("error"):
        raise HTTPException(404, out["error"])
    return out
