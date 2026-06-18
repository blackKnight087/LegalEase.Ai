"""Per-user court sync preferences and optional eCourtsIndia API key."""
from __future__ import annotations

from typing import Any, Dict

from backend.app.core.ecourtsindia_client import mask_api_key
from backend.app.core.user_preferences import get_preference_profile, save_preference_profile


def _integrations(profile: Dict[str, Any]) -> Dict[str, Any]:
    raw = profile.get("integrations")
    return dict(raw) if isinstance(raw, dict) else {}


def get_court_sync_settings(user_id: str) -> Dict[str, Any]:
    import os

    profile = get_preference_profile(user_id)
    integrations = _integrations(profile)
    user_key = str(integrations.get("ecourtsindia_api_key") or "").strip()
    env_key = os.getenv("ECOURTSINDIA_API_KEY", "").strip()
    effective = user_key or env_key
    return {
        "preferred_mode": str(profile.get("court_sync_mode") or "paste"),
        "api_configured": bool(effective),
        "api_key_masked": mask_api_key(user_key) if user_key else (mask_api_key(env_key) if env_key else ""),
        "api_key_source": "user" if user_key else ("env" if env_key else ""),
        "save_user_key": bool(user_key),
    }


def save_court_sync_settings(
    user_id: str,
    *,
    preferred_mode: str = "",
    api_key: str | None = None,
    clear_api_key: bool = False,
) -> Dict[str, Any]:
    profile = get_preference_profile(user_id)
    if preferred_mode in {"paste", "ecourtsindia"}:
        profile["court_sync_mode"] = preferred_mode
    integrations = _integrations(profile)
    if clear_api_key:
        integrations.pop("ecourtsindia_api_key", None)
    elif api_key is not None and api_key.strip():
        integrations["ecourtsindia_api_key"] = api_key.strip()
    if integrations:
        profile["integrations"] = integrations
    elif "integrations" in profile:
        profile.pop("integrations", None)
    save_preference_profile(user_id, profile)
    return get_court_sync_settings(user_id)


def resolve_ecourtsindia_api_key(user_id: str, override: str = "") -> str:
    import os

    key = (override or "").strip()
    if key:
        return key
    profile = get_preference_profile(user_id)
    integrations = _integrations(profile)
    user_key = str(integrations.get("ecourtsindia_api_key") or "").strip()
    if user_key:
        return user_key
    return os.getenv("ECOURTSINDIA_API_KEY", "").strip()
