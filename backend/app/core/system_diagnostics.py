"""
Deep system diagnostic — RAM, API, embeddings, index jobs, connection health.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]


def run_system_diagnostics(user_id: str = "") -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    fixes: List[str] = []

    mem: Dict[str, Any] = {"percent": 0.0, "available_mb": 0}
    sched: Dict[str, Any] = {}
    try:
        from backend.app.core.resource_scheduler import memory_snapshot, scheduler_status

        mem = memory_snapshot()
        sched = scheduler_status()
    except Exception as exc:
        sched = {"error": str(exc)[:120]}
        issues.append({"severity": "warning", "code": "SCHEDULER", "message": str(exc)[:200]})

    pct = float(mem.get("percent") or 0)
    if pct >= 90:
        issues.append({
            "severity": "warning",
            "code": "RAM_HIGH",
            "message": (
                f"RAM usage {pct:.0f}% — indexing uses smaller batches automatically "
                "(efficient mode)."
            ),
        })
        fixes.append("Close extra apps for faster indexing; work continues in efficient mode")
    elif pct >= 85:
        issues.append({
            "severity": "info",
            "code": "RAM_ELEVATED",
            "message": f"RAM usage {pct:.0f}% — embed batch size reduced automatically.",
        })

    emb: Dict[str, Any] = {}
    try:
        from backend.app.core.embedding_manager import get_manager

        emb = get_manager().get_status()
        if emb.get("state") in ("LOADING_MODEL", "RECOVERING", "FAILED"):
            issues.append({
                "severity": "warning" if emb.get("state") != "FAILED" else "error",
                "code": "EMBEDDINGS",
                "message": f"Embeddings: {emb.get('state')} — {emb.get('error', '')[:120]}",
            })
    except Exception as exc:
        emb = {"error": str(exc)[:120]}

    index_jobs: Dict[str, Any] = {"active": 0}
    try:
        from backend.app.core.index_jobs import list_active_jobs

        if user_id:
            active = list_active_jobs(user_id)
            index_jobs = {"active": len(active), "jobs": active[:5]}
            if active and pct >= 85:
                issues.append({
                    "severity": "warning",
                    "code": "INDEX_DURING_RAM_PRESSURE",
                    "message": f"{len(active)} index job(s) running while RAM is {pct:.0f}%.",
                })
                fixes.append("Wait for indexing to finish before heavy chat/uploads")
    except Exception:
        pass

    api_live = False
    try:
        import urllib.request

        with urllib.request.urlopen(
            "http://127.0.0.1:8000/api/v1/health/live", timeout=3
        ) as resp:
            api_live = resp.status == 200
    except Exception:
        issues.append({
            "severity": "error",
            "code": "API_DOWN",
            "message": "Backend not responding on port 8000.",
        })
        fixes.append("Run .\\run_backend.ps1 in a dedicated terminal")

    llm: Dict[str, Any] = {}
    try:
        from backend.app.core.llm_status import quick_llm_status

        llm = quick_llm_status(timeout=2.0)
        if not (llm.get("online") or llm.get("available")):
            issues.append({
                "severity": "warning",
                "code": "LLM_OFFLINE",
                "message": llm.get("message") or "Ollama/LM Studio not reachable",
            })
            fixes.append("Start Ollama app or LM Studio local server")
    except Exception as exc:
        llm = {"error": str(exc)[:80]}

    try:
        from backend.app.core.memory_efficiency import adaptive_index_embed_batch, prefer_thread_indexing

        batch_hint = adaptive_index_embed_batch()
        if not prefer_thread_indexing():
            issues.append({
                "severity": "info",
                "code": "INDEX_SUBPROCESS",
                "message": "Subprocess indexing enabled — uses more RAM; thread mode preferred when RAM is high.",
            })
    except Exception:
        batch_hint = int(os.getenv("RAG_INDEX_EMBED_BATCH", "16"))

    healthy = not any(i.get("severity") == "error" for i in issues) and api_live

    return {
        "healthy": healthy,
        "memory": mem,
        "scheduler": sched,
        "embeddings": emb,
        "index_jobs": index_jobs,
        "api_live": api_live,
        "llm": llm,
        "config": {
            "index_job_use_process": use_process,
            "rag_index_embed_batch": os.getenv("RAG_INDEX_EMBED_BATCH", "32"),
            "ram_pause_pct": os.getenv("LEGALEEASE_RAM_PAUSE_PCT", "85"),
        },
        "issues": issues,
        "recommended_fixes": fixes,
    }
