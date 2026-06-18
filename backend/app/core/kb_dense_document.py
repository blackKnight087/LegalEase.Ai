"""
LegalEase dense / multi-topic KB test PDFs — structured extractors for mixed documents.

Handles: IPC/BNS sections (Meaning/Explanation fields), Important Cases blurbs,
Sample NDA clauses, constitutional lists — without chunk dumps or cross-topic bleed.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

_NDA_SECTION_RE = re.compile(
    r"(?:Sample\s+NDA(?:\s+Clauses)?|Non[- ]?Disclosure\s+Agreement|"
    r"Sample\s+Non[- ]?Disclosure)",
    re.I,
)
_NDA_END_RE = re.compile(
    r"(?:^|\n)\s*(?:IPC\s+Section|BNS\s+Section|Important\s+Cases|"
    r"Constitutional\s+Rights|Suggested\s+KB|Legal\s+Testing\s+Material)\b",
    re.I,
)
_IMPORTANT_CASES_RE = re.compile(r"Important\s+Cases\b", re.I)

_LANDMARK_LINE_RE = {
    "kesavananda": re.compile(
        r"Kesavananda\s+Bharati\s+Case\s*:\s*(.+?)(?=\s*(?:Nirbhaya\s+Case|Sample\s+NDA|"
        r"Constitutional\s+Rights|IPC\s+Section|$))",
        re.I | re.S,
    ),
    "nirbhaya": re.compile(
        r"Nirbhaya\s+Case\s*\([^)]*\)\s*:\s*(.+?)(?=\s*(?:Kesavananda|Sample\s+NDA|"
        r"Constitutional\s+Rights|IPC\s+Section|$))",
        re.I | re.S,
    ),
}


def is_nda_topic_query(query: str) -> bool:
    try:
        from document_classifier import is_contract_topic_query

        return is_contract_topic_query(query)
    except ImportError:
        pass
    ql = (query or "").lower()
    return bool(
        re.search(
            r"\b(?:nda|non[- ]?disclosure|confidential|disclosing\s+party|"
            r"receiving\s+party|sample\s+nda|sample\s+.*\s+agreement|sample\s+agreement)\b",
            ql,
        )
    )


def extract_nda_clauses_block(text: str) -> str:
    """Isolate Sample NDA / confidentiality clause text from a mixed KB PDF."""
    body = (text or "").strip()
    if not body:
        return ""
    m = _NDA_SECTION_RE.search(body)
    if not m:
        if re.search(r"\bdisclosing\s+party\b", body, re.I) and re.search(
            r"\breceiving\s+party\b", body, re.I
        ):
            start = 0
        else:
            return ""
    else:
        start = m.start()

    tail = body[start:]
    end_m = _NDA_END_RE.search(tail, pos=30)
    block = tail[: end_m.start()].strip() if end_m else tail[:1200].strip()
    block = re.sub(r"\s+", " ", block)
    if len(block) < 40:
        return ""
    return block


def build_nda_topic_answer(
    query: str,
    chunks: Sequence[Dict[str, Any]],
    *,
    index_dir: Any = None,
    scope: Optional[Dict[str, Any]] = None,
) -> str:
    """Answer NDA / confidentiality questions from mixed criminal+NDA test PDFs."""
    if not is_nda_topic_query(query):
        return ""

    combined_parts: List[str] = []
    for ch in chunks or []:
        block = extract_nda_clauses_block(ch.get("content") or "")
        if block:
            combined_parts.append(block)

    if index_dir is not None:
        try:
            from backend.app.core.kb_doc_scope import load_contract_index_text, load_scoped_document_text

            if scope and scope.get("strict"):
                scoped = load_scoped_document_text(index_dir, scope)
                if scoped:
                    block = extract_nda_clauses_block(scoped)
                    if block:
                        combined_parts.append(block)
            extra = load_contract_index_text(index_dir, scope)
            if extra:
                block = extract_nda_clauses_block(extra)
                if block:
                    combined_parts.append(block)
        except Exception:
            pass

    combined = " ".join(combined_parts)
    if not combined:
        return ""

    ql = (query or "").lower()
    summarize = bool(
        re.search(r"\b(?:summarize|summarise|summary|overview|sample\s+nda)\b", ql)
    )
    lines: List[str] = ["## Sample NDA (from your uploaded document)", ""]

    pm = re.search(r"Parties\s+involved:\s*([^.]+\.)", combined, re.I)
    if pm:
        lines.append(f"**Parties:** {pm.group(1).strip()}")
    elif re.search(r"\bdisclosing\s+party\b", combined, re.I):
        lines.append(
            "**Parties:** Disclosing Party and Receiving Party (as stated in your document)."
        )

    cm = re.search(r"Confidential\s+information[^.]*\.", combined, re.I)
    if cm:
        lines.append(f"\n**Confidential Information:** {cm.group(0).strip()}")

    term_m = re.search(
        r"(?:Term|Duration|Effective\s+date)[^.]*\.",
        combined,
        re.I,
    )
    if term_m:
        lines.append(f"\n**Term:** {term_m.group(0).strip()}")

    tm = re.search(r"Upon\s+termination[^.]*\.", combined, re.I)
    if tm:
        lines.append(f"\n**Termination:** {tm.group(0).strip()}")

    if summarize or len(lines) <= 2:
        if pm or cm or tm:
            pass
        elif len(lines) <= 2:
            lines.append(combined[:900])

    body = "\n".join(lines).strip()
    try:
        from backend.app.core.kb_document_first import format_kb_structured_response

        meta = (chunks[0].get("metadata") if chunks else {}) or {}
        return format_kb_structured_response(
            body,
            [{"content": combined[:500], "metadata": meta}],
            confidence=0.88,
        )
    except ImportError:
        return body


def enrich_landmark_passage(text: str, landmark_key: str) -> str:
    """Prefer 'Name: description' lines from Important Cases sections."""
    key = landmark_key.lower()
    pat = _LANDMARK_LINE_RE.get(key)
    if pat:
        m = pat.search(text or "")
        if m:
            desc = re.sub(r"\s+", " ", m.group(1).strip())
            title = "Kesavananda Bharati Case" if key == "kesavananda" else "Nirbhaya Case"
            if len(desc) > 25:
                return f"{title}: {desc}"

    try:
        from backend.app.core.kb_landmark_case import extract_landmark_passage

        base = extract_landmark_passage(text, key)
        if base and len(base) > 50:
            return base
    except ImportError:
        pass

    if _IMPORTANT_CASES_RE.search(text or ""):
        m = re.search(
            rf"{re.escape(key)}[^:.\n]{{0,40}}:\s*([^.\n]{{20,400}}\.)",
            text,
            re.I,
        )
        if m:
            return m.group(0).strip()
    return ""


def build_dense_section_explain(
    query: str,
    chunks: Sequence[Dict[str, Any]],
) -> str:
    """Explain IPC/BNS section using Meaning/Explanation/Example fields from dense PDFs."""
    try:
        from backend.app.core.kb_document_first import (
            parse_statute_lookup,
            try_statute_section_lookup_answer,
        )

        direct = try_statute_section_lookup_answer(query, list(chunks))
        if direct and re.search(r"\*\*Meaning:\*\*", direct):
            return direct
        sec, law = parse_statute_lookup(query)
        if not sec:
            return direct or ""
    except ImportError:
        return ""

    for ch in chunks:
        body = ch.get("content") or ""
        if not re.search(rf"\b(?:IPC|BNS)\s+Section\s+{re.escape(sec)}\b", body, re.I):
            continue
        try:
            from kb_preprocess import extract_section_content
            from kb_content_cleaner import format_statute_section_fields

            isolated = extract_section_content(body, sec) or body
            formatted = format_statute_section_fields(isolated, section=sec, law=law.upper())
            if formatted and len(formatted) > 80:
                try:
                    from answer_orchestrator import polish_kb_response

                    return polish_kb_response(formatted, [ch])
                except ImportError:
                    return formatted
        except ImportError:
            pass
    return direct or ""


def collect_combined_chunk_text(
    chunks: Sequence[Dict[str, Any]],
    *,
    index_dir: Any = None,
    scope: Optional[Dict[str, Any]] = None,
) -> str:
    parts: List[str] = []
    seen: set[str] = set()
    for ch in chunks or []:
        t = (ch.get("content") or "").strip()
        if t and t[:80] not in seen:
            seen.add(t[:80])
            parts.append(t)
    if index_dir and scope and scope.get("strict"):
        try:
            from backend.app.core.kb_doc_scope import load_scoped_document_text

            full = load_scoped_document_text(index_dir, scope)
            if full and full[:80] not in seen:
                parts.append(full)
        except Exception:
            pass
    return "\n\n".join(parts)


def try_dense_document_answer(
    query: str,
    chunks: Sequence[Dict[str, Any]],
    *,
    index_dir: Any = None,
    scope: Optional[Dict[str, Any]] = None,
) -> str:
    """Single entry: NDA, landmark, section explain — for LegalEase dense PDFs."""
    if is_nda_topic_query(query):
        ans = build_nda_topic_answer(query, chunks, index_dir=index_dir, scope=scope)
        if ans:
            return ans

    try:
        from backend.app.core.kb_landmark_case import (
            build_landmark_case_answer,
            is_landmark_case_query,
            landmark_keys_in_query,
        )

        if is_landmark_case_query(query):
            combined = collect_combined_chunk_text(chunks, index_dir=index_dir, scope=scope)
            if combined:
                keys = landmark_keys_in_query(query)
                enriched_chunks = list(chunks)
                passage = enrich_landmark_passage(combined, keys[0]) if keys else ""
                if passage:
                    enriched_chunks = [
                        {
                            "content": passage,
                            "metadata": (chunks[0].get("metadata") if chunks else {}) or {},
                            "final_score": 2.0,
                        }
                    ] + list(chunks)
            ans = build_landmark_case_answer(query, enriched_chunks or chunks)
            if ans and len(ans) > 120:
                return ans
    except ImportError:
        pass

    if re.search(r"\bexplain\b", (query or "").lower()):
        sec_ans = build_dense_section_explain(query, chunks)
        if sec_ans:
            return sec_ans

    return ""


def ollama_synthesis_mode() -> str:
    import os

    return (os.getenv("KB_USE_OLLAMA_SYNTHESIS") or "hybrid").strip().lower()


def should_invoke_ollama() -> bool:
    return ollama_synthesis_mode() not in {"0", "false", "no", "off", ""}


def should_ollama_polish_only() -> bool:
    return ollama_synthesis_mode() in {"hybrid", "polish", "extractive_first"}
