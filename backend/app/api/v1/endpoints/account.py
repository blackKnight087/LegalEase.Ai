"""Account GDPR, onboarding, password reset."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ....core.account_service import delete_user_account, export_user_data_zip
from ....core.auth import get_current_user
from ....core.onboarding_service import dismiss_onboarding, get_onboarding_state
from ....core.password_reset_service import request_password_reset, reset_password_with_token

router = APIRouter(tags=["account"])


class ForgotPasswordRequest(BaseModel):
    username: str = Field(..., min_length=3)


class ResetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)


class DeleteAccountRequest(BaseModel):
    confirm_username: str
    password: str


@router.get("/onboarding")
def onboarding_status(user: Dict[str, Any] = Depends(get_current_user)):
    return get_onboarding_state(
        str(user["id"]),
        str(user.get("membership") or "Free"),
    )


@router.post("/onboarding/dismiss")
def onboarding_dismiss(user: Dict[str, Any] = Depends(get_current_user)):
    dismiss_onboarding(str(user["id"]))
    return {"ok": True}


class LearnerModeBody(BaseModel):
    enabled: bool


@router.get("/preferences")
def account_preferences(user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.user_preferences import get_preference_profile, get_learner_mode

    data = get_preference_profile(user["id"])
    return {
        "profile": data.get("profile", {}),
        "learner_mode": get_learner_mode(user["id"]),
    }


@router.patch("/preferences/learner-mode")
def account_learner_mode(
    body: LearnerModeBody,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from ....core.user_preferences import set_learner_mode

    prof = set_learner_mode(user["id"], body.enabled)
    return {"ok": True, "learner_mode": prof.get("learner_mode", False)}


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10)


class SendVerifyEmailRequest(BaseModel):
    email: str = Field(..., min_length=3)


@router.post("/verify-email/send")
def send_verify(body: SendVerifyEmailRequest, user: Dict[str, Any] = Depends(get_current_user)):
    from ....core.email_verify_service import send_verification_email

    return send_verification_email(str(user["id"]), body.email.strip())


@router.post("/verify-email/confirm")
def confirm_verify(body: VerifyEmailRequest):
    from ....core.email_verify_service import verify_email_token

    out = verify_email_token(body.token.strip())
    if not out.get("ok"):
        raise HTTPException(400, out.get("error", "Invalid token"))
    return out


@router.get("/export")
def export_account(user: Dict[str, Any] = Depends(get_current_user)):
    try:
        from ....core.audit_service import log_audit

        log_audit("account.export", user_id=str(user["id"]))
    except Exception:
        pass
    data = export_user_data_zip(str(user["id"]), str(user.get("username") or "user"))
    username = str(user.get("username") or "user")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in username)[:40]
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="legalease-export-{safe}.zip"'
        },
    )


@router.delete("")
def delete_account(
    body: DeleteAccountRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from legalease_auth import authenticate_user

    if body.confirm_username.strip() != str(user.get("username") or ""):
        raise HTTPException(400, "Username confirmation does not match")
    if not authenticate_user(str(user.get("username") or ""), body.password):
        raise HTTPException(403, "Invalid password")
    try:
        return delete_user_account(str(user["id"]))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    request_password_reset(body.username.strip())
    return {"ok": True, "message": "If that account exists, a reset link was sent."}


@router.post("/reset-password/{token}")
def reset_password(token: str, body: ResetPasswordRequest):
    if body.password != body.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    try:
        reset_password_with_token(token, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "message": "Password updated. You can log in now."}
