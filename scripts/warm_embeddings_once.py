#!/usr/bin/env python3
"""Load embedding model before uvicorn starts so KB indexing works immediately."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

cache = Path(os.getenv("LEGALEEASE_HF_CACHE", str(ROOT / "Data" / "hf_cache")))
cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("LOW_RESOURCE_MODE", "1")
os.environ.setdefault("HF_HOME", str(cache))
os.environ.setdefault("LEGALEEASE_HF_CACHE", str(cache))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault(
    "HF_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-MiniLM-L3-v2",
)
os.environ.setdefault("EMBEDDING_MODEL_LOAD_TIMEOUT_SEC", "240")

from backend.app.core.embedding_manager import get_manager

print("Warming embeddings (CPU; first load may take 1-3 min)...")
mgr = get_manager()
mgr.start_background_load()
deadline = time.time() + float(os.getenv("EMBEDDING_MODEL_LOAD_TIMEOUT_SEC", "240")) + 30
while time.time() < deadline:
    st = mgr.get_status()
    state = st.get("state", "")
    if st.get("ready"):
        print("OK: model", st.get("model"), "state", state)
        raise SystemExit(0)
    if state == "FAILED" and st.get("error"):
        err = str(st.get("error") or "")
        if "retry" not in err.lower():
            print("FAILED:", err[:500])
            raise SystemExit(1)
    time.sleep(2)

st = mgr.get_status()
print("TIMEOUT:", st)
raise SystemExit(1)
