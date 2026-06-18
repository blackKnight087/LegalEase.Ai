#!/usr/bin/env python3
"""Preload embedding model (run once with backend STOPPED for fastest load)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("RAG_PREFER_BASE_EMBEDDINGS", "1")
os.environ.setdefault("RAG_FAST_EMBED_LOAD", "1")

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from llms import get_embeddings_status, warmup_embeddings

print("Preloading embeddings (stop run_backend.ps1 first if load is very slow)...")
t0 = time.time()
ok = warmup_embeddings()
st = get_embeddings_status()
print("ok:", ok, "elapsed:", round(time.time() - t0, 1), "s")
print("status:", st)
raise SystemExit(0 if ok else 1)
