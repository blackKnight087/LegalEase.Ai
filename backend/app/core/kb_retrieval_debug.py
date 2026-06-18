"""Retrieval debug console — observability for KB pipeline stages."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_last_debug: Dict[str, Any] = {}


def get_last_retrieval_debug() -> Dict[str, Any]:
    return dict(_last_debug)


def is_retrieval_hard_fail(text: str = "") -> bool:
    """True when orchestrator skipped LLM due to zero chunks — do not run recovery fallbacks."""
    tl = (text or "").lower()
    if any(
        m in tl
        for m in (
            "no relevant chunks found",
            "no unlinked documents are available",
        )
    ):
        return True
    dbg = _last_debug or {}
    pipe = dbg.get("pipeline") or {}
    if pipe.get("found_reason") == "hard_fail_zero_chunks":
        return True
    if int(dbg.get("chunk_count") or 0) == 0 and not dbg.get("context_passed_to_llm"):
        stages = (dbg.get("pipeline_trace") or {}).get("stages") or []
        for st in stages:
            if st.get("stage") == "llm_call" and st.get("skipped"):
                return True
    return False


def _chunk_summary(chunks: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, ch in enumerate(chunks[:limit]):
        meta = ch.get("metadata") or {}
        out.append(
            {
                "index": i + 1,
                "score": round(
                    float(
                        ch.get("final_score")
                        or ch.get("hybrid_score")
                        or ch.get("score")
                        or 0.0
                    ),
                    4,
                ),
                "source": str(meta.get("filename") or meta.get("source_file") or ""),
                "section": str(
                    meta.get("validated_section")
                    or meta.get("primary_section")
                    or meta.get("section")
                    or ""
                ),
                "excerpt": (ch.get("content") or "")[:180].replace("\n", " "),
            }
        )
    return out


def _stage_failures(report: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    if not report.get("expanded_query") and report.get("follow_up_detected"):
        failures.append("follow_up_not_expanded")
    if int(report.get("chunk_count") or 0) == 0:
        failures.append("no_chunks_retrieved")
    stages = (report.get("pipeline_trace") or {}).get("stages") or []
    for st in stages:
        if not st.get("ok"):
            failures.append(f"stage_failed:{st.get('stage')}")
    if not report.get("context_passed_to_llm"):
        failures.append("context_not_injected")
    if report.get("rag_enforcement_failed"):
        failures.append("rag_enforcement_failed")
    if report.get("linked_doc_leak"):
        failures.append("linked_matter_doc_in_kb")
    pipe = report.get("pipeline") or {}
    if pipe.get("potential_retrieval_failure"):
        failures.append("potential_retrieval_failure")
    return failures


def build_retrieval_debug_report(
    *,
    original_query: str,
    expanded_query: str = "",
    retrieval_mode: str = "KB",
    chunks: Optional[List[Dict[str, Any]]] = None,
    session_mem: Optional[Dict[str, Any]] = None,
    scope: Optional[Dict[str, Any]] = None,
    follow_up_detected: bool = False,
    memory_used: bool = False,
    context_passed_to_llm: bool = False,
    prompt_preview: str = "",
    prompt_token_estimate: int = 0,
    active_matter: str = "",
    index_dir: str = "",
    pipe_diag: Optional[Dict[str, Any]] = None,
    rag_enforcement_failed: bool = False,
    linked_doc_leak: bool = False,
    pipeline_trace: Optional[Dict[str, Any]] = None,
    index_stats: Optional[Dict[str, Any]] = None,
    rejections: Optional[List[Dict[str, Any]]] = None,
    retrieval_candidates: Optional[List[Dict[str, Any]]] = None,
    threshold_used: Optional[float] = None,
    top_score: Optional[float] = None,
) -> Dict[str, Any]:
    chunks = chunks or []
    mem = session_mem or {}
    report: Dict[str, Any] = {
        "original_query": (original_query or "")[:500],
        "expanded_query": (expanded_query or original_query or "")[:500],
        "retrieval_mode": retrieval_mode or "KB",
        "follow_up_detected": bool(follow_up_detected),
        "memory_used": bool(memory_used),
        "active_topic": mem.get("last_topic") or "",
        "active_section": mem.get("last_section") or "",
        "context_reset": bool(pipe_diag.get("context_reset")) if pipe_diag else False,
        "query_class": (pipe_diag or {}).get("query_class") or "",
        "active_document": mem.get("last_document") or mem.get("last_filename") or "",
        "active_entities": mem.get("last_entities") or [],
        "previous_query": mem.get("last_user_query") or "",
        "active_matter": active_matter or "",
        "index_dir": (index_dir or "")[:200],
        "document_scope": scope or {},
        "retrieved_chunks": _chunk_summary(chunks),
        "accepted_chunks": _chunk_summary(chunks),
        "retrieval_candidates": retrieval_candidates or [],
        "threshold_used": threshold_used,
        "top_score": top_score,
        "chunk_count": len(chunks),
        "context_passed_to_llm": bool(context_passed_to_llm),
        "prompt_preview": (prompt_preview or "")[:1200],
        "prompt_token_estimate": int(prompt_token_estimate or 0),
        "rag_enforcement_failed": bool(rag_enforcement_failed),
        "linked_doc_leak": bool(linked_doc_leak),
    }
    if pipeline_trace:
        report["pipeline_trace"] = pipeline_trace
    if index_stats:
        report["index_stats"] = index_stats
    if rejections:
        report["rejections"] = rejections
    if pipe_diag:
        report["pipeline"] = {
            k: pipe_diag[k]
            for k in (
                "query_class",
                "retrieval_mode",
                "found",
                "found_reason",
                "sections_requested",
                "validation",
            )
            if k in pipe_diag
        }
    report["stage_failures"] = _stage_failures(report)
    return report


def record_retrieval_debug(report: Dict[str, Any]) -> Dict[str, Any]:
    global _last_debug
    try:
        from llms import get_embeddings_status

        emb = get_embeddings_status()
        report["embedding_model"] = str(emb.get("model") or "")
        report["embedding_ready"] = bool(emb.get("ready"))
        report["embedding_dim"] = int(emb.get("dimension") or emb.get("dim") or 0)
    except Exception:
        pass
    _last_debug = dict(report)
    if os.getenv("KB_RETRIEVAL_DEBUG", "1").lower() in {"1", "true", "yes"}:
        logger.info(
            "QUERY: %s | EXPANDED: %s | CHUNK_COUNT: %s | MODE: %s",
            report.get("original_query", "")[:80],
            report.get("expanded_query", "")[:80],
            report.get("chunk_count", 0),
            report.get("retrieval_mode", ""),
        )
        for ch in report.get("retrieved_chunks") or []:
            logger.info(
                "RETRIEVED_CHUNK[%s] score=%s source=%s",
                ch.get("index"),
                ch.get("score"),
                ch.get("source"),
            )
        if report.get("embedding_model"):
            logger.info(
                "EMBED model=%s ready=%s dim=%s",
                report.get("embedding_model"),
                report.get("embedding_ready"),
                report.get("embedding_dim"),
            )
    return report
