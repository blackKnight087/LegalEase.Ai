"""
Stable operation profile — smooth, efficient, safe (no hard stops).

- Safe: partial index progress saved; API stays reachable; graceful retries
- Efficient: adaptive embed batches + GC under RAM pressure
- Smooth: cached health checks; no false "offline" from one slow request
"""
from __future__ import annotations

from typing import Any, Dict


def operation_profile() -> Dict[str, Any]:
    """Single snapshot for UI / diagnostics — what mode the system is in."""
    mem: Dict[str, Any] = {}
    pressure = "low"
    mode = "normal"
    tips: list[str] = []

    try:
        from backend.app.core.memory_efficiency import (
            adaptive_index_embed_batch,
            memory_snapshot,
            pressure_level,
        )

        mem = memory_snapshot()
        pressure = pressure_level()
        batch = adaptive_index_embed_batch()
    except Exception:
        batch = 16

    pct = float(mem.get("percent") or 0)
    if pressure in ("high", "critical"):
        mode = "efficient"
        tips.append("Indexing uses smaller batches to stay stable — may take longer.")
    if pct >= 88:
        tips.append("Close unused browser tabs for smoother performance.")

    api_ok = False
    llm_ok = False
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health/live", timeout=2) as r:
            api_ok = r.status == 200
    except Exception:
        tips.append("Start backend: .\\run_backend.ps1")

    try:
        from backend.app.core.llm_status import quick_llm_status

        st = quick_llm_status(timeout=2.0)
        llm_ok = bool(st.get("online") or st.get("available"))
    except Exception:
        pass

    emb_ready = False
    try:
        from backend.app.core.embedding_manager import EmbeddingManager

        emb_ready = bool(EmbeddingManager.instance().get_status().get("ready"))
    except Exception:
        pass

    return {
        "mode": mode,
        "pressure": pressure,
        "memory_percent": pct,
        "embed_batch_size": batch,
        "api_ok": api_ok,
        "llm_ok": llm_ok,
        "embeddings_ready": emb_ready,
        "safe_to_index": api_ok and (emb_ready or pressure != "critical"),
        "tips": tips,
        "message": _mode_message(mode, api_ok, llm_ok, emb_ready),
    }


def _mode_message(mode: str, api_ok: bool, llm_ok: bool, emb_ready: bool) -> str:
    if not api_ok:
        return "Backend starting or unreachable — check run_backend.ps1"
    if not emb_ready:
        return "Loading knowledge base model… chat works; indexing starts when ready"
    if not llm_ok:
        return "API ready — start Ollama for AI answers"
    if mode == "efficient":
        return "Running efficiently under memory pressure — all features available"
    return "System ready"
