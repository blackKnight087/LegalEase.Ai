"""Stage-by-stage KB pipeline tracer — log success/failure at each step."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STAGES = (
    "query_received",
    "mode_selection",
    "scope_resolved",
    "retriever_invoked",
    "chunks_raw",
    "chunks_after_filter",
    "chunk_validation",
    "context_assembly",
    "prompt_construction",
    "llm_call",
)

_last_trace: Dict[str, Any] = {}


def bypass_retrieval_filters() -> bool:
    return os.getenv("KB_RETRIEVAL_BYPASS_FILTERS", "0").lower() in {"1", "true", "yes"}


def get_last_pipeline_trace() -> Dict[str, Any]:
    return dict(_last_trace)


class PipelineTracer:
    """Records each pipeline stage for the debug console."""

    def __init__(self, query: str = "") -> None:
        self.query = (query or "")[:500]
        self.stages: List[Dict[str, Any]] = []
        self._t0 = time.perf_counter()
        self.index_stats: Dict[str, Any] = {}
        self.rejection_log: List[Dict[str, Any]] = []

    def stage(
        self,
        name: str,
        *,
        ok: bool = True,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        elapsed_ms = round((time.perf_counter() - self._t0) * 1000, 1)
        entry = {
            "stage": name,
            "ok": bool(ok),
            "elapsed_ms": elapsed_ms,
            **(detail or {}),
        }
        self.stages.append(entry)
        if os.getenv("KB_PIPELINE_TRACE", "1").lower() in {"1", "true", "yes"}:
            status = "OK" if ok else "FAIL"
            logger.info(
                "[KB_PIPELINE] %s %s query=%r detail=%s",
                name,
                status,
                self.query[:80],
                {k: v for k, v in entry.items() if k not in ("stage", "ok")},
            )

    def log_rejection(
        self,
        chunk: Dict[str, Any],
        reason: str,
        *,
        score: float = 0.0,
    ) -> None:
        meta = chunk.get("metadata") or {}
        self.rejection_log.append(
            {
                "source": str(meta.get("filename") or meta.get("source_file") or ""),
                "score": round(float(score or 0), 4),
                "reason": reason,
                "excerpt": (chunk.get("content") or "")[:120],
            }
        )

    def set_index_stats(
        self,
        *,
        documents: int = 0,
        chunks: int = 0,
        vectors: int = 0,
        index_path: str = "",
        unlinked_documents: int = 0,
    ) -> None:
        self.index_stats = {
            "documents_indexed": documents,
            "chunks_indexed": chunks,
            "vectors_indexed": vectors,
            "index_path": index_path[:200],
            "unlinked_documents": unlinked_documents,
            "mismatch": vectors > 0 and chunks == 0,
        }

    def finalize(self) -> Dict[str, Any]:
        global _last_trace
        payload = {
            "query": self.query,
            "stages": self.stages,
            "index_stats": self.index_stats,
            "rejections": self.rejection_log[:20],
            "bypass_filters": bypass_retrieval_filters(),
        }
        _last_trace = payload
        return payload


def rescue_top_chunks(
    index_dir: Any,
    query: str,
    *,
    k: int = 5,
    scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Last-resort: return top-k vector hits with filters disabled."""
    try:
        from rag import query_kb

        hits = query_kb(
            query,
            k=k,
            index_dir=index_dir,
            document_scope=None,
        )
        if not hits:
            return []
        scope = scope or {}
        # global_kb: rescue uses full index — do not restrict to legacy unlinked allowlists
        if scope.get("unlinked_only") and not scope.get("allowed_filenames") and not scope.get(
            "allowed_doc_ids"
        ):
            return hits[:k]
        allowed = {n.lower() for n in (scope.get("allowed_filenames") or [])}
        allowed_ids = set(scope.get("allowed_doc_ids") or [])
        if allowed or allowed_ids:
            kept = []
            for h in hits:
                meta = h.get("metadata") or {}
                fn = str(meta.get("filename") or meta.get("source_file") or "").lower()
                did = str(meta.get("doc_id") or "")
                if allowed_ids and did in allowed_ids:
                    kept.append(h)
                elif allowed and fn in allowed:
                    kept.append(h)
            return kept[:k]
        return hits[:k]
    except Exception as exc:
        logger.debug("rescue_top_chunks failed: %s", exc)
        return []
