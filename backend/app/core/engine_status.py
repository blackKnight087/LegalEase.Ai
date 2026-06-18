"""Unified engine status for chat UI status bar."""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

_STATUS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_STATUS_CACHE_TTL = float(os.getenv("ENGINE_STATUS_CACHE_SEC", "12"))
_cache_lock = threading.Lock()


def get_engine_status(
    user_id: str = "",
    matter_id: Optional[str] = None,
    membership: str = "Free",
) -> Dict[str, Any]:
    cache_key = f"{user_id}:{matter_id or ''}:{membership}"
    now = time.monotonic()
    with _cache_lock:
        hit = _STATUS_CACHE.get(cache_key)
        if hit and (now - hit[0]) < _STATUS_CACHE_TTL:
            return dict(hit[1])

    gemini: Dict[str, Any] = {"ok": False, "label": "Web Intel off"}
    kb_gemini_enhance: Dict[str, Any] = {"enabled": False, "label": "KB retrieval local"}
    try:
        from backend.app.core.web_intelligence import gemini_configured, web_intel_status

        st = web_intel_status()
        configured = st.get("gemini_configured", False)
        gemini = {
            "ok": configured,
            "label": "Web Intel on" if configured else "No API key",
            "model": st.get("model"),
        }
        try:
            from backend.app.core.kb_gemini_safety import (
                GEMINI_KB_RERANK,
                GEMINI_KB_RETRIEVAL_HINTS,
                GEMINI_KB_SYNTHESIS,
                kb_gemini_enhancement_allowed,
            )

            if kb_gemini_enhancement_allowed():
                parts = []
                if GEMINI_KB_RETRIEVAL_HINTS:
                    parts.append("search hints")
                if GEMINI_KB_RERANK:
                    parts.append("rerank")
                kb_gemini_enhance = {
                    "enabled": True,
                    "label": "KB enhance: " + ", ".join(parts),
                    "synthesis_blocked": not GEMINI_KB_SYNTHESIS,
                }
            else:
                kb_gemini_enhance = {
                    "enabled": False,
                    "label": "KB answers: local only",
                    "synthesis_blocked": True,
                }
        except Exception:
            pass
    except Exception as exc:
        gemini = {"ok": False, "label": str(exc)[:40]}

    llm: Dict[str, Any] = {"ok": False, "label": "LLM offline"}
    try:
        from backend.app.core.llm_status import quick_llm_status

        st = quick_llm_status(timeout=2.0)
        online = bool(st.get("online") or st.get("available"))
        llm = {
            "ok": online,
            "label": (st.get("message") or "LLM")[:60],
            "backend": st.get("backend"),
            "model": st.get("model"),
        }
    except Exception as exc:
        llm = {"ok": False, "label": str(exc)[:40]}

    kb: Dict[str, Any] = {"ok": False, "label": "KB empty", "doc_count": 0, "vectors": 0}
    embeddings: Dict[str, Any] = {"ok": False, "label": "Embeddings loading"}
    try:
        from backend.app.core.document_db import get_scoped_document_count
        from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
        from backend.app.core.matter_index import resolve_rag_index_dir

        mid = (matter_id or "").strip()
        kb["doc_count"] = int(get_scoped_document_count(user_id, mid or None))
        idx = resolve_rag_index_dir(user_id, mid or None)
        vectors = count_index_vectors(idx) if index_exists(idx) else 0
        kb["vectors"] = vectors
        kb["ok"] = kb["doc_count"] > 0 and vectors > 0
        if kb["ok"]:
            kb["label"] = f"{kb['doc_count']} docs · {vectors} chunks"
        elif kb["doc_count"] > 0 and vectors == 0:
            kb["label"] = f"{kb['doc_count']} docs · re-index needed"
        elif kb["doc_count"]:
            kb["label"] = "No index"
        else:
            kb["label"] = "Upload documents"
        kb["matter_id"] = mid
    except Exception as exc:
        kb = {"ok": False, "label": str(exc)[:40], "doc_count": 0, "vectors": 0}

    try:
        from llms import ensure_embeddings_background, get_embeddings_status

        try:
            ensure_embeddings_background()
        except Exception:
            pass
        st = get_embeddings_status()
        ready = bool(st.get("ready"))
        embeddings = {
            "ok": ready,
            "label": "Embeddings ready" if ready else (st.get("error") or "Loading…")[:40],
            "model": (st.get("model") or "")[-40:],
        }
    except Exception as exc:
        embeddings = {"ok": False, "label": str(exc)[:36]}

    learning: Dict[str, Any] = {"ok": True, "label": "Adaptive on"}
    try:
        from backend.app.core.learning_engine import get_learning_engine_status

        ls = get_learning_engine_status(user_id)
        learning = {
            "ok": ls.get("enabled", True),
            "label": f"Memory {ls.get('answer_memory_count', 0)}",
            "neural_auto": (ls.get("neural_finetuning") or {}).get("auto_train"),
        }
    except Exception:
        pass

    usage: Dict[str, Any] = {}
    try:
        from backend.app.core.gemini_usage import usage_summary

        usage = usage_summary(user_id, membership)
    except Exception:
        pass

    payload = {
        "gemini": gemini,
        "kb_gemini_enhance": kb_gemini_enhance,
        "llm": llm,
        "kb": kb,
        "embeddings": embeddings,
        "learning": learning,
        "usage": usage,
        "strict_citations": os.getenv("STRICT_CITATIONS", "0").lower() in ("1", "true", "yes"),
        "legacy_web": os.getenv("LEGACY_WEB", "0").lower() in ("1", "true", "yes"),
    }
    with _cache_lock:
        _STATUS_CACHE[cache_key] = (now, dict(payload))
        if len(_STATUS_CACHE) > 128:
            for k in list(_STATUS_CACHE.keys())[:32]:
                _STATUS_CACHE.pop(k, None)
    return payload
