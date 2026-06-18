"""Hard production startup guards when SAAS_PRODUCTION=1."""
from __future__ import annotations

import os
from typing import List

from backend.app.core.production_config import production_mode
from backend.app.core.secret_rotation import validate_secrets_for_production


def validate_production_guards() -> List[str]:
    """Return blocking errors for production boot. Empty = OK."""
    if not production_mode():
        return []

    errors: List[str] = list(validate_secrets_for_production())

    email_provider = os.getenv("EMAIL_PROVIDER", "console").strip().lower()
    if email_provider in ("", "console"):
        errors.append(
            "EMAIL_PROVIDER must not be 'console' in production (use brevo, smtp, or sendgrid)"
        )

    db_url = os.getenv("DATABASE_URL", "").strip().lower()
    if not db_url.startswith("postgresql"):
        errors.append("DATABASE_URL must be a PostgreSQL URL in production")

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        errors.append("REDIS_URL is required in production for queues and presence")

    if os.getenv("SSO_DEV_MOCK", "0").lower() in {"1", "true", "yes"}:
        errors.append("SSO_DEV_MOCK must be disabled in production")

    return errors


def assert_production_guards() -> None:
    errs = validate_production_guards()
    if errs:
        raise RuntimeError("Production guards failed: " + "; ".join(errs))


def guards_summary() -> dict:
    return {
        "production_mode": production_mode(),
        "errors": validate_production_guards(),
    }
