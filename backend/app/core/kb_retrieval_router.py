"""
Global KB vs Matter KB — strict index separation and retrieval routing.

Global KB  → faiss_indexes/user_*/global_kb  (statutes, constitution, case law, templates)
Matter KB  → faiss_indexes/user_*/matter_{id} (FIRs, evidence, witness statements, orders)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MATTER_AI_MODES = frozenset(
    {"matter_only", "chronology", "hearing_prep", "evidence", "hearing", "witness"}
)


def is_matter_ai_mode(matter_mode: Optional[str]) -> bool:
    return (matter_mode or "").strip().lower() in MATTER_AI_MODES


def resolve_global_kb_index_dir(user_id: str) -> Path:
    from backend.app.core.matter_index import get_global_kb_index_dir

    return get_global_kb_index_dir(user_id)


def resolve_matter_kb_index_dir(user_id: str, matter_id: str) -> Path:
    from backend.app.core.matter_index import get_matter_index_dir

    return get_matter_index_dir(user_id, matter_id)


def get_index_stats(user_id: str, index_dir: Path) -> Dict[str, Any]:
    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists

    vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
    docs = 0
    try:
        from backend.app.core.kb_doc_scope import list_index_documents

        docs = len(list_index_documents(index_dir))
    except Exception:
        pass
    return {
        "documents": docs,
        "chunks": vectors,
        "vectors": vectors,
        "index_path": str(index_dir),
        "index_exists": bool(index_exists(index_dir)),
        "ready": vectors > 0,
    }


def get_dual_kb_stats(
    user_id: str,
    matter_id: Optional[str] = None,
    *,
    matter_name: str = "",
) -> Dict[str, Any]:
    """Diagnostics for UI — Global KB + optional current matter."""
    from app import get_scoped_document_count

    global_dir = resolve_global_kb_index_dir(user_id)
    global_stats = get_index_stats(user_id, global_dir)
    global_stats["label"] = "Global KB"
    global_stats["scope"] = "global_kb"
    try:
        global_stats["documents"] = get_scoped_document_count(user_id, None)
    except Exception:
        pass

    out: Dict[str, Any] = {"global_kb": global_stats}
    mid = (matter_id or "").strip()
    if mid:
        matter_dir = resolve_matter_kb_index_dir(user_id, mid)
        matter_stats = get_index_stats(user_id, matter_dir)
        matter_stats["label"] = matter_name or f"Matter {mid[:8]}…"
        matter_stats["scope"] = f"matter:{mid}"
        matter_stats["matter_id"] = mid
        try:
            matter_stats["documents"] = get_scoped_document_count(user_id, mid)
        except Exception:
            pass
        out["current_matter"] = matter_stats
    return out


class GlobalKBRetriever:
    """Search only the global legal knowledge index — never matter indexes."""

    @staticmethod
    def index_dir(user_id: str) -> Path:
        return resolve_global_kb_index_dir(user_id)

    @staticmethod
    def retrieve(
        user_id: str,
        query: str,
        *,
        k: int = 10,
        document_scope: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        from rag import index_exists, query_kb

        index_dir = GlobalKBRetriever.index_dir(user_id)
        if not index_exists(index_dir):
            return []
        return query_kb(
            query,
            k=k,
            index_dir=index_dir,
            document_scope=document_scope,
        ) or []


class MatterRetriever:
    """Search only the active matter index — never global_kb."""

    @staticmethod
    def index_dir(user_id: str, matter_id: str) -> Path:
        return resolve_matter_kb_index_dir(user_id, matter_id)

    @staticmethod
    def retrieve(
        user_id: str,
        matter_id: str,
        query: str,
        *,
        k: int = 10,
        document_scope: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        from rag import index_exists, query_kb

        if not (matter_id or "").strip():
            return []
        index_dir = MatterRetriever.index_dir(user_id, matter_id)
        if not index_exists(index_dir):
            return []
        return query_kb(
            query,
            k=k,
            index_dir=index_dir,
            document_scope=document_scope,
        ) or []


def resolve_retrieval_index_dir(
    user_id: str,
    *,
    retrieval_scope: str = "global",
    matter_id: Optional[str] = None,
) -> Path:
    """
    retrieval_scope: 'global' | 'matter' | 'hybrid_primary_global'
    """
    scope = (retrieval_scope or "global").strip().lower()
    if scope == "matter":
        mid = (matter_id or "").strip()
        if not mid:
            raise ValueError("matter_id required for matter retrieval scope")
        return resolve_matter_kb_index_dir(user_id, mid)
    return resolve_global_kb_index_dir(user_id)


def hybrid_retrieve(
    user_id: str,
    query: str,
    matter_id: Optional[str],
    *,
    k_global: int = 6,
    k_matter: int = 6,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Hybrid mode — separate global and matter chunks (never merged at index level)."""
    global_chunks = GlobalKBRetriever.retrieve(user_id, query, k=k_global)
    matter_chunks: List[Dict[str, Any]] = []
    if (matter_id or "").strip():
        matter_chunks = MatterRetriever.retrieve(user_id, matter_id, query, k=k_matter)
    return global_chunks, matter_chunks
