"""Merge scripts/.env.rotation.generated into .env (Postgres + secrets). No stdout secrets."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROTATION = ROOT / "scripts" / ".env.rotation.generated"
ENV = ROOT / ".env"

KEYS = (
    "JWT_SECRET",
    "LEGALEASE_API_SECRET",
    "POSTGRES_PASSWORD",
    "DATA_ENCRYPTION_KEY",
    "INTERNAL_CRON_SECRET",
    "SESSION_SIGNING_KEY",
)


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _localhost_db_url(bundle: dict[str, str]) -> str | None:
    raw = bundle.get("DATABASE_URL", "")
    if not raw.startswith("postgresql://"):
        return None
    return raw.replace("@postgres:", "@localhost:")


def _upsert(lines: list[str], key: str, value: str) -> list[str]:
    pat = re.compile(rf"^\s*{re.escape(key)}\s*=")
    replaced = False
    out: list[str] = []
    for line in lines:
        if pat.match(line):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def main() -> int:
    if not ROTATION.is_file():
        print("Missing scripts/.env.rotation.generated — run: py scripts/rotate_secrets.py")
        return 1
    if not ENV.is_file():
        print("Missing .env")
        return 1

    bundle = _parse(ROTATION)
    lines = ENV.read_text(encoding="utf-8").splitlines()

    for key in KEYS:
        if bundle.get(key):
            lines = _upsert(lines, key, bundle[key])

    db = _localhost_db_url(bundle)
    if db:
        lines = _upsert(lines, "DATABASE_URL", db)

    for flag, val in (
        ("SAAS_USE_POSTGRES_LEGACY", "1"),
        ("SAAS_AUTO_POSTGRES_LEGACY", "1"),
        ("SSO_DEV_MOCK", "0"),
    ):
        lines = _upsert(lines, flag, val)

    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Updated .env: Postgres URL (localhost), rotation secrets, SAAS_USE_POSTGRES_LEGACY=1, SSO_DEV_MOCK=0")
    print("If using docker compose only, set DATABASE_URL host to postgres instead of localhost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
