from __future__ import annotations

import asyncio
from time import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ....core.admin_auth import require_metrics_access
from ....core.auth import get_current_user
from ....core.production_config import production_mode
from ....core.llm_status import quick_llm_status
from ....core.startup_state import get_startup_snapshot
from ....models.response_models import HealthResponse

router = APIRouter(tags=["health"])

_LLM_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": {}}
_LLM_CACHE_TTL_SEC = 8.0


async def _cached_llm_status() -> Dict[str, Any]:
    now = time()
    if _LLM_CACHE["payload"] and (now - float(_LLM_CACHE["ts"])) < _LLM_CACHE_TTL_SEC:
        return dict(_LLM_CACHE["payload"])
    loop = asyncio.get_running_loop()
    payload = await loop.run_in_executor(None, lambda: quick_llm_status(timeout=2.5))
    _LLM_CACHE["ts"] = now
    _LLM_CACHE["payload"] = payload
    return dict(payload)


@router.get("/health/gpu")
async def health_gpu():
    """GPU / STT / embedding accelerator status (auth not required for local dev ops)."""
    from fastapi.concurrency import run_in_threadpool
    from ....core.gpu_runtime import get_runtime_accelerator_status

    return await run_in_threadpool(get_runtime_accelerator_status)


@router.get("/ping")
async def ping_alias():
    return await ping()


@router.get("/metrics")
async def metrics_public(user: Dict[str, Any] = Depends(require_metrics_access)):
    """Ops metrics (JSON). Superadmin-only when SAAS_PRODUCTION=1."""
    _ = user
    return _metrics_payload()


def _metrics_payload() -> Dict[str, Any]:
    import os

    out: Dict[str, Any] = {"service": "LegalEase API"}
    try:
        from backend.app.core.core_db import core_db_backend
        from backend.app.core.legacy_db import use_postgres_legacy
        from backend.app.core.ml_job_queue import ml_queue_available, should_use_ml_queue

        out["core_db"] = core_db_backend()
        out["postgres_legacy"] = use_postgres_legacy()
        out["redis"] = bool(os.getenv("REDIS_URL", "").strip())
        out["ml_queue"] = should_use_ml_queue()
        out["ml_queue_redis"] = ml_queue_available()
    except Exception as exc:
        out["error"] = str(exc)[:200]
    try:
        from backend.app.core.startup_state import get_startup_snapshot

        snap = get_startup_snapshot()
        out["embeddings_ok"] = bool(snap.get("embeddings_ok"))
    except Exception:
        pass
    return out


@router.get("/health/live")
async def ping():
    """Instant connectivity check — must not block on embeddings or indexing."""
    return {"status": "ok", "service": "LegalEase API", "live": True}


@router.get("/health/embeddings")
async def health_embeddings():
    """Embedding model status — never blocks on load."""
    from llms import ensure_embeddings_background, get_embeddings_status

    ensure_embeddings_background()
    st = get_embeddings_status()
    return {
        "ready": bool(st.get("ready")),
        "loading": bool(st.get("loading")),
        "model": st.get("model") or "",
        "device": st.get("device") or "cpu",
        "error": st.get("error") or "",
    }


@router.get("/health/llm")
async def health_llm():
    """Fast Ollama/LM Studio probe for sidebar status (cached, non-blocking)."""
    try:
        from backend.app.core.ollama_manager import ensure_ollama_background

        ensure_ollama_background()
    except Exception:
        pass
    gen = await _cached_llm_status()
    ready = bool(gen.get("online") or gen.get("available"))
    return {
        "llm_ready": ready,
        "llm_label": gen.get("message"),
        "backend": gen.get("backend"),
        "model": gen.get("model"),
        "architecture": gen.get("architecture"),
        "roles": gen.get("roles"),
    }





@router.get("/health/ready")
async def health_ready():
    """Readiness — uses startup snapshot; never blocks on warmup during indexing."""
    snap = get_startup_snapshot()
    emb_ready = bool(snap.get("embeddings_ok"))
    try:
        from llms import get_embeddings_status

        st = get_embeddings_status()
        if st.get("ready"):
            emb_ready = True
    except Exception:
        pass
    faiss_ok = False
    faiss_error = ""
    try:
        import faiss  # noqa: F401

        faiss_ok = True
    except Exception as exc:
        faiss_error = str(exc)
    gen = await _cached_llm_status()
    ready = emb_ready and faiss_ok
    matter_intel_error = str(snap.get("matter_intel_error") or "")
    return {
        "status": "ready" if ready else "degraded",
        "ready": ready,
        "embeddings_ok": emb_ready,
        "embeddings": snap,
        "faiss_ok": faiss_ok,
        "faiss_error": faiss_error,
        "matter_intel_ok": not matter_intel_error,
        "matter_intel_error": matter_intel_error,
        "llm_ready": bool(gen.get("online") or gen.get("available")),
        "llm_label": gen.get("message"),
    }





@router.get("/health/public")
async def health_public(request: Request):
    """
    Public health for login page — never calls warmup_embeddings (that blocked the API
    during document indexing and made the UI show backend disconnected / LLM offline).
    """
    import os

    gen = await _cached_llm_status()
    web: Dict[str, Any] = {}
    snap = get_startup_snapshot()
    embeddings_ready = bool(snap.get("embeddings_ok"))
    embeddings_label = (
        str(snap.get("embeddings_model") or "")
        or ("Embedding model loaded" if embeddings_ready else str(snap.get("embeddings_error") or "loading…"))
    )
    saas_ready = bool(getattr(request.app.state, "saas_practice_routes", False))
    try:
        from llms import web_search_status, get_embeddings_status

        web = web_search_status()
        st = get_embeddings_status()
        if st.get("ready"):
            embeddings_ready = True
            embeddings_label = str(st.get("model") or embeddings_label)
        elif not embeddings_ready and st.get("error"):
            embeddings_label = str(st.get("error") or embeddings_label)
    except Exception as exc:
        if not embeddings_ready:
            embeddings_label = f"Embeddings loading: {exc}"

    saas_config: Dict[str, Any] = {}
    try:
        from backend.app.core.production_config import production_config_summary

        saas_config = production_config_summary()
    except Exception:
        pass

    core_db: Dict[str, Any] = {}
    try:
        from backend.app.core.core_db import core_db_backend
        from backend.app.core.legacy_db import use_postgres_legacy
        from backend.app.core.pg_core_schema import postgres_core_ready

        core_db = {
            "backend": core_db_backend(),
            "postgres_legacy": use_postgres_legacy(),
            "postgres_core_ready": postgres_core_ready(),
        }
    except Exception:
        pass

    return {
        "status": "ok",
        "llm_ready": bool(gen.get("online") or gen.get("available")),
        "llm_label": gen.get("message"),
        "embeddings_ready": embeddings_ready,
        "embeddings_ok": embeddings_ready,
        "embeddings_label": embeddings_label,
        "web_search": web,
        "saas_practice_routes": saas_ready,
        "saas_production": saas_config,
        "core_db": core_db,
        "intake_public_enabled": os.getenv("INTAKE_PUBLIC_ENABLED", "0").lower()
        in {"1", "true", "yes"},
    }





@router.get("/health", response_model=HealthResponse)
async def health_check(user: Dict[str, Any] = Depends(get_current_user)):
    gen = await _cached_llm_status()

    indexed_docs = 0

    chunks = 0

    vector_ready = False

    try:

        from ....core.kb_observability import get_kb_observability



        kb = get_kb_observability(user["id"])

        indexed_docs = int(kb.get("documents", 0))

        chunks = int(kb.get("faiss_chunks_total") or kb.get("faiss_chunks") or 0)

        vector_ready = bool(kb.get("embeddings_ok")) and chunks > 0

    except Exception:

        try:

            from ....core.rag_engine import kb_health



            kb = kb_health(user["id"])

            indexed_docs = int(kb.get("indexed_docs", 0))

            chunks = int(kb.get("chunks", 0))

            vector_ready = bool(kb.get("vector_db_ready", False))

        except Exception:

            pass



    return HealthResponse(

        status="ok",

        llm_ready=bool(gen.get("online") or gen.get("available")),

        vector_db_ready=vector_ready,

        indexed_docs=indexed_docs,

        chunks=chunks,

        llm_label=gen.get("message"),

    )


