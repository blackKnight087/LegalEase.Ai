"""Validate production environment before serving traffic."""
from __future__ import annotations

import os
from typing import List

from backend.app.core.secret_rotation import (
    cors_looks_insecure_for_production,
    is_weak_password,
    is_weak_secret,
)


def local_dev_mode() -> bool:
    """Laptop dev (run_backend.ps1) — never treat as public production."""
    return os.getenv("LEGALEEASE_LOCAL_DEV", "0").lower() in {"1", "true", "yes"}


def production_mode() -> bool:
    if local_dev_mode():
        return False
    return os.getenv("SAAS_PRODUCTION", "0").lower() in {"1", "true", "yes"}


def validate_production_config() -> List[str]:
    """Return list of configuration errors (empty = OK)."""
    if not production_mode():
        return []
    errors: List[str] = []
    secret = os.getenv("LEGALEASE_API_SECRET") or os.getenv("JWT_SECRET") or ""
    if is_weak_secret(secret):
        errors.append("JWT_SECRET / LEGALEASE_API_SECRET must be set to a strong unique value")
    if len(secret) < 32:
        errors.append("JWT secret should be at least 32 characters")

    if is_weak_password(os.getenv("POSTGRES_PASSWORD")):
        errors.append("POSTGRES_PASSWORD must not use default placeholder in production")

    errors.extend(cors_looks_insecure_for_production(os.getenv("CORS_ORIGINS", "")))

    if os.getenv("CORS_ALLOW_LOCALHOST_REGEX", "0").lower() in {"1", "true", "yes"}:
        errors.append("CORS_ALLOW_LOCALHOST_REGEX must be disabled in production")

    if not os.getenv("REDIS_URL", "").strip():
        errors.append("REDIS_URL is recommended for multi-worker API in production")

    if not os.getenv("STRIPE_SECRET_KEY", "").strip():
        errors.append("STRIPE_SECRET_KEY is required in production (no mock billing)")
    elif not os.getenv("STRIPE_WEBHOOK_SECRET", "").strip():
        errors.append("STRIPE_WEBHOOK_SECRET required when STRIPE_SECRET_KEY is set")
    price_pro = os.getenv("STRIPE_PRICE_PRO", "").strip()
    price_lp = os.getenv("STRIPE_PRICE_LEGAL_PRO", "").strip()
    if os.getenv("STRIPE_SECRET_KEY", "").strip() and not (price_pro or price_lp):
        errors.append("STRIPE_PRICE_PRO and/or STRIPE_PRICE_LEGAL_PRO must be set")

    if os.getenv("ALLOW_MOCK_BILLING", "").lower() in {"1", "true", "yes"}:
        errors.append("ALLOW_MOCK_BILLING must be disabled in production")

    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url or "sqlite" in db_url.lower():
        errors.append("DATABASE_URL should point to Postgres in production (not SQLite)")

    if os.getenv("SAAS_USE_POSTGRES_LEGACY", "").lower() not in ("1", "true", "yes"):
        errors.append("SAAS_USE_POSTGRES_LEGACY=1 is required in production")

    if os.getenv("FORCE_HTTPS", "1").lower() not in ("1", "true", "yes"):
        errors.append("FORCE_HTTPS should remain enabled in production")

    if not (os.getenv("DATA_ENCRYPTION_KEY") or "").strip():
        errors.append("DATA_ENCRYPTION_KEY is required in production")

    if os.getenv("SECURITY_HEADERS_ENABLED", "1").lower() not in ("1", "true", "yes"):
        errors.append("SECURITY_HEADERS_ENABLED must stay enabled in production")

    if os.getenv("RATE_LIMIT_ENABLED", "1").lower() not in ("1", "true", "yes"):
        errors.append("RATE_LIMIT_ENABLED must stay enabled in production")

    email_provider = os.getenv("EMAIL_PROVIDER", "").strip().lower()
    if email_provider in ("brevo", "sendinblue") and not (
        os.getenv("BREVO_API_KEY", "").strip()
    ):
        errors.append("BREVO_API_KEY is required when EMAIL_PROVIDER=brevo")
    if email_provider == "smtp" and not (
        os.getenv("SMTP_HOST", "").strip() and os.getenv("SMTP_USER", "").strip()
    ):
        errors.append("SMTP_HOST and SMTP_USER are required when EMAIL_PROVIDER=smtp")

    fw = os.getenv("FIREWALL_ENABLED", "0").lower() in {"1", "true", "yes"}
    fw_ips = (os.getenv("FIREWALL_ALLOWED_IPS") or "").strip()
    if fw and not fw_ips:
        errors.append(
            "FIREWALL_ENABLED=1 requires FIREWALL_ALLOWED_IPS (comma-separated) or disable firewall"
        )

    public_url = (os.getenv("PUBLIC_APP_URL") or "").strip()
    if public_url.startswith("http://") and "localhost" not in public_url.lower():
        errors.append("PUBLIC_APP_URL should use HTTPS in production")

    return errors


def production_config_summary() -> dict:
    """Non-secret production readiness snapshot for /health."""
    from backend.app.core.crypto_vault import encryption_enabled

    return {
        "production_mode": production_mode(),
        "errors": validate_production_config(),
        "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY", "").strip()),
        "redis_configured": bool(os.getenv("REDIS_URL", "").strip()),
        "encryption_at_rest": encryption_enabled(),
        "security_headers": os.getenv("SECURITY_HEADERS_ENABLED", "1").lower()
        in {"1", "true", "yes"},
        "firewall_enabled": os.getenv("FIREWALL_ENABLED", "0").lower() in {"1", "true", "yes"},
        "firewall_allowlist_size": len(
            [p for p in (os.getenv("FIREWALL_ALLOWED_IPS") or "").split(",") if p.strip()]
        ),
        "cors_strict": production_mode()
        and os.getenv("CORS_ALLOW_LOCALHOST_REGEX", "0").lower()
        not in {"1", "true", "yes"},
        "mock_billing_allowed": not production_mode()
        and os.getenv("ALLOW_MOCK_BILLING", "1").lower() in {"1", "true", "yes"},
    }


def assert_production_config() -> None:
    errs = validate_production_config()
    if errs:
        raise RuntimeError("Production config invalid: " + "; ".join(errs))


def strict_production_startup() -> bool:
    """When true, invalid production config prevents API boot."""
    return production_mode() and os.getenv("SAAS_PRODUCTION_STRICT", "1").lower() in {
        "1",
        "true",
        "yes",
    }
