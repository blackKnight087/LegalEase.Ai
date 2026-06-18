"""Profile backend import chain — run: py scripts/profile_imports.py"""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy_saas"
for p in (str(ROOT), str(LEGACY)):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

STEPS = [
    "backend.app.core.gpu_runtime",
    "backend.app.api.v1.endpoints.health",
    "backend.app.api.v1.endpoints.chat",
    "backend.app.services.chat_service",
    "backend.app.api.v1.endpoints.documents",
    "backend.app.api.v1.endpoints.speech",
    "backend.app.api.v1.endpoints.engines",
    "backend.app.api.v1.endpoints.learning",
    "backend.app.api.v1.endpoints.collab",
    "backend.app.api.v1.endpoints.enterprise",
    "backend.app.api.v1.router",
    "backend.app.main",
]

def main() -> None:
    total = 0.0
    for mod in STEPS:
        t0 = time.time()
        try:
            importlib.import_module(mod)
            dt = time.time() - t0
            total += dt
            print(f"{dt:6.1f}s  OK  {mod}")
        except Exception as exc:
            dt = time.time() - t0
            print(f"{dt:6.1f}s  ERR {mod}: {exc}")
            break
    print(f"--- total {total:.1f}s ---")

if __name__ == "__main__":
    main()
