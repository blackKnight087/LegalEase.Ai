"""Enterprise SSO — OIDC/SAML readiness (Phase 6).

Production: configure OIDC issuer + client credentials.
Development: SSO_DEV_MOCK=1 allows email-based provisioning for pilot firms.
"""
from __future__ import annotations

import os
import secrets
import urllib.parse
from typing import Any, Dict, Optional

SSO_ENABLED = os.getenv("SSO_ENABLED", "0").lower() in {"1", "true", "yes"}
SSO_DEV_MOCK = os.getenv("SSO_DEV_MOCK", "0").lower() in {"1", "true", "yes"}
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "").strip().rstrip("/")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "").strip()
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "").strip()
OIDC_SCOPES = os.getenv("OIDC_SCOPES", "openid email profile").strip()
SAML_IDP_METADATA_URL = os.getenv("SAML_IDP_METADATA_URL", "").strip()

PUBLIC_APP_URL = (
    os.getenv("PUBLIC_APP_URL") or os.getenv("NEXT_PUBLIC_APP_URL") or "http://localhost:3000"
).rstrip("/")


def sso_status() -> Dict[str, Any]:
    oidc_ready = bool(OIDC_ISSUER and OIDC_CLIENT_ID and OIDC_REDIRECT_URI)
    saml_ready = bool(SAML_IDP_METADATA_URL)
    return {
        "enabled": SSO_ENABLED,
        "oidc_configured": oidc_ready,
        "saml_configured": saml_ready,
        "dev_mock": SSO_DEV_MOCK,
        "protocols": {
            "oidc": oidc_ready or SSO_DEV_MOCK,
            "saml": saml_ready,
        },
    }


def get_oidc_authorize_url(*, state: str = "") -> str:
    if not SSO_ENABLED:
        raise ValueError("SSO is not enabled")
    if not OIDC_ISSUER or not OIDC_CLIENT_ID:
        if SSO_DEV_MOCK:
            return f"{PUBLIC_APP_URL}/login?sso=dev_mock"
        raise ValueError("OIDC not configured")
    st = state or secrets.token_urlsafe(16)
    params = {
        "client_id": OIDC_CLIENT_ID,
        "response_type": "code",
        "scope": OIDC_SCOPES,
        "redirect_uri": OIDC_REDIRECT_URI,
        "state": st,
    }
    return f"{OIDC_ISSUER}/authorize?{urllib.parse.urlencode(params)}"


def provision_sso_user(
    *,
    email: str,
    display_name: str = "",
    external_id: str = "",
) -> Dict[str, Any]:
    """Find or create user from SSO identity; return user dict + token."""
    from auth_tokens import create_access_token
    from legalease_auth import create_user, get_user_by_username

    username = (email.split("@")[0] if email else external_id or "sso_user").strip().lower()
    username = username[:48] or f"user_{secrets.token_hex(4)}"
    user = get_user_by_username(username)
    if not user and email:
        user = get_user_by_username(email.strip().lower())
    if not user:
        password = secrets.token_urlsafe(24)
        user = create_user(username, password, membership="Pro")
        if not user:
            raise ValueError("Could not provision SSO user")
        from backend.app.core.org_service import create_org_for_user

        create_org_for_user(str(user["id"]), display_name or username, plan="Pro")
    token = create_access_token(str(user["id"]), user.get("username", username))
    return {"token": token, "user": user, "external_id": external_id}


def _exchange_oidc_code(code: str) -> Dict[str, Any]:
    """Token exchange + userinfo when SSO_DEV_MOCK=0."""
    import httpx

    token_url = f"{OIDC_ISSUER}/oauth/token"
    if not token_url.startswith("http"):
        token_url = f"{OIDC_ISSUER}/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": OIDC_REDIRECT_URI,
        "client_id": OIDC_CLIENT_ID,
        "client_secret": OIDC_CLIENT_SECRET,
    }
    with httpx.Client(timeout=30.0) as client:
        tok_resp = client.post(token_url, data=data)
        tok_resp.raise_for_status()
        tokens = tok_resp.json()
        access = tokens.get("access_token", "")
        if not access:
            raise ValueError("OIDC token response missing access_token")
        userinfo_url = tokens.get("userinfo_endpoint") or f"{OIDC_ISSUER}/userinfo"
        ui_resp = client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access}"},
        )
        ui_resp.raise_for_status()
        return ui_resp.json()


def handle_oidc_callback(
    *,
    code: str = "",
    state: str = "",
    email: str = "",
    name: str = "",
) -> Dict[str, Any]:
    """Exchange OIDC code for session. Dev mock accepts email directly."""
    if not SSO_ENABLED:
        raise ValueError("SSO disabled")
    if SSO_DEV_MOCK and email:
        return provision_sso_user(email=email, display_name=name, external_id=state)
    if not code:
        raise ValueError("Authorization code required")
    if not OIDC_CLIENT_SECRET:
        raise ValueError("OIDC client secret not configured — token exchange not available")
    if SSO_DEV_MOCK:
        raise ValueError("Use email provisioning when SSO_DEV_MOCK=1")
    profile = _exchange_oidc_code(code)
    user_email = (
        profile.get("email")
        or (profile.get("emails") or [{}])[0].get("value")
        or ""
    )
    display = profile.get("name") or profile.get("preferred_username") or name
    sub = str(profile.get("sub") or state or "")
    if not user_email:
        raise ValueError("OIDC userinfo did not include email")
    return provision_sso_user(
        email=str(user_email),
        display_name=str(display),
        external_id=sub,
    )
