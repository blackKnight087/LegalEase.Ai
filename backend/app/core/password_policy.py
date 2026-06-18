"""Password strength rules for SaaS accounts."""
from __future__ import annotations

import os
import re
from typing import List, Tuple


def _min_length() -> int:
    if os.getenv("SAAS_PRODUCTION", "0").lower() in ("1", "true", "yes"):
        return int(os.getenv("PASSWORD_MIN_LENGTH", "12"))
    return int(os.getenv("PASSWORD_MIN_LENGTH", "8"))


def validate_password(password: str) -> Tuple[bool, str]:
    """Return (ok, error_message)."""
    if not password:
        return False, "Password is required"
    min_len = _min_length()
    if len(password) < min_len:
        return False, f"Password must be at least {min_len} characters"
    if len(password) > 128:
        return False, "Password must be at most 128 characters"
    errors: List[str] = []
    if not re.search(r"[a-z]", password):
        errors.append("one lowercase letter")
    if not re.search(r"[A-Z]", password):
        errors.append("one uppercase letter")
    if not re.search(r"\d", password):
        errors.append("one digit")
    if not re.search(r"[^\w\s]", password):
        errors.append("one symbol")
    if errors:
        return False, "Password must include " + ", ".join(errors)
    return True, ""
