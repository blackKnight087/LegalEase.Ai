#!/usr/bin/env python3
"""Start Ollama on GPU before uvicorn (mirrors warm_embeddings_once.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

if os.getenv("LLM_BACKEND", "ollama").strip().lower() != "ollama":
    print("SKIP: LLM_BACKEND is not ollama")
    raise SystemExit(0)

from backend.app.core.ollama_manager import ensure_ollama_gpu, get_ollama_status, is_ollama_reachable

if is_ollama_reachable():
    print("OK: Ollama already running at", os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    if os.getenv("OLLAMA_AUTO_WARMUP", "1").lower() in {"1", "true", "yes"}:
        print("Warming legalease-tuned on GPU (may take 1-3 min)...")
        ok = ensure_ollama_gpu(wait=True)
    else:
        ok = True
else:
    print("Starting Ollama with GPU layers =", os.getenv("OLLAMA_NUM_GPU", "999"))
    ok = ensure_ollama_gpu(wait=True)

st = get_ollama_status()
if ok and (st.get("reachable") or is_ollama_reachable()):
    print("OK: Ollama ready — model", st.get("model"), "GPU layers", st.get("gpu_layers"))
    raise SystemExit(0)

print("WARN:", st.get("error") or "Ollama not ready — KB will retry in background")
raise SystemExit(0)
