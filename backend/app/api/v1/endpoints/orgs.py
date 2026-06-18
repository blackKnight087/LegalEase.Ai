"""Organization / firm tenancy API."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.org_service import (
    accept_invite,
    create_invite,
    get_invite_by_token,
    get_org,
    get_primary_org_id,
    list_org_members,
    list_pending_invites,
    revoke_invite,
)

router = APIRouter(tags=["organizations"])


class InviteRequest(BaseModel):
    email: str = Field(..., min_length=3)
    role: str = "member"


@router.get("/me")
def my_org(user: Dict[str, Any] = Depends(get_current_user)):
    org_id = get_primary_org_id(str(user["id"]))
    if not org_id:
        raise HTTPException(404, "No organization")
    org = get_org(org_id)
    members = list_org_members(org_id, str(user["id"]))
    return {"org": org, "members": members, "member_count": len(members)}


@router.get("/invites")
def pending_invites(user: Dict[str, Any] = Depends(get_current_user)):
    org_id = get_primary_org_id(str(user["id"]))
    if not org_id:
        raise HTTPException(404, "No organization")
    return {"invites": list_pending_invites(org_id, str(user["id"]))}


@router.post("/invite")
def invite_member(req: InviteRequest, user: Dict[str, Any] = Depends(get_current_user)):
    org_id = get_primary_org_id(str(user["id"]))
    if not org_id:
        raise HTTPException(404, "No organization")
    try:
        inv = create_invite(org_id, str(user["id"]), req.email, req.role)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "invite": inv}


@router.delete("/invites/{invite_id}")
def revoke_org_invite(invite_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    org_id = get_primary_org_id(str(user["id"]))
    if not org_id:
        raise HTTPException(404, "No organization")
    try:
        ok = revoke_invite(org_id, str(user["id"]), invite_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    if not ok:
        raise HTTPException(404, "Invite not found or already used")
    return {"ok": True}


@router.get("/invites/{token}")
def preview_invite(token: str):
    inv = get_invite_by_token(token)
    if not inv:
        raise HTTPException(404, "Invite not found")
    return {
        "org_name": inv.get("org_name"),
        "email": inv.get("email"),
        "role": inv.get("role"),
        "status": inv.get("status"),
        "expires_at": inv.get("expires_at"),
    }


@router.post("/invites/{token}/accept")
def accept_org_invite(token: str, user: Dict[str, Any] = Depends(get_current_user)):
    try:
        result = accept_invite(
            token,
            str(user["id"]),
            str(user.get("username") or user.get("email") or ""),
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result
