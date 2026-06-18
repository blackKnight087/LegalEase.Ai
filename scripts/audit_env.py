"""Compare .env vs .env.example — report missing production variables with severity."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Keys that must be set for production (value checks applied separately)
CRITICAL_KEYS = {
    "DATABASE_URL": lambda v: v.strip().lower().startswith("postgresql"),
    "SAAS_USE_POSTGRES_LEGACY": lambda v: v.strip() in ("1", "true", "yes"),
    "JWT_SECRET": lambda v: len(v.strip()) >= 32
    or len(os.getenv("LEGALEASE_API_SECRET", "")) >= 32,
    "REDIS_URL": lambda v: bool(v.strip()),
    "CORS_ORIGINS": lambda v: bool(v.strip()) and "localhost" not in v.lower(),
}

WARN_KEYS = {
    "STRIPE_SECRET_KEY": lambda v: bool(v.strip()),
    "STRIPE_WEBHOOK_SECRET": lambda v: bool(v.strip()),
    "EMAIL_PROVIDER": lambda v: v.strip().lower() not in ("", "console"),
    "BREVO_API_KEY": lambda v: bool(v.strip())
    or os.getenv("SENDGRID_API_KEY", "").strip()
    or os.getenv("EMAIL_PROVIDER", "").lower() in ("smtp",),
    "DATA_ENCRYPTION_KEY": lambda v: bool(v.strip()),
    "POSTHOG_API_KEY": lambda v: bool(v.strip())
    or bool(os.getenv("NEXT_PUBLIC_POSTHOG_KEY", "").strip()),
    "NEXT_PUBLIC_API_URL": lambda v: v.strip().startswith("https://"),
    "SAAS_PRODUCTION": lambda v: v.strip() in ("1", "true", "yes"),
}

OK_OPTIONAL = {
    "SENTRY_DSN",
    "OIDC_ISSUER",
    "OIDC_CLIENT_ID",
    "ECOURTS_API_ENABLED",
    "SSO_ENABLED",
}


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        env_path = ROOT / ".env"
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val


def _parse_example_keys() -> dict[str, str]:
    example = ROOT / ".env.example"
    if not example.is_file():
        return {}
    keys: dict[str, str] = {}
    for line in example.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        keys[key.strip()] = val.strip()
    return keys


def _severity_for_key(key: str, present: bool, valid: bool) -> str:
    if key in CRITICAL_KEYS:
        if present and valid:
            return "ok"
        return "critical"
    if key in WARN_KEYS:
        if present and valid:
            return "ok"
        return "warn"
    return "ok" if present else "ok"


def audit() -> int:
    _load_dotenv()
    example_keys = _parse_example_keys()
    if not example_keys:
        print("[FAIL] .env.example not found")
        return 1

    print("LegalEase environment audit\n")
    print(f"Compared against {len(example_keys)} keys in .env.example\n")

    critical_fail = 0
    warn_fail = 0
    missing_from_env: list[str] = []

    for key in sorted(example_keys):
        val = os.getenv(key, "")
        if not val and key not in os.environ:
            missing_from_env.append(key)

    for key, checker in CRITICAL_KEYS.items():
        val = os.getenv(key, "")
        ok = bool(val) and checker(val)
        sev = "ok" if ok else "critical"
        tag = sev.upper()
        detail = val[:40] + "…" if len(val) > 40 else (val or "(missing)")
        if not ok:
            critical_fail += 1
        print(f"[{tag}] {key} — {detail if ok else 'required for production'}")

    for key, checker in WARN_KEYS.items():
        val = os.getenv(key, "")
        ok = bool(val) and checker(val)
        sev = "ok" if ok else "warn"
        tag = sev.upper()
        if not ok:
            warn_fail += 1
        print(f"[{tag}] {key}")

    example_critical = [
        k
        for k in example_keys
        if k in ("DATABASE_URL", "JWT_SECRET", "REDIS_URL", "SAAS_PRODUCTION")
        and k not in os.environ
        and not os.getenv(k, "")
    ]
    if example_critical:
        print("\n[NOTE] Keys in .env.example but unset in environment:")
        for k in example_critical[:12]:
            print(f"  - {k}")
        if len(example_critical) > 12:
            print(f"  … and {len(example_critical) - 12} more")

    print(f"\nSummary: {critical_fail} critical, {warn_fail} warnings")
    print("See docs/GO_LIVE.md for remediation steps.\n")

    if critical_fail:
        return 1
    return 0


def main() -> int:
    try:
        return audit()
    except Exception as exc:
        print(f"[FAIL] audit crashed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
