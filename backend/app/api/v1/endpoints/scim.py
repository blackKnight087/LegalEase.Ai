"""SCIM 2.0 stub — enterprise directory preview (requires IdP partnership)."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["scim"])


class ScimUser(BaseModel):
    userName: str = Field(..., min_length=2)
    displayName: str = ""
    emails: List[Dict[str, str]] = Field(default_factory=list)
    active: bool = True


@router.get("/Users")
def scim_list_users() -> Dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": 0,
        "Resources": [],
        "note": "SCIM preview — configure enterprise IdP partnership for live provisioning.",
    }


@router.post("/Users")
def scim_create_user(body: ScimUser) -> Dict[str, Any]:
    raise HTTPException(
        501,
        detail={
            "message": "SCIM user provisioning is a preview stub.",
            "userName": body.userName,
            "hint": "Use SSO OIDC flow or scripts/onboard_pilot_firm.py for pilot firms.",
        },
    )
