"""Fast FAISS index checks without importing rag.py or app.py."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Dict, Tuple, Union

INDEX_NAME = "index"
_VECTOR_CACHE_TTL = float(os.getenv("FAISS_VECTOR_COUNT_CACHE_SEC", "8"))
_vector_cache: Dict[str, Tuple[float, int]] = {}
_vector_cache_lock = threading.Lock()


def index_exists(index_dir: Union[str, Path]) -> bool:
    target = Path(index_dir)
    return (target / f"{INDEX_NAME}.faiss").exists() and (
        target / f"{INDEX_NAME}.pkl"
    ).exists()


def count_index_vectors(index_dir: Union[str, Path], *, use_cache: bool = True) -> int:
    """
    Return vector count for index.faiss. Cached briefly — avoids disk thrash when UI polls /kb/health.
    """
    faiss_path = Path(index_dir) / f"{INDEX_NAME}.faiss"
    if not faiss_path.exists():
        return 0
    key = str(faiss_path.resolve())
    mtime_ns = faiss_path.stat().st_mtime_ns
    cache_key = f"{key}:{mtime_ns}"
    if use_cache and _VECTOR_CACHE_TTL > 0:
        now = time.monotonic()
        with _vector_cache_lock:
            hit = _vector_cache.get(cache_key)
            if hit and (now - hit[0]) < _VECTOR_CACHE_TTL:
                return hit[1]
    try:
        import faiss

        idx = faiss.read_index(str(faiss_path))
        n = int(getattr(idx, "ntotal", 0) or 0)
    except Exception:
        n = 0
    if use_cache and _VECTOR_CACHE_TTL > 0:
        with _vector_cache_lock:
            _vector_cache[cache_key] = (time.monotonic(), n)
            if len(_vector_cache) > 64:
                oldest = sorted(_vector_cache.items(), key=lambda x: x[1][0])[:16]
                for k, _ in oldest:
                    _vector_cache.pop(k, None)
    return n
