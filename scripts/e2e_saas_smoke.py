#!/usr/bin/env python3
"""API smoke test for SaaS stack (no browser). Day 9 minimum E2E."""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("E2E_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        import json

        return json.loads(resp.read().decode())


def main() -> int:
    checks = [
        ("/api/v1/health/live", "live"),
        ("/api/v1/health/public", "public"),
    ]
    failed = 0
    for path, label in checks:
        try:
            data = _get(path)
            print(f"OK {label}: {list(data.keys())[:6]}")
        except urllib.error.URLError as exc:
            print(f"FAIL {label}: {exc}")
            failed += 1
    if failed:
        print("Start API first: py -m uvicorn backend.app.main:app --port 8000")
        return 1
    print("SaaS API smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
