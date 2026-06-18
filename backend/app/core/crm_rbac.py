"""CRM role-based permissions (org member roles)."""
from __future__ import annotations

from typing import Any, Dict

from backend.app.core.org_service import get_org_member_role, get_primary_org_id, is_org_owner
from backend.app.core.admin_auth import is_superadmin


def _role(user: Dict[str, Any]) -> str:
    if is_superadmin(user):
        return "owner"
    org_id = get_primary_org_id(str(user.get("id", "")))
    if not org_id:
        return "owner"
    r = get_org_member_role(str(user["id"]), org_id)
    if r == "owner":
        return "owner"
    if r in ("lawyer", "member"):
        return "associate"
    if r == "viewer":
        return "intern"
    return "associate"


def crm_permissions(user: Dict[str, Any]) -> Dict[str, bool]:
    role = _role(user)
    if role == "owner":
        return {
            "view": True,
            "create": True,
            "edit": True,
            "convert": True,
            "reject": True,
            "analytics": True,
            "assign": True,
            "notes_only": False,
        }
    if role == "associate":
        return {
            "view": True,
            "create": True,
            "edit": True,
            "convert": True,
            "reject": False,
            "analytics": True,
            "assign": False,
            "notes_only": False,
        }
    return {
        "view": True,
        "create": False,
        "edit": False,
        "convert": False,
        "reject": False,
        "analytics": False,
        "assign": False,
        "notes_only": True,
    }


def require_crm_perm(user: Dict[str, Any], perm: str) -> None:
    from fastapi import HTTPException

    perms = crm_permissions(user)
    if not perms.get(perm):
        raise HTTPException(403, f"CRM permission denied: {perm}")
