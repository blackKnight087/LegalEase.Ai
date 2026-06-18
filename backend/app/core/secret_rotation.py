"""Secret generation and weak-value detection for production deploys."""
from __future__ import annotations

import re
import secrets
from typing import Dict, Iterable, List, Optional

# Placeholders that must never ship in production
_WEAK_EXACT = frozenset(
    {
        "",
        "change-me",
        "change-me-in-production",
        "change_this_jwt_secret_min_32_chars",
        "legalease-dev-change-in-production",
        "changeme",
        "change_this_strong_password",
        "your_gemini_key",
        "your_stripe_secret",
        "your_stripe_webhook_secret",
        "sk_test_placeholder",
        "whsec_placeholder",
    }
)

_WEAK_SUBSTRINGS = (
    "change_me",
    "change-me",
    "changeme",
    "placeholder",
    "example.com",
    "your_",
    "paste_",
    "xxx",
    "todo",
)

# Keys rotated locally via scripts/rotate_secrets.*
LOCAL_ROTATION_KEYS = (
    "JWT_SECRET",
    "LEGALEASE_API_SECRET",
    "POSTGRES_PASSWORD",
    "DATA_ENCRYPTION_KEY",
    "INTERNAL_CRON_SECRET",
    "SESSION_SIGNING_KEY",
)

# Keys that must be rotated in external provider dashboards
EXTERNAL_ROTATION_KEYS = (
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "BREVO_API_KEY",
    "SENDGRID_API_KEY",
    "SMTP_PASSWORD",
    "DOCUSIGN_ACCESS_TOKEN",
    "OIDC_CLIENT_SECRET",
    "SENTRY_DSN",
    "POSTHOG_API_KEY",
    "ECOURTS_API_KEY",
)


def is_weak_secret(value: Optional[str], *, min_length: int = 32) -> bool:
    """True if value is empty, a known placeholder, or too short for signing keys."""
    v = (value or "").strip()
    if not v:
        return True
    low = v.lower()
    if low in _WEAK_EXACT:
        return True
    if len(v) < min_length:
        return True
    for needle in _WEAK_SUBSTRINGS:
        if needle in low:
            return True
    if re.match(r"^CHANGE_ME", v, re.I):
        return True
    return False


def is_weak_password(value: Optional[str]) -> bool:
    v = (value or "").strip()
    if not v or v.lower() in _WEAK_EXACT:
        return True
    if len(v) < 16:
        return True
    return is_weak_secret(v, min_length=16)


def cors_looks_insecure_for_production(cors_origins: str) -> List[str]:
    """Return human-readable CORS problems for production."""
    issues: List[str] = []
    raw = (cors_origins or "").strip()
    if not raw:
        issues.append("CORS_ORIGINS must list your HTTPS app URL(s)")
        return issues
    for origin in (o.strip() for o in raw.split(",") if o.strip()):
        low = origin.lower()
        if "localhost" in low or "127.0.0.1" in low:
            issues.append("CORS_ORIGINS must not include localhost in production")
        if "trycloudflare.com" in low or "ngrok" in low:
            issues.append("CORS_ORIGINS must not include tunnel URLs in production")
        if origin.startswith("http://") and "127.0.0.1" not in low:
            issues.append(f"CORS origin should use HTTPS: {origin}")
    return issues


def generate_rotation_bundle() -> Dict[str, str]:
    """Generate new locally-managed secrets (does not touch provider API keys)."""
    from backend.app.core.crypto_vault import generate_encryption_key

    pg_pass = secrets.token_urlsafe(32)
    jwt = secrets.token_hex(32)
    return {
        "JWT_SECRET": jwt,
        "LEGALEASE_API_SECRET": secrets.token_hex(32),
        "POSTGRES_PASSWORD": pg_pass,
        "DATA_ENCRYPTION_KEY": generate_encryption_key(),
        "INTERNAL_CRON_SECRET": secrets.token_hex(24),
        "SESSION_SIGNING_KEY": secrets.token_hex(32),
        # Example DATABASE_URL — user must align user/host/db with deploy
        "DATABASE_URL": f"postgresql://legalease:{pg_pass}@postgres:5432/legalease",
    }


def rotation_checklist() -> Dict[str, Iterable[str]]:
    return {
        "local_env": LOCAL_ROTATION_KEYS,
        "provider_dashboards": EXTERNAL_ROTATION_KEYS,
    }


def validate_secrets_for_production() -> List[str]:
    """Aggregate secret/CORS validation errors for production boot."""
    import os

    errors: List[str] = []
    jwt = (os.getenv("JWT_SECRET") or os.getenv("LEGALEASE_API_SECRET") or "").strip()
    if is_weak_secret(jwt):
        errors.append("JWT_SECRET / LEGALEASE_API_SECRET must be rotated (32+ random chars)")

    if is_weak_password(os.getenv("POSTGRES_PASSWORD")):
        errors.append("POSTGRES_PASSWORD must be rotated (16+ chars, not a placeholder)")

    enc = (os.getenv("DATA_ENCRYPTION_KEY") or "").strip()
    if not enc:
        errors.append("DATA_ENCRYPTION_KEY is required in production (Fernet at-rest encryption)")
    elif len(enc) < 40:
        errors.append("DATA_ENCRYPTION_KEY looks invalid (use generate_encryption_key())")

    errors.extend(cors_looks_insecure_for_production(os.getenv("CORS_ORIGINS", "")))

    stripe = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if stripe and is_weak_secret(stripe, min_length=20):
        errors.append("STRIPE_SECRET_KEY must be a live key from Stripe dashboard (rotated)")

    gemini = (os.getenv("GEMINI_API_KEY") or "").strip()
    if gemini and is_weak_secret(gemini, min_length=20):
        errors.append("GEMINI_API_KEY must be rotated in Google AI Studio")

    return errors
