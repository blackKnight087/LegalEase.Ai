"""
Strict KB retrieval — exact section metadata first, BM25 second, vector last.

Never answer a statute question from a different section's chunks.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SECTION_QUERY_RE = re.compile(
    r"\b(?:ipc|bns|crpc|bnss|bsa|it\s*act)\s*(?:section\s*)?(\d{1,4}[a-z]?)|"
    r"\bsection\s+(\d{1,4}[a-z]?)\b",
    re.I,
)
_CODE_RE = re.compile(
    r"\b(ipc|bns|crpc|bnss|bsa|indian penal code|bharatiya nyaya)\b",
    re.I,
)


@dataclass
class StructuredLegalQuery:
    raw: str
    legal_code: str = "IPC"
    sections: List[str] = field(default_factory=list)
    is_statute_query: bool = False
    is_comparison: bool = False


def parse_structured_query(query: str) -> StructuredLegalQuery:
    q = (query or "").strip()
    out = StructuredLegalQuery(raw=q)
    if not q:
        return out

    secs: List[str] = []
    for m in _SECTION_QUERY_RE.finditer(q):
        sec = (m.group(1) or m.group(2) or "").lower()
        if sec and sec not in secs:
            secs.append(sec)

    if not secs:
        try:
            from conversation_context import extract_sections_from_text

            secs = extract_sections_from_text(q)
        except ImportError:
            pass

    if not secs:
        try:
            from backend.app.services.legal_query_parser import section_numbers_from_query

            secs = [s.lower() for s in section_numbers_from_query(q)]
        except ImportError:
            pass

    out.sections = secs[:6]
    cm = _CODE_RE.search(q)
    if cm:
        token = cm.group(1).lower()
        if "penal" in token or token == "ipc":
            out.legal_code = "IPC"
        elif "bns" in token or "nyaya" in token:
            out.legal_code = "BNS"
        elif "crpc" in token:
            out.legal_code = "CrPC"
        else:
            out.legal_code = token.upper()
    else:
        try:
            from conversation_context import extract_law_from_text

            law = extract_law_from_text(q)
            out.legal_code = (law or "ipc").upper()
            if out.legal_code == "INDIAN PENAL CODE":
                out.legal_code = "IPC"
        except ImportError:
            out.legal_code = "IPC"

    out.is_statute_query = bool(out.sections) and bool(
        re.search(r"\b(?:ipc|bns|crpc|section|punishment|penalty|explain|meaning)\b", q, re.I)
        or len(out.sections) >= 1
    )
    try:
        from kb_retrieval import is_comparison_query

        out.is_comparison = is_comparison_query(q) and len(out.sections) >= 2
    except ImportError:
        out.is_comparison = bool(
            re.search(r"\b(compare|difference|versus|vs\.?|between)\b", q, re.I)
            and len(out.sections) >= 2
        )
    return out


def _normalize_law(law: str) -> str:
    l = (law or "IPC").strip().upper()
    if l in ("INDIAN PENAL CODE", "IPC"):
        return "IPC"
    if l in ("BNS", "BHARATIYA NYAYA SANHITA"):
        return "BNS"
    return l or "IPC"


def validate_section_chunks(
    chunks: List[Dict[str, Any]],
    sections: List[str],
    law: str = "IPC",
) -> List[Dict[str, Any]]:
    """
    Drop chunks that do not match requested section(s).
    Isolate per-section text when a chunk mentions multiple sections.
    """
    if not sections or not chunks:
        return chunks

    from kb_preprocess import extract_section_content, filter_chunks_for_section
    from rag import _chunk_matches_strict_section

    law_u = _normalize_law(law)
    want = [s.lower() for s in sections if s]
    validated: List[Dict[str, Any]] = []

    for ch in chunks:
        body = ch.get("content") or ""
        meta = dict(ch.get("metadata") or {})
        primary = str(meta.get("primary_section") or "").lower()
        matched_sec = None

        for sec in want:
            if primary and primary != sec:
                continue
            if not _chunk_matches_strict_section(body, sec, law_u):
                continue
            meta_secs = {
                s.strip().lower()
                for s in (meta.get("section_numbers") or "").split(",")
                if s.strip()
            }
            if meta_secs and sec not in meta_secs and len(meta_secs) == 1:
                only = next(iter(meta_secs))
                if only != sec:
                    continue
            matched_sec = sec
            break

        if not matched_sec:
            continue

        isolated = extract_section_content(body, matched_sec) or body
        if not _chunk_matches_strict_section(isolated, matched_sec, law_u):
            continue

        out = dict(ch)
        out["content"] = isolated
        out["metadata"] = {**meta, "validated_section": matched_sec, "legal_code": law_u}
        out["entity"] = matched_sec
        out["retrieval_mode"] = ch.get("retrieval_mode") or "strict_section"
        validated.append(out)

    if validated:
        return filter_chunks_for_section(validated, want[0], law=law_u.lower())

    return filter_chunks_for_section(chunks, want[0], law=law_u.lower())


def bm25_section_search(
    index_dir: Any,
    section: str,
    law: str = "IPC",
    *,
    top_k: int = 8,
    scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Keyword/BM25-style lookup for exact section phrases."""
    law_u = _normalize_law(law)
    sec = (section or "").lower()
    if not sec or not index_dir:
        return []

    queries = [
        f"{law_u} Section {sec.upper()}",
        f"Section {sec.upper()} {law_u}",
        f"{law_u} Section {sec}",
    ]
    hits: List[Dict[str, Any]] = []
    seen: set = set()

    try:
        from rag import _load_docstore_only, _load_faiss_vectorstore, _get_langchain_embeddings
        from kb_legal_query_rewrite import keyword_fallback_from_vectorstore

        view = _load_docstore_only(Path(index_dir))
        if view:
            for q in queries:
                for h in keyword_fallback_from_vectorstore(view, q, top_k=top_k):
                    key = (h.get("content") or "")[:96]
                    if key in seen:
                        continue
                    seen.add(key)
                    h["retrieval_mode"] = "bm25_keyword"
                    hits.append(h)
        if len(hits) < top_k:
            vs = _load_faiss_vectorstore(Path(index_dir), _get_langchain_embeddings())
            if vs:
                for q in queries[:2]:
                    for h in keyword_fallback_from_vectorstore(vs, q, top_k=top_k):
                        key = (h.get("content") or "")[:96]
                        if key in seen:
                            continue
                        seen.add(key)
                        h["retrieval_mode"] = "bm25_keyword"
                        hits.append(h)
    except Exception as exc:
        logger.debug("bm25_section_search failed: %s", exc)

    if scope and scope.get("strict"):
        try:
            from backend.app.core.kb_doc_scope import filter_chunks_by_scope

            hits = filter_chunks_by_scope(hits, scope)
        except Exception:
            pass

    return validate_section_chunks(hits, [sec], law_u)[:top_k]


def strict_retrieve_statute_sections(
    index_dir: Any,
    *,
    query: str,
    sections: List[str],
    law: str = "IPC",
    scope: Optional[Dict[str, Any]] = None,
    top_k: int = 8,
    allow_vector_fallback: bool = False,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    """
    Exact metadata → BM25 → optional vector (disabled by default for statutes).

    Returns (chunks, mode, diagnostics).
    """
    diag: Dict[str, Any] = {
        "pipeline": "strict_statute",
        "requested_sections": list(sections),
        "legal_code": _normalize_law(law),
        "stages": [],
    }
    want = [s.lower() for s in sections if s]
    if not want or not index_dir:
        return [], "strict_no_sections", diag

    law_u = _normalize_law(law)
    merged: List[Dict[str, Any]] = []

    try:
        from rag import exact_section_lookup

        exact = exact_section_lookup(index_dir, want, law=law_u, top_k=top_k)
        if exact:
            diag["stages"].append("exact_metadata")
            merged.extend(exact)
    except Exception as exc:
        logger.debug("exact_section_lookup: %s", exc)

    if len(merged) < max(2, top_k // 2):
        for sec in want[:4]:
            kw = bm25_section_search(
                index_dir, sec, law_u, top_k=6, scope=scope
            )
            if kw:
                diag["stages"].append(f"bm25:{sec}")
                merged.extend(kw)

    validated = validate_section_chunks(merged, want, law_u)
    diag["stages"].append("validation")
    diag["pre_validation_count"] = len(merged)
    diag["post_validation_count"] = len(validated)

    if validated:
        diag["top_file"] = str((validated[0].get("metadata") or {}).get("filename", ""))[:80]
        diag["validated_section"] = want[0]
        return validated[:top_k], "strict_exact_bm25", diag

    if allow_vector_fallback:
        try:
            from backend.app.services.legal_orchestrator_v2 import _vector_search_last

            vec = _vector_search_last(
                index_dir,
                f"{law_u} Section {want[0].upper()} {query}",
                k=top_k,
                scope=scope,
                exclude_bns=law_u != "BNS",
            )
            validated = validate_section_chunks(vec, want, law_u)
            if validated:
                diag["stages"].append("vector_fallback_validated")
                return validated[:top_k], "strict_vector_fallback", diag
        except Exception:
            pass

    diag["stages"].append("not_found")
    return [], "section_not_in_kb", diag


def attach_retrieval_debug_footer(answer: str, chunks: List[Dict[str, Any]]) -> str:
    """Append retrieval provenance for debugging (Settings / dev)."""
    import os

    if os.getenv("KB_RETRIEVAL_DEBUG", "0").lower() not in {"1", "true", "yes"}:
        return answer
    if not chunks:
        return answer
    top = chunks[0]
    meta = top.get("metadata") or {}
    sec = meta.get("validated_section") or top.get("entity") or meta.get("primary_section") or ""
    code = meta.get("legal_code") or ""
    fn = meta.get("filename") or meta.get("source_file") or ""
    chunk_id = meta.get("chunk_id") or meta.get("chunk_index") or ""
    score = float(top.get("final_score") or top.get("hybrid_score") or 0.0)
    mode = top.get("retrieval_mode") or ""
    footer = (
        f"\n\n---\n**Retrieval debug:** "
        f"{code} Section {str(sec).upper()} | source: {fn} | chunk: {chunk_id} | "
        f"score: {score:.3f} | mode: {mode}"
    )
    if footer.strip() in (answer or ""):
        return answer
    return (answer or "").rstrip() + footer


def wants_detailed_section_answer(query: str) -> bool:
    """True when user expects a long-form statute explanation."""
    ql = (query or "").lower()
    return bool(
        re.search(
            r"\b(explain|explanation|detail|details|overview|ingredients?|elements?|"
            r"comprehensive|expand|elaborate|simple language|tell me more)\b",
            ql,
        )
    )


def apply_follow_up_scope_pin(
    scope: Dict[str, Any],
    *,
    query: str,
    session_id: Optional[str] = None,
    history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Pin retrieval to the same document/section as the prior turn on follow-ups."""
    try:
        from conversation_context import is_meta_follow_up

        if not is_meta_follow_up(query):
            return scope
    except ImportError:
        return scope

    out = dict(scope or {})
    pinned_fn = ""
    if session_id:
        try:
            from backend.app.core.conversation_memory import get_session_legal_memory

            mem = get_session_legal_memory(session_id)
            pinned_fn = str(mem.get("last_document") or mem.get("last_filename") or "")
            sec = mem.get("last_section")
            law = (mem.get("last_law") or "IPC").upper()
            if sec:
                out["section"] = str(sec).lower()
                out["legal_code"] = law
        except Exception:
            pass

    if not pinned_fn and history:
        try:
            from conversation_context import build_conversation_state

            state = build_conversation_state(history)
            pinned_fn = str(state.active_document or "")
        except Exception:
            pass

    if pinned_fn:
        out["filename"] = pinned_fn
        out["strict"] = True
        out["pinned_reason"] = "follow_up_document"
    return out


def enrich_query_sections_from_history(
    query: str,
    history: Optional[List[Dict]] = None,
    session_id: Optional[str] = None,
) -> str:
    """Expand vague follow-ups (e.g. 'Explanation') using history and session memory."""
    structured = parse_structured_query(query)
    if structured.sections:
        return query
    try:
        from conversation_context import enrich_query_with_context, is_meta_follow_up

        if history:
            expanded = enrich_query_with_context(query, history)
            if expanded and expanded.strip() != query.strip():
                return expanded.strip()
        if is_meta_follow_up(query) and history:
            expanded = enrich_query_with_context(query, history)
            if expanded and expanded.strip() != query.strip():
                return expanded.strip()
    except ImportError:
        pass
    if session_id:
        try:
            from conversation_context import is_meta_follow_up
            from backend.app.core.conversation_memory import get_session_legal_memory

            if is_meta_follow_up(query):
                mem = get_session_legal_memory(session_id)
                last_case = str(mem.get("last_case") or "").strip()
                if last_case:
                    ql = (query or "").lower()
                    if re.search(r"\bexplain\b", ql) or len((query or "").split()) <= 6:
                        return (
                            f"Explain the case {last_case} in detail using only the "
                            f"uploaded documents, including facts, parties, and court observations."
                        )
                    return f"{query} (regarding the case: {last_case})"
                sec = mem.get("last_section")
                law = (mem.get("last_law") or "IPC").upper()
                if sec:
                    ql = (query or "").lower()
                    if re.search(r"\bpunish", ql):
                        return (
                            f"What is the punishment under {law} Section "
                            f"{str(sec).upper()} in the uploaded documents?"
                        )
                    if wants_detailed_section_answer(query):
                        return (
                            f"Provide a comprehensive explanation of {law} Section "
                            f"{str(sec).upper()} from the uploaded documents, including "
                            f"overview, meaning, legal ingredients, punishment, and examples."
                        )
                    return (
                        f"Explain {law} Section {str(sec).upper()} in detail using "
                        f"only the uploaded documents."
                    )
        except Exception:
            pass
    return query
