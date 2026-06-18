"""
Document-first Knowledge Base answering — generic for any uploaded PDF.

Ollama is optional polish only. Primary answers are built from retrieved chunks.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

KB_INSUFFICIENT_FULL = (
    "The uploaded documents do not contain sufficient information to answer this question."
)

_PAGE_MARKER_RE = re.compile(r"\[\s*PAGE\s*:\s*(\d+)\s*\]", re.I)
_STOPWORDS = frozenset(
    {
        "what", "when", "where", "which", "explain", "define", "about", "under",
        "the", "and", "for", "from", "with", "your", "this", "that", "document",
        "documents", "tell", "describe", "please", "does", "mean", "section",
        "summarize", "summary", "list", "show", "give", "say", "report",
    }
)

_STATUTE_LOOKUP_RE = re.compile(
    r"\b(?:IPC|BNS|CrPC|BNSS|Indian\s+Penal\s+Code)\s+Section\s+(\d{1,4}[a-z]?)\b",
    re.I,
)


def is_statute_section_lookup_query(query: str) -> bool:
    """Bare or labeled statute section lookup (not constitutional rights lists)."""
    q = (query or "").strip()
    if not q:
        return False
    try:
        from backend.app.core.constitutional_concept_map import (
            is_constitutional_rights_list_query,
        )

        if is_constitutional_rights_list_query(q):
            return False
    except ImportError:
        pass
    if _STATUTE_LOOKUP_RE.search(q):
        return True
    try:
        from kb_query_types import is_bare_section_query

        if is_bare_section_query(q):
            return True
    except ImportError:
        pass
    ql = q.lower()
    if re.search(r"\bsection\s+\d{1,4}[a-z]?\b", ql) and re.search(
        r"\b(?:ipc|bns|crpc|bnss)\b", ql
    ):
        return True
    return False


def parse_statute_lookup(query: str) -> Tuple[str, str]:
    """Return (section_number, law_lower) e.g. ('103', 'bns')."""
    q = (query or "").strip()
    m = _STATUTE_LOOKUP_RE.search(q)
    if m:
        sec = m.group(1).lower()
        law = "bns" if re.search(r"\bbns\b", q, re.I) else "ipc"
        if re.search(r"\bipc\b", q, re.I) and not re.search(r"\bbns\b", q, re.I):
            law = "ipc"
        return sec, law
    try:
        from kb_rag_decision import extract_query_sections

        secs = extract_query_sections(q)
    except Exception:
        secs = []
    if not secs:
        m2 = re.search(r"\bsection\s+(\d{1,4}[a-z]?)\b", q, re.I)
        if m2:
            secs = [m2.group(1)]
    if not secs:
        return "", ""
    sec = secs[0].lower()
    law = "bns" if re.search(r"\bbns\b", q, re.I) else "ipc"
    return sec, law


def try_statute_section_lookup_answer(
    query: str,
    chunks: List[Dict[str, Any]],
) -> str:
    """Deterministic IPC/BNS section card — never dump unrelated document topics."""
    if not is_statute_section_lookup_query(query) or not chunks:
        return ""
    sec, law = parse_statute_lookup(query)
    if not sec:
        return ""
    try:
        from kb_preprocess import filter_chunks_for_section
        from answer_orchestrator import format_statute_section_answer

        scoped = filter_chunks_for_section(chunks, sec, law=law)
        ans = format_statute_section_answer(query, scoped or chunks, sec, law)
        return (ans or "").strip()
    except ImportError:
        return ""


def kb_llm_temperature() -> float:
    raw = (__import__("os").getenv("KB_LLM_TEMPERATURE") or "0.23").strip()
    try:
        return max(0.0, min(float(raw), 1.0))
    except ValueError:
        return 0.23


def kb_llm_top_p() -> float:
    raw = (__import__("os").getenv("KB_LLM_TOP_P") or "0.1").strip()
    try:
        return max(0.05, min(float(raw), 1.0))
    except ValueError:
        return 0.1


def _query_terms(query: str) -> List[str]:
    ql = (query or "").lower()
    terms = [
        w
        for w in re.findall(r"[a-z0-9]{3,}", ql)
        if w not in _STOPWORDS
    ]
    return terms


def _chunk_meta(ch: Dict[str, Any]) -> Dict[str, str]:
    m = ch.get("metadata") or {}
    fn = str(m.get("filename") or m.get("source_file") or "uploaded document")
    page = str(m.get("page") or m.get("page_number") or "")
    if not page:
        pm = _PAGE_MARKER_RE.search(ch.get("content") or "")
        if pm:
            page = pm.group(1)
    sec = str(m.get("section") or m.get("primary_section") or "")
    return {"filename": fn, "page": page, "section": sec}


def _clean_excerpt(text: str, *, max_len: int = 1200) -> str:
    t = (text or "").strip()
    t = re.sub(r"\(cid:\d+\)\s*", "", t)
    t = _PAGE_MARKER_RE.sub(lambda m: f"[Page {m.group(1)}] ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        t = t[:max_len].rstrip() + "…"
    return t


def _score_chunk_for_query(query: str, ch: Dict[str, Any]) -> float:
    terms = _query_terms(query)
    body = (ch.get("content") or "").lower()
    if not body:
        return 0.0
    base = float(ch.get("final_score") or ch.get("hybrid_score") or ch.get("score") or 0.0)
    if not terms:
        return base
    hits = sum(1 for t in terms if t in body)
    phrase = " ".join(terms[:6])
    bonus = hits * 2.0
    if phrase and phrase in body:
        bonus += 6.0
    return base + bonus


def select_relevant_chunks(query: str, chunks: List[Dict[str, Any]], *, top_k: int = 6) -> List[Dict[str, Any]]:
    if not chunks:
        return []
    ranked = sorted(chunks, key=lambda c: -_score_chunk_for_query(query, c))
    terms = _query_terms(query)
    if not terms:
        return ranked[:top_k]
    filtered = [c for c in ranked if _score_chunk_for_query(query, c) >= 2.0]
    return (filtered or ranked)[:top_k]


def chunks_answer_query(query: str, chunks: List[Dict[str, Any]]) -> bool:
    if not chunks:
        return False
    try:
        from backend.app.core.universal_kb import chunks_overlap_query

        if chunks_overlap_query(query, chunks, min_ratio=0.2):
            return True
    except ImportError:
        pass
    terms = _query_terms(query)
    if not terms:
        return len((chunks[0].get("content") or "").strip()) > 60
    combined = " ".join((c.get("content") or "")[:700].lower() for c in chunks[:5])
    hits = sum(1 for t in terms if t in combined)
    return hits >= max(1, (len(terms) + 1) // 2)


def _extract_matching_paragraphs(query: str, text: str, *, max_paras: int = 4) -> List[str]:
    terms = _query_terms(query)
    paras: List[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = re.sub(r"\s+", " ", block).strip()
        if len(block) < 20:
            continue
        bl = block.lower()
        if terms and not any(t in bl for t in terms):
            continue
        paras.append(block)
        if len(paras) >= max_paras:
            break
    if not paras and text.strip():
        paras = [_clean_excerpt(text, max_len=900)]
    return paras


def prune_ungrounded_sentences(answer: str, chunks: List[Dict[str, Any]]) -> str:
    """Remove sentences with no token overlap with retrieved chunks."""
    try:
        from backend.app.core.kb_claim_audit import audit_and_prune_answer

        return audit_and_prune_answer(answer, chunks)
    except ImportError:
        pass
    ctx = " ".join((c.get("content") or "")[:1200].lower() for c in chunks[:8])
    if not ctx.strip():
        return (answer or "").strip()
    kept: List[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", (answer or "").strip()):
        s = sent.strip()
        if len(s) < 25:
            kept.append(s)
            continue
        words = {w for w in re.findall(r"[a-z]{5,}", s.lower())} - _STOPWORDS
        if not words:
            continue
        hits = sum(1 for w in list(words)[:15] if w in ctx)
        if hits >= max(2, len(words) // 3):
            kept.append(s)
    return " ".join(kept).strip()


def strip_insufficient_disclaimer(text: str) -> str:
    """Remove insufficient-info lines from otherwise grounded answers."""
    from backend.app.core.kb_strict_policy import KB_INSUFFICIENT_INFO

    lines = []
    for line in (text or "").splitlines():
        low = line.strip().lower()
        if not low:
            if lines:
                lines.append("")
            continue
        if "sufficient information" in low:
            continue
        if low.startswith("**from your documents:**"):
            continue
        if low.startswith("no sufficient"):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def format_kb_structured_response(
    answer_body: str,
    chunks: List[Dict[str, Any]],
    *,
    confidence: Optional[float] = None,
) -> str:
    """User-facing KB format: Answer / Supporting Evidence / Source / Page / Confidence."""
    body = strip_insufficient_disclaimer((answer_body or "").strip())
    if not body:
        return KB_INSUFFICIENT_FULL

    top = chunks[0] if chunks else {}
    meta = _chunk_meta(top)
    evidence_parts: List[str] = []
    for c in chunks[:2]:
        ex = _clean_excerpt(c.get("content") or "", max_len=400)
        if ex and ex.lower() in body.lower() or any(
            w in ex.lower() for w in re.findall(r"[a-z]{6,}", body.lower())[:12]
        ):
            evidence_parts.append(f"> {ex}")
    evidence = "\n\n".join(evidence_parts) if evidence_parts else f"> {_clean_excerpt(top.get('content') or '', max_len=500)}"

    if confidence is None:
        confidence = min(
            0.95,
            max(
                0.55,
                float(top.get("final_score") or top.get("hybrid_score") or top.get("score") or 0.72),
            ),
        )

    page_line = meta["page"] or "Not specified in excerpt"
    return (
        f"## Answer\n\n{body}\n\n"
        f"## Supporting Evidence\n\n{evidence}\n\n"
        f"**Source File:** {meta['filename']}\n\n"
        f"**Page Number:** {page_line}\n\n"
        f"**Confidence Score:** {confidence:.0%}"
    )


def build_document_first_answer(
    query: str,
    chunks: List[Dict[str, Any]],
) -> str:
    """
  Generic extractive answer from chunks — no LLM, any document type.
  Returns empty string if chunks do not support the question.
    """
    if not chunks:
        return ""
    try:
        from backend.app.core.kb_question_aware import generate_question_aware_answer

        qa = generate_question_aware_answer(query, chunks)
        if qa:
            return qa
    except ImportError:
        pass
    try:
        from backend.app.core.kb_dense_document import try_dense_document_answer

        dense = try_dense_document_answer(query, chunks)
        if dense:
            return dense
    except ImportError:
        pass
    try:
        from backend.app.core.kb_landmark_case import (
            build_landmark_case_answer,
            is_landmark_case_query,
        )

        if is_landmark_case_query(query):
            landmark = build_landmark_case_answer(query, chunks)
            if landmark:
                return landmark
            return ""
    except ImportError:
        pass
    statute_ans = try_statute_section_lookup_answer(query, chunks)
    if statute_ans:
        return statute_ans
    try:
        from backend.app.core.constitutional_concept_map import (
            is_constitutional_rights_list_query,
        )
        from answer_orchestrator import format_constitutional_rights_answer

        if is_constitutional_rights_list_query(query):
            const_ans = format_constitutional_rights_answer(query, chunks)
            if const_ans:
                return const_ans
    except ImportError:
        pass
    try:
        from backend.app.core.kb_claim_audit import try_statute_safe_answer

        safe = try_statute_safe_answer(query, chunks)
        if safe:
            return safe
    except ImportError:
        pass
    try:
        from backend.app.core.kb_case_context_lock import (
            is_case_locked_query,
            lock_chunks_to_query,
        )

        if is_case_locked_query(query):
            chunks = lock_chunks_to_query(query, chunks)
    except ImportError:
        pass
    selected = select_relevant_chunks(query, chunks)
    if not chunks_answer_query(query, selected):
        return ""

    combined_raw = "\n\n".join((c.get("content") or "") for c in selected)
    paras = _extract_matching_paragraphs(query, combined_raw)
    if not paras:
        return ""

    terms = _query_terms(query)
    ql = (query or "").lower()

    # Title / topic lookup — require substantive sentences, not headings alone
    if len(terms) >= 2 and not re.search(r"\bexplain\b", ql):
        title_hits = [
            p
            for p in paras
            if all(t in p.lower() for t in terms[:3]) and len(p.split()) >= 12
        ]
        if title_hits:
            paras = title_hits[:2]

    if re.search(r"\b(?:summarize|summary|overview)\b", ql):
        intro = "The uploaded document states:"
    elif re.search(r"\bexplain\b", ql):
        intro = "Based on the uploaded document:"
    elif re.search(r"\bwhat does\b|\bwhat is\b|\bsay about\b", ql):
        intro = "The document records:"
    else:
        intro = "From the uploaded document:"

    body_parts = [intro, ""]
    for p in paras[:4]:
        body_parts.append(p)
    body = "\n\n".join(body_parts).strip()
    try:
        from backend.app.core.kb_landmark_case import strip_kb_document_boilerplate

        body = strip_kb_document_boilerplate(body)
    except ImportError:
        pass
    body = prune_ungrounded_sentences(body, selected)
    if len(body) < 40:
        return ""
    try:
        from kb_content_cleaner import is_kb_test_boilerplate

        if is_kb_test_boilerplate(body[:400]):
            return ""
    except ImportError:
        pass

    conf = min(
        0.92,
        max(0.6, float(selected[0].get("final_score") or selected[0].get("hybrid_score") or 0.75)),
    )
    return format_kb_structured_response(body, selected, confidence=conf)


def finalize_document_first(
    answer: str,
    query: str,
    chunks: List[Dict[str, Any]],
) -> str:
    """
    Last-mile KB gate: document-first rebuild, strip disclaimers, structured format.
    """
    from backend.app.core.kb_strict_policy import answer_has_outside_knowledge_bleed

    statute_ans = try_statute_section_lookup_answer(query, chunks)
    if statute_ans:
        return statute_ans

    try:
        from backend.app.core.constitutional_concept_map import (
            is_constitutional_rights_list_query,
        )
        from answer_orchestrator import format_constitutional_rights_answer

        if is_constitutional_rights_list_query(query):
            const_ans = format_constitutional_rights_answer(query, chunks)
            if const_ans:
                return const_ans
    except ImportError:
        pass

    try:
        from backend.app.core.kb_case_context_lock import is_case_locked_query, lock_chunks_to_query
        from backend.app.core.kb_claim_audit import (
            answer_has_legal_definition_leak,
            try_statute_safe_answer,
        )

        if is_case_locked_query(query):
            locked = lock_chunks_to_query(query, chunks)
            try:
                from backend.app.core.case_narrative_engine import build_case_answer_from_chunks
                from answer_orchestrator import polish_kb_response

                case_body = build_case_answer_from_chunks(query, locked or chunks)
                if case_body:
                    return polish_kb_response(case_body, locked or chunks)
            except ImportError:
                pass

        safe = try_statute_safe_answer(query, chunks)
        if safe:
            return safe
        if answer and answer_has_legal_definition_leak(answer, chunks):
            safe = try_statute_safe_answer(query, chunks)
            if safe:
                return safe
            answer = ""
    except ImportError:
        pass

    if chunks:
        doc_any = build_document_first_answer(query, chunks)
        if doc_any:
            return doc_any

    if chunks_answer_query(query, chunks):
        doc_first = build_document_first_answer(query, chunks)
        if doc_first:
            return doc_first

    cleaned = strip_insufficient_disclaimer(answer)
    if cleaned and chunks_answer_query(query, chunks):
        cleaned = prune_ungrounded_sentences(cleaned, chunks)
        if answer_has_outside_knowledge_bleed(cleaned):
            cleaned = ""
        if cleaned and len(cleaned) > 40:
            cleaned = prune_ungrounded_sentences(cleaned, chunks)
            if len(cleaned) < 40:
                cleaned = ""
            if cleaned:
                if "## Answer" not in cleaned:
                    return format_kb_structured_response(
                        cleaned, select_relevant_chunks(query, chunks)
                    )
                return cleaned

    if chunks_answer_query(query, chunks):
        doc_first = build_document_first_answer(query, chunks)
        if doc_first:
            return doc_first

    return KB_INSUFFICIENT_FULL
