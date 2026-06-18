"""Firm Chat RBAC — free for all logged-in users."""
from __future__ import annotations

from typing import Any, Dict

# Firm Chat is included for every membership tier and org role.
_ALL_PERMS = {
    "view": True,
    "post": True,
    "dm": True,
    "create_channel": True,
    "upload": True,
    "mention": True,
    "create_task": True,
    "create_deadline": True,
    "summarize": True,
    "manage_members": True,
    "search_users": True,
    "send_chat_request": True,
}


def collab_permissions(user: Dict[str, Any]) -> Dict[str, bool]:
    del user  # same access for Free, Pro, viewer, associate, learner, solo, etc.
    perms = dict(_ALL_PERMS)
    perms["included_free"] = True
    return perms


def require_collab_perm(user: Dict[str, Any], perm: str) -> None:
    from fastapi import HTTPException

    if not collab_permissions(user).get(perm):
        raise HTTPException(403, f"Firm Chat permission denied: {perm}")
