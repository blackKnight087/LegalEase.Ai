"""Pinpoint which import step hangs — run: py scripts/profile_main_import.py"""
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
    ("dotenv", lambda: None),
    ("gpu_runtime.apply_gpu_profile", lambda: __import__("backend.app.core.gpu_runtime", fromlist=["apply_gpu_profile"]).apply_gpu_profile()),
    ("api_router", lambda: importlib.import_module("backend.app.api.v1.router")),
    ("admin_auth", lambda: importlib.import_module("backend.app.core.admin_auth")),
    ("auth", lambda: importlib.import_module("backend.app.core.auth")),
    ("config", lambda: importlib.import_module("backend.app.core.config")),
    ("FastAPI app shell", lambda: __import__("fastapi").FastAPI(title="t")),
    ("startup_state", lambda: importlib.import_module("backend.app.core.startup_state")),
    ("memory_guard", lambda: importlib.import_module("backend.app.middleware.memory_guard")),
    ("rate_limit", lambda: importlib.import_module("backend.app.middleware.rate_limit")),
    ("request_guard", lambda: importlib.import_module("backend.app.middleware.request_guard")),
    ("ip_firewall", lambda: importlib.import_module("backend.app.middleware.ip_firewall")),
    ("security_headers", lambda: importlib.import_module("backend.app.middleware.security_headers")),
    ("api_routes legacy", lambda: importlib.import_module("api_routes")),
    ("backend.app.main full", lambda: importlib.import_module("backend.app.main")),
]

def main() -> None:
    for label, fn in STEPS:
        t0 = time.time()
        print(f"  -> {label} ...", flush=True)
        try:
            fn()
            print(f"  OK {time.time()-t0:.1f}s {label}", flush=True)
        except Exception as exc:
            print(f"  ERR {time.time()-t0:.1f}s {label}: {exc}", flush=True)
            raise

if __name__ == "__main__":
    main()
