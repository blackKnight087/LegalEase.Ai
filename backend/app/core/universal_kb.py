"""
Universal Knowledge Base — any document type, any length, any legal topic.

Statute queries (IPC/BNS section N) use exact-section path.
Everything else uses hybrid retrieval + grounded synthesis from uploaded PDFs.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_STATUTE_RE = re.compile(
    r"\b(?:ipc|bns|crpc|bnss|bsa)\s*(?:section\s*)?\d{1,4}[a-z]?|"
    r"\bsection\s+\d{1,4}[a-z]?\b.*\b(?:ipc|bns|penal|punishment)\b|"
    r"\b(?:punishment|penalty)\s+(?:for|under)\s+(?:ipc|bns|section)\b",
    re.I,
)
_BARE_SECTION_RE = re.compile(r"^\s*(?:section|sec\.?)\s*(\d{1,4}[a-z]?)\s*$", re.I)


def is_statute_focused_query(query: str) -> bool:
    """True when the user clearly asks about a penal-code section (not general doc Q&A)."""
    q = (query or "").strip()
    if not q:
        return False
    if _STATUTE_RE.search(q):
        return True
    if _BARE_SECTION_RE.match(q):
        return True
    try:
        from backend.app.services.legal_query_parser import section_numbers_from_query

        nums = section_numbers_from_query(q)
        if nums and re.search(r"\b(?:ipc|bns|crpc|section|punishment|penalty)\b", q, re.I):
            return True
    except Exception:
        pass
    return False


def query_target_doc_types(query: str) -> List[str]:
    """Soft hints for retrieval ranking — never hard-excludes other docs."""
    hints: List[str] = []
    try:
        from document_classifier import document_type_for_query, DocumentType

        dt = document_type_for_query(query)
        if dt:
            hints.append(dt)
        if re.search(r"\b(constitution|fundamental rights?|article\s+\d+)\b", query, re.I):
            hints.append("constitutional")
        if re.search(r"\b(contract|nda|agreement|indemnity|clause)\b", query, re.I):
            hints.extend([DocumentType.CONTRACT.value, DocumentType.NDA.value])
        if re.search(r"\b(judgment|petitioner|respondent|court held)\b", query, re.I):
            hints.append(DocumentType.COURT_JUDGMENT.value)
        if re.search(r"\b(notice|demand letter|cease)\b", query, re.I):
            hints.append(DocumentType.LEGAL_NOTICE.value)
        if re.search(r"\b(policy|privacy|terms of service)\b", query, re.I):
            hints.append(DocumentType.POLICY.value)
        if re.search(r"\b(fir|complainant|police station)\b", query, re.I):
            hints.append(DocumentType.FIR.value)
    except Exception:
        pass
    return list(dict.fromkeys(hints))


def chunks_overlap_query(query: str, chunks: List[Dict[str, Any]], *, min_ratio: float = 0.25) -> bool:
    """True when retrieved text shares meaningful terms with the question."""
    if not chunks or not (query or "").strip():
        return False
    stop = {
        "what", "when", "where", "which", "explain", "define", "about", "under",
        "the", "and", "for", "from", "with", "your", "this", "that", "document",
        "documents", "tell", "describe", "please", "does", "mean", "section",
    }
    terms = [
        w
        for w in re.findall(r"[A-Za-z0-9]{3,}", (query or "").lower())
        if w not in stop
    ]
    if not terms:
        return len((chunks[0].get("content") or "").strip()) > 80
    combined = " ".join((c.get("content") or "")[:600].lower() for c in chunks[:5])

    def _term_hit(term: str) -> bool:
        if term in combined:
            return True
        if len(term) >= 5:
            return any(term in w or w in term for w in combined.split() if len(w) >= 4)
        return False

    hits = sum(1 for t in terms if _term_hit(t))
    return hits >= max(1, int(len(terms) * min_ratio))


def boost_chunks_by_doc_relevance(
    chunks: List[Dict[str, Any]],
    query: str,
) -> List[Dict[str, Any]]:
    """Re-rank without dropping chunks — prefer matching document families."""
    if not chunks:
        return []
    hints = {h.lower() for h in query_target_doc_types(query)}
    if not hints:
        return chunks

    def _score(c: Dict[str, Any]) -> float:
        base = float(c.get("final_score") or c.get("hybrid_score") or 0.0)
        meta = c.get("metadata") or {}
        dt = str(meta.get("document_type") or "").lower()
        fn = str(meta.get("filename") or "").lower()
        body = (c.get("content") or "").lower()
        bonus = 0.0
        for h in hints:
            if h in dt or h in fn:
                bonus += 0.35
            if h == "constitutional" and any(
                k in body for k in ("fundamental", "article", "constitution", "equality")
            ):
                bonus += 0.25
        return base + bonus

    return sorted(chunks, key=_score, reverse=True)


def universal_retrieve(
    query: str,
    index_dir: Any,
    *,
    scope: Optional[Dict[str, Any]] = None,
    k: int = 12,
) -> List[Dict[str, Any]]:
    """
    Document-agnostic retrieval: vector + keyword docstore + optional type boost.
    Does not apply IPC-only filters or force section lookup.
    """
    scope = dict(scope or {})
    if scope.get("strict") and len(scope.get("allowed_filenames") or []) > 1:
        scope["strict"] = False

    merged: List[Dict[str, Any]] = []
    queries = [query]
    try:
        from backend.app.core.kb_query_expansion import expand_query_for_retrieval

        queries = expand_query_for_retrieval(query)
    except Exception:
        pass

    try:
        from rag import query_kb

        seen_q: set[str] = set()
        for qv in queries:
            qk = qv.lower()[:60]
            if qk in seen_q:
                continue
            seen_q.add(qk)
            vector_hits = query_kb(
                qv,
                k=max(k, 8),
                index_dir=index_dir,
                document_scope=scope if scope.get("strict") else None,
            )
            merged.extend(vector_hits or [])
    except Exception as exc:
        logger.debug("universal vector pass: %s", exc)

    try:
        from backend.app.core.kb_retrieval_robust import _keyword_docstore_hits

        merged.extend(
            _keyword_docstore_hits(
                query,
                index_dir,
                top_k=k,
                document_scope=scope if scope.get("strict") else None,
            )
        )
    except Exception as exc:
        logger.debug("universal keyword pass: %s", exc)

    # Constitutional / rights queries: also scan docstore for rights language
    ql = (query or "").lower()
    if any(
        k in ql
        for k in (
            "constitutional",
            "fundamental",
            "article ",
            "right to",
            "equality",
            "liberty",
        )
    ):
        try:
            from backend.app.core.kb_retrieval_robust import _constitutional_docstore_hits

            merged.extend(_constitutional_docstore_hits(query, index_dir, top_k=k))
        except Exception:
            pass

    try:
        from kb_content_cleaner import is_index_meta_boilerplate
    except ImportError:
        is_index_meta_boilerplate = lambda _t: False  # noqa: E731

    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for c in merged:
        body = c.get("content") or ""
        if is_index_meta_boilerplate(body):
            continue
        key = body[:100]
        if not key or key in seen:
            continue
        seen.add(key)
        c = dict(c)
        c.setdefault("retrieval_mode", "universal_hybrid")
        deduped.append(c)

    ranked = boost_chunks_by_doc_relevance(deduped, query)
    if scope.get("strict") and ranked:
        try:
            from backend.app.core.kb_doc_scope import filter_chunks_by_scope

            scoped = filter_chunks_by_scope(ranked, scope)
            if scoped:
                ranked = scoped
        except Exception:
            pass
    return ranked[: max(k, 10)]


def universal_document_answer(
    query: str,
    chunks: List[Dict[str, Any]],
    *,
    user_id: str = "",
    use_llm: bool = True,
) -> str:
    """Grounded answer — segmented narrative first; LLM polish only on clean context."""
    if not chunks:
        return ""

    try:
        from backend.app.core.case_narrative_engine import (
            build_entity_document_answer,
            filter_case_chunks,
        )
        from backend.app.core.case_entity_resolver import extract_case_needles

        needles = extract_case_needles(query)
        clean = filter_case_chunks(chunks, needles)
        entity_ans = build_entity_document_answer(query, clean or chunks)
        if entity_ans and len(entity_ans.strip()) > 80:
            return entity_ans
    except Exception as exc:
        logger.debug("universal entity narrative: %s", exc)

    try:
        from intent_engine import classify_intent
        from kb_response_state import build_found_answer

        profile = classify_intent(query, [])
        clean_chunks = chunks
        try:
            from backend.app.core.case_narrative_engine import filter_case_chunks
            from backend.app.core.case_entity_resolver import extract_case_needles

            clean_chunks = filter_case_chunks(chunks, extract_case_needles(query)) or chunks
        except Exception:
            pass
        ans = build_found_answer(
            query,
            clean_chunks[:6],
            profile,
            messages=[],
            use_llm=use_llm,
            user_id=user_id,
        )
        if ans and len(ans.strip()) > 60:
            if "From your uploaded documents" not in ans[:100] or len(ans) < 800:
                return ans
    except Exception as exc:
        logger.debug("universal build_found_answer: %s", exc)

    try:
        from backend.app.core.kb_force_answer import guarantee_kb_answer

        return guarantee_kb_answer(query, chunks) or ""
    except Exception:
        return ""
