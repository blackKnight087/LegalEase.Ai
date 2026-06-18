#!/usr/bin/env python3
"""Download smallest embedding model into Data/hf_cache (run before first backend start)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

cache = Path(os.getenv("LEGALEEASE_HF_CACHE", str(ROOT / "Data" / "hf_cache")))
cache.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(cache)
os.environ.pop("TRANSFORMERS_CACHE", None)
os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(cache / "sentence_transformers")
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

MODEL = (
    os.getenv("HF_EMBEDDING_MODEL", "").strip()
    or "sentence-transformers/paraphrase-MiniLM-L3-v2"
)
if os.getenv("LOW_RESOURCE_MODE", "1").lower() in {"1", "true", "yes"}:
    MODEL = "sentence-transformers/paraphrase-MiniLM-L3-v2"

print(f"Downloading embedding model to {cache} …")
print(f"Model: {MODEL}")

try:
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        MODEL,
        cache_dir=str(cache),
        local_files_only=False,
        local_dir_use_symlinks=False,
    )
    print("OK:", path)
    raise SystemExit(0)
except Exception as exc:
    print("Download failed:", exc)
    print("Indexing will retry on backend start; ensure network access to huggingface.co")
    raise SystemExit(1) from exc
