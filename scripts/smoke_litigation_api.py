"""Smoke-test Litigation Desk API routes (source app, auth overridden)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy_saas"
for p in (str(ROOT), str(LEGACY)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient

from backend.app.core.auth import get_current_user
from backend.app.main import app

UID = "litigation-smoke-user"
SAMPLE = (
    "15-03-2025\nBefore Honble Justice Singh\n"
    "WP 99/2024 Sharma v State listed for admission\n"
)


def fake_user():
    return {"id": UID, "username": "smoke", "membership": "Pro", "role": "user"}


def main() -> int:
    app.dependency_overrides[get_current_user] = fake_user
    client = TestClient(app)
    checks: list[tuple[str, int, bool]] = []

    def run(name: str, method: str, path: str, **kwargs):
        r = getattr(client, method)(path, **kwargs)
        ok = r.status_code < 500
        checks.append((name, r.status_code, ok))
        return r

    run("court-day parse", "post", "/api/v1/practice/court-day/parse", json={"text": SAMPLE})
    run("court-day today", "get", "/api/v1/practice/court-day/today")
    run("evidence-desk GET", "get", "/api/v1/practice/evidence-desk")
    run("evidence-desk scan", "post", "/api/v1/practice/evidence-desk/scan?max_matters=1")
    run("hearing digest", "get", "/api/v1/matters/hearings/digest")
    r_study = run("study irac removed", "post", "/api/v1/study/irac", json={"question": "x"})

    app.dependency_overrides.clear()

    failed = 0
    for name, code, ok in checks:
        tag = "OK" if ok else "FAIL"
        print(f"{tag}: {name} -> {code}")
        if not ok:
            failed += 1

    if r_study.status_code != 404:
        print(f"WARN: study/irac should be 404, got {r_study.status_code}")
        failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
