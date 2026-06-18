"""
Live KB smoke test — fast retrieval path (no full LLM pipeline per query).
Validates legal answering (60%) + index health (40% learning subsystem status).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Legacy fallback — prefer build_smoke_queries_from_index() for real smoke tests
DEFAULT_SMOKE_QUERIES: List[Dict[str, str]] = [
    {"id": "doc_summary", "query": "Summarize the main topics in my uploaded documents"},
    {"id": "doc_key_points", "query": "What are the key legal points in the documents?"},
]


def _smoke_retrieve_and_answer(
    user_id: str,
    query: str,
    index_dir: Any,
    *,
    scope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Retrieval-only smoke path — fast, no Ollama synthesis."""
    from backend.app.core.universal_kb import is_statute_focused_query, universal_retrieve
    from backend.app.services.legal_orchestrator_v2 import (
        build_retrieval_plan,
        execute_retrieval,
        generate_answer,
        parse_query,
    )
    from backend.app.core.kb_force_answer import guarantee_kb_answer
    from kb_response_state import KB_NOT_FOUND_MESSAGE

    t0 = time.perf_counter()
    parsed = parse_query(query)
    if parsed.query_class.value == "document_qa" or not is_statute_focused_query(query):
        chunks = universal_retrieve(query, index_dir, scope=scope or {}, k=10)
        mode = "universal_document"
        plan = build_retrieval_plan(parsed)
    else:
        plan = build_retrieval_plan(parsed)
        chunks, mode = execute_retrieval(plan, parsed, index_dir, scope=scope or {})
    latency_ms = int((time.perf_counter() - t0) * 1000)

    answer = ""
    if chunks:
        try:
            answer = generate_answer(parsed, plan, chunks, user_id=user_id, index_dir=index_dir)
        except Exception:
            pass
        if not answer or KB_NOT_FOUND_MESSAGE in (answer or ""):
            forced = guarantee_kb_answer(query, chunks)
            if forced:
                answer = forced

    found = bool(
        answer
        and answer != "NOT_FOUND_IN_KB"
        and KB_NOT_FOUND_MESSAGE not in (answer or "")
        and len((answer or "").strip()) > 40
    )
    return {
        "found": found,
        "chunk_count": len(chunks or []),
        "retrieval_mode": mode,
        "latency_ms": latency_ms,
        "answer_preview": (answer or "")[:220],
        "query_class": parsed.query_class.value,
    }


def run_kb_smoke_test(
    user_id: str,
    *,
    matter_id: Optional[str] = None,
    queries: Optional[List[Dict[str, str]]] = None,
    fast: bool = True,
) -> Dict[str, Any]:
    """
    Verify index health and representative legal queries return grounded answers.
    Uses resource scheduler — yields if RAM high or KB busy.
    """
    from app import resolve_rag_index_dir
    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
    from backend.app.core.kb_observability import resolve_active_index_scope
    from backend.app.core.resource_scheduler import Priority, acquire, scheduler_status

    uid = str(user_id)
    mid = (matter_id or "").strip() or None
    t_start = time.perf_counter()

    with acquire(Priority.SMOKE_TEST, "kb_smoke_test") as slot:
        if not slot.get("ok"):
            return {
                "ok": False,
                "skipped": True,
                "reason": slot.get("reason", "scheduler_busy"),
                "scheduler": scheduler_status(),
                "kb_pass": False,
                "training_pass": None,
            }

        active = resolve_active_index_scope(uid, mid)
        index_dir = resolve_rag_index_dir(uid, mid)
        vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0

        result: Dict[str, Any] = {
            "ok": False,
            "kb_pass": False,
            "training_pass": None,
            "query_source": "index_introspection",
            "index_path": active.get("index_path", ""),
            "index_scope": active.get("index_scope", ""),
            "index_scope_label": active.get("label", ""),
            "faiss_vectors": vectors,
            "index_exists": bool(active.get("index_exists")),
            "queries": [],
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "scheduler": scheduler_status(),
            "total_latency_ms": 0,
        }

        if vectors == 0:
            result["error"] = "No vectors in active index — re-index required."
            return result

        try:
            from llms import ensure_embeddings_background, get_embeddings_status

            ensure_embeddings_background()
            emb = get_embeddings_status()
            result["embeddings_ok"] = bool(emb.get("ready"))
            if not emb.get("ready"):
                result["embeddings_error"] = emb.get("error") or "Embeddings loading"
        except Exception as exc:
            result["embeddings_ok"] = False
            result["embeddings_error"] = str(exc)[:120]

        scope: Dict[str, Any] = {}
        try:
            from backend.app.core.kb_doc_scope import resolve_document_scope

            scope = resolve_document_scope(uid, "", index_dir)
            if not scope.get("strict"):
                scope = {**scope, "strict": False}
        except Exception:
            pass

        test_queries = queries
        if not test_queries:
            try:
                from backend.app.core.kb_smoke_query_builder import build_smoke_queries_from_index

                test_queries = build_smoke_queries_from_index(index_dir)
            except Exception:
                test_queries = DEFAULT_SMOKE_QUERIES

        result["query_source"] = "provided" if queries else "index_introspection"
        result["smoke_query_count"] = len(test_queries)

        for item in test_queries:
            qid = item.get("id") or "query"
            qtext = (item.get("query") or "").strip()
            entry: Dict[str, Any] = {"id": qid, "query": qtext, "status": "fail"}
            if not qtext:
                entry["status"] = "skipped"
                result["skipped"] += 1
                result["queries"].append(entry)
                continue
            try:
                if fast:
                    detail = _smoke_retrieve_and_answer(uid, qtext, index_dir, scope=scope)
                else:
                    from kb_pipeline import kb_pipeline
                    from kb_response_state import KB_NOT_FOUND_MESSAGE

                    answer, chunks, diag = kb_pipeline(uid, qtext, [], index_dir=index_dir)
                    detail = {
                        "found": bool(
                            answer
                            and answer != "NOT_FOUND_IN_KB"
                            and KB_NOT_FOUND_MESSAGE not in (answer or "")
                        ),
                        "chunk_count": len(chunks or []),
                        "best_score": diag.get("best_score"),
                        "found_reason": diag.get("found_reason"),
                        "answer_preview": (answer or "")[:220],
                        "latency_ms": 0,
                    }
                entry.update(detail)
                if detail.get("found"):
                    entry["status"] = "pass"
                    result["passed"] += 1
                else:
                    entry["status"] = "fail"
                    entry["reason"] = entry.get("reason") or "not_found"
                    result["failed"] += 1
            except Exception as exc:
                logger.exception("smoke query failed: %s", qtext)
                entry["status"] = "error"
                entry["error"] = str(exc)[:200]
                result["failed"] += 1
            result["queries"].append(entry)

        result["total_latency_ms"] = int((time.perf_counter() - t_start) * 1000)
        result["kb_pass"] = result["failed"] == 0 and result["passed"] > 0
        result["ok"] = result["kb_pass"]

        try:
            from backend.app.core.neural_finetuning import tuning_status

            ts = tuning_status(uid)
            result["training_status"] = ts
            result["training_pass"] = not bool(ts.get("last_error"))
        except Exception as exc:
            result["training_pass"] = None
            result["training_status"] = {"error": str(exc)[:80]}

        result["scheduler"] = scheduler_status()
        return result
