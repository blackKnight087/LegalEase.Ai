"""Deduplicate .env and append a single hybrid production block (last wins for listed keys)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
MARKER = "# === HYBRID PRODUCTION (single source of truth) ==="

# Keys managed only in the production block (removed from earlier lines)
PRODUCTION_KEYS = frozenset(
    {
        "PUBLIC_APP_URL",
        "CORS_ORIGINS",
        "CORS_ALLOW_LOCALHOST_REGEX",
        "NEXT_PUBLIC_API_URL",
        "NEXT_PUBLIC_APP_URL",
        "DATABASE_URL",
        "REDIS_URL",
        "SAAS_USE_POSTGRES_LEGACY",
        "SAAS_AUTO_POSTGRES_LEGACY",
        "SAAS_PRODUCTION",
        "SAAS_PRODUCTION_STRICT",
        "ALLOW_MOCK_BILLING",
        "FORCE_HTTPS",
        "SECURITY_HEADERS_ENABLED",
        "FIREWALL_ENABLED",
        "FIREWALL_TRUST_PROXY",
        "EMAIL_PROVIDER",
        "LLM_BACKEND",
        "CLOUD_GEMINI_KB",
        "OLLAMA_AUTO_START",
        "ML_USE_QUEUE",
        "JWT_SECRET",
        "LEGALEASE_API_SECRET",
        "POSTGRES_PASSWORD",
        "DATA_ENCRYPTION_KEY",
        "INTERNAL_CRON_SECRET",
        "SESSION_SIGNING_KEY",
        "SSO_ENABLED",
        "SSO_DEV_MOCK",
        "INTAKE_PUBLIC_ENABLED",
        "INTAKE_ORG_USER_ID",
    }
)

PRODUCTION_BLOCK = """\
# === HYBRID PRODUCTION (single source of truth) ===
# API: run_backend.ps1 | Web: run_web_prod.ps1 | DB: docker compose up -d postgres redis

PUBLIC_APP_URL=https://legalease.duckdns.org
NEXT_PUBLIC_APP_URL=https://legalease.duckdns.org
NEXT_PUBLIC_API_URL=https://legalease.duckdns.org/api
CORS_ORIGINS=https://legalease.duckdns.org
CORS_ALLOW_LOCALHOST_REGEX=0

SAAS_PRODUCTION=1
SAAS_PRODUCTION_STRICT=1
SAAS_USE_POSTGRES_LEGACY=1
SAAS_AUTO_POSTGRES_LEGACY=1
ALLOW_MOCK_BILLING=0
FORCE_HTTPS=1
SECURITY_HEADERS_ENABLED=1
FIREWALL_ENABLED=0
FIREWALL_TRUST_PROXY=1

REDIS_URL=redis://127.0.0.1:6379/0
ML_USE_QUEUE=0

LLM_BACKEND=gemini
CLOUD_GEMINI_KB=1
OLLAMA_AUTO_START=0

EMAIL_PROVIDER=smtp

SSO_ENABLED=0
SSO_DEV_MOCK=0
"""


def _parse_existing(path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    if not path.is_file():
        return vals
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        vals[k.strip()] = v.strip()
    return vals


def main() -> int:
    if not ENV.is_file():
        print("No .env found")
        return 1

    existing = _parse_existing(ENV)
    lines = ENV.read_text(encoding="utf-8").splitlines()

    # Drop old production marker blocks and duplicate production keys above marker
    out: list[str] = []
    skip_marker_section = False
    key_pat = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")

    for line in lines:
        if line.strip() == MARKER:
            skip_marker_section = True
            continue
        if skip_marker_section:
            m = key_pat.match(line)
            if m and m.group(1) in PRODUCTION_KEYS:
                continue
            if line.strip() and not line.strip().startswith("#"):
                m2 = key_pat.match(line)
                if m2 and m2.group(1) in PRODUCTION_KEYS:
                    continue
            # End marker section at first non-production-key line that's not comment/empty
            if line.strip() and not line.strip().startswith("#"):
                m3 = key_pat.match(line)
                if m3 and m3.group(1) not in PRODUCTION_KEYS:
                    skip_marker_section = False
                    out.append(line)
            continue

        m = key_pat.match(line)
        if m and m.group(1) in PRODUCTION_KEYS:
            continue
        out.append(line)

    # Preserve secrets from prior tail if present
    tail_lines = [PRODUCTION_BLOCK.rstrip()]
    for key in (
        "JWT_SECRET",
        "LEGALEASE_API_SECRET",
        "POSTGRES_PASSWORD",
        "DATA_ENCRYPTION_KEY",
        "INTERNAL_CRON_SECRET",
        "SESSION_SIGNING_KEY",
        "DATABASE_URL",
    ):
        if existing.get(key):
            tail_lines.append(f"{key}={existing[key]}")

    # Comment out duplicate dev conflict block hint
    cleaned = "\n".join(out).rstrip() + "\n\n" + "\n".join(tail_lines) + "\n"
    ENV.write_text(cleaned, encoding="utf-8")
    print(f"Consolidated {ENV} — production keys deduplicated, block appended.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
