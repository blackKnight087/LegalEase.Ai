"""
Adaptive efficiency under memory pressure — never hard-stop user work.

Lowers embed batch size, avoids duplicate subprocess models, and nudges GC between batches.
"""
from __future__ import annotations

import gc
import logging
import os
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger("legalease.memory")

# Thresholds for tuning only (not blocking)
_HIGH_PCT = float(os.getenv("LEGALEEASE_RAM_HIGH_PCT", "85"))
_PRESSURE_PCT = float(os.getenv("LEGALEEASE_RAM_PRESSURE_PCT", "90"))


def memory_snapshot() -> dict:
    try:
        from backend.app.core.resource_scheduler import memory_snapshot as _snap

        return _snap()
    except Exception:
        return {"percent": 0.0, "available_mb": 0}


def pressure_level() -> str:
    pct = float(memory_snapshot().get("percent") or 0)
    if pct >= _PRESSURE_PCT:
        return "critical"
    if pct >= _HIGH_PCT:
        return "high"
    if pct >= 75:
        return "medium"
    return "low"


def adaptive_index_embed_batch() -> int:
    """Smaller batches when RAM is tight — keeps indexing running without OOM."""
    base = int(os.getenv("RAG_INDEX_EMBED_BATCH", "32"))
    level = pressure_level()
    if level == "critical":
        return max(4, min(8, base))
    if level == "high":
        return max(8, min(16, base))
    if level == "medium":
        return max(12, min(24, base))
    return max(16, min(64, base))


def prefer_thread_indexing() -> bool:
    """Subprocess indexing duplicates the embedding model (~2× RAM) and often hangs on Windows."""
    import sys

    if sys.platform == "win32":
        return True
    if pressure_level() in ("high", "critical", "medium"):
        return True
    if os.getenv("INDEX_JOB_USE_PROCESS", "0").lower() not in ("1", "true", "yes"):
        return True
    return False


def maybe_collect_garbage(label: str = "") -> None:
    if pressure_level() in ("high", "critical"):
        gc.collect()
        if label:
            logger.debug("[MEMORY] gc.collect after %s (pressure=%s)", label, pressure_level())


@contextmanager
def efficient_indexing_mode() -> Iterator[dict]:
    """
    Temporarily tune env for one indexing run — always proceeds, never raises.
    """
    level = pressure_level()
    snap = memory_snapshot()
    batch = adaptive_index_embed_batch()
    prev_batch = os.environ.get("RAG_INDEX_EMBED_BATCH")
    os.environ["RAG_INDEX_EMBED_BATCH"] = str(batch)
    if level in ("high", "critical"):
        os.environ.setdefault("RAG_ENABLE_CROSS_ENCODER", "0")
        os.environ.setdefault("RAG_PREFER_BASE_EMBEDDINGS", "1")
    logger.info(
        "[MEMORY] Efficient indexing mode level=%s ram=%.0f%% batch=%s",
        level,
        float(snap.get("percent") or 0),
        batch,
    )
    try:
        yield {"level": level, "batch": batch, "memory": snap}
    finally:
        if prev_batch is None:
            os.environ.pop("RAG_INDEX_EMBED_BATCH", None)
        else:
            os.environ["RAG_INDEX_EMBED_BATCH"] = prev_batch
        maybe_collect_garbage("index_run")
