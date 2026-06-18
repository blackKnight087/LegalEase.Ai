"""Enterprise SSO endpoints."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ....core.sso_service import (
    get_oidc_authorize_url,
    handle_oidc_callback,
    sso_status,
)

router = APIRouter(tags=["sso"])


class SsoCallbackRequest(BaseModel):
    code: str = ""
    state: str = ""
    email: str = ""
    name: str = ""


@router.get("/status")
def sso_status_public():
    return sso_status()


@router.get("/login")
def sso_login_start():
    try:
        url = get_oidc_authorize_url()
    except ValueError as exc:
        raise HTTPException(501, str(exc)) from exc
    return {"authorize_url": url}


@router.post("/callback")
def sso_callback(body: SsoCallbackRequest):
    try:
        return handle_oidc_callback(
            code=body.code,
            state=body.state,
            email=body.email,
            name=body.name,
        )
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
