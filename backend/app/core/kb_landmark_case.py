"""
Landmark / named-case blurbs in mixed KB test PDFs — extract one case only, no chunk dumps.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from backend.app.core.case_entity_resolver import _LANDMARK_KEYS

_LANDMARK_HEADERS: Dict[str, re.Pattern] = {
    "kesavananda": re.compile(
        r"Kesavananda\s+Bharati\s+Case\b",
        re.I,
    ),
    "nirbhaya": re.compile(
        r"Nirbhaya\s+Case\b",
        re.I,
    ),
    "vishaka": re.compile(r"Vishaka\s+Case\b", re.I),
    "puttaswamy": re.compile(r"Puttaswamy\b", re.I),
    "navtej": re.compile(r"Navtej\b", re.I),
    "shayara": re.compile(r"Shayara\b", re.I),
}

_NEXT_TOPIC_RE = re.compile(
    r"(?:"
    r"Right\s+to\s+|Right\s+against\s+|Five\s+Constitutional|"
    r"Constitutional\s+Rights|Important\s+Cases|"
    r"IPC\s+Section|BNS\s+Section|Case\s+\d+|Sample\s+NDA|Sample\s+Non|"
    r"LegalEase\s+KB|Bharatiya\s+Nyaya|Indian\s+Penal\s+Code|"
    r"Nirbhaya\s+Case|Vishaka\s+Case|Suggested\s+KB"
    r")",
    re.I,
)

_DOC_BOILERPLATE_RE = re.compile(
    r"\b(?:legalease\s+kb\s+testing|realistic\s+indian[- ]style\s+legal\s+case\s+compilation|"
    r"created\s+for\s+testing\s+legalease\s+kb|stress\s+test\s+legalease)\b",
    re.I,
)


def landmark_keys_in_query(query: str) -> List[str]:
    ql = (query or "").lower()
    return [k for k in _LANDMARK_KEYS if k in ql]


def is_landmark_case_query(query: str) -> bool:
    return bool(landmark_keys_in_query(query))


def extract_landmark_passage(text: str, landmark_key: str) -> str:
    """Single landmark blurb from a multi-topic page (often one line in test PDFs)."""
    body = re.sub(r"\(cid:\d+\)\s*", "", text or "")
    body = re.sub(r"\s+", " ", body).strip()
    if not body:
        return ""

    pat = _LANDMARK_HEADERS.get(landmark_key.lower())
    if not pat:
        m = re.search(rf"\b{re.escape(landmark_key)}[^.]{{0,400}}\.?", body, re.I)
        return m.group(0).strip() if m else ""

    m = pat.search(body)
    if not m:
        return ""

    tail = body[m.start() :]
    search_from = max(20, len(m.group(0)))
    end_m = _NEXT_TOPIC_RE.search(tail, pos=search_from)
    if end_m:
        tail = tail[: end_m.start()].strip()
    else:
        m_stop = re.search(
            r"\.\s+(?:Nirbhaya|IPC\s+Section|BNS\s+Section|Five\s+Constitutional|Case\s+\d)",
            tail,
            re.I,
        )
        if m_stop:
            tail = tail[: m_stop.start() + 1].strip()
        else:
            tail = tail[:500].strip()

    tail = re.sub(r"\s+", " ", tail).strip()
    if _DOC_BOILERPLATE_RE.search(tail):
        return ""
    return tail


def strip_kb_document_boilerplate(text: str) -> str:
    """Remove test-document index lines from user-facing answers."""
    if not text:
        return ""
    try:
        from kb_content_cleaner import is_kb_test_boilerplate, strip_kb_test_boilerplate

        return strip_kb_test_boilerplate(text)
    except ImportError:
        pass
    lines: List[str] = []
    for line in (text or "").splitlines():
        if _DOC_BOILERPLATE_RE.search(line):
            continue
        if is_landmark_boilerplate_only(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def is_landmark_boilerplate_only(line: str) -> bool:
    ls = (line or "").strip()
    if not ls:
        return False
    if _DOC_BOILERPLATE_RE.search(ls):
        return True
    if re.match(
        r"^LegalEase\s+KB\s+Testing\s+Document",
        ls,
        re.I,
    ):
        return True
    return False


def chunk_supports_landmark(chunk: Dict[str, Any], landmark_key: str) -> bool:
    """Chunk must contain a substantive landmark passage, not only an FAQ mention."""
    body = (chunk.get("content") or "")
    bl = body.lower()
    key = landmark_key.lower()
    if key not in bl:
        return False
    passage = extract_landmark_passage(body, key)
    if len(passage) < 40:
        return False
    if passage.lower().count(key) < 1:
        return False
    return bool(_LANDMARK_HEADERS.get(key, re.compile(re.escape(key), re.I)).search(passage))


def build_landmark_case_answer(
    query: str,
    chunks: Sequence[Dict[str, Any]],
) -> str:
    keys = landmark_keys_in_query(query)
    if not keys or not chunks:
        return ""

    key = keys[0]
    best_passage = ""
    best_score = 0.0
    for ch in chunks:
        if not chunk_supports_landmark(ch, key):
            continue
        passage = extract_landmark_passage(ch.get("content") or "", key)
        score = float(ch.get("final_score") or ch.get("hybrid_score") or 0) + len(passage) / 200.0
        if len(passage) > len(best_passage) or score > best_score:
            best_passage = passage
            best_score = score

    if len(best_passage) < 50:
        try:
            from backend.app.core.kb_dense_document import enrich_landmark_passage

            for ch in chunks:
                enriched = enrich_landmark_passage(ch.get("content") or "", key)
                if enriched and len(enriched) > len(best_passage):
                    best_passage = enriched
        except ImportError:
            pass

    if not best_passage or len(best_passage) < 35:
        return ""

    body = strip_kb_document_boilerplate(best_passage)
    body = re.sub(r"\s*Sample\s+NDA.*$", "", body, flags=re.I).strip()
    if not body or len(body) < 40:
        return ""

    try:
        from backend.app.core.kb_question_aware import structure_landmark_passage

        structured = structure_landmark_passage(key, body)
        if structured and len(structured) > 90:
            answer_body = structured
        else:
            raise ValueError("short structured")
    except Exception:
        title = "Kesavananda Bharati Case" if "kesavananda" in key else f"{key.replace('_', ' ').title()} Case"
        if len(body) < 60 and ":" not in body:
            return ""
        answer_body = f"## {title}\n\n### Case Summary\n\n{body}"

    evidence_chunk = {
        "content": body,
        "metadata": (chunks[0].get("metadata") if chunks else {}) or {},
    }
    try:
        from backend.app.core.kb_document_first import format_kb_structured_response

        return format_kb_structured_response(
            answer_body, [evidence_chunk], confidence=0.9
        )
    except ImportError:
        return answer_body


def answer_mentions_wrong_landmark(answer: str, query: str) -> bool:
    """Reject answers that mix multiple landmark topics."""
    keys = landmark_keys_in_query(query)
    if not keys:
        return False
    primary = keys[0].lower()
    al = (answer or "").lower()
    for other in _LANDMARK_KEYS:
        if other == primary or other not in al:
            continue
        if other in al and primary not in al:
            return True
    return False
