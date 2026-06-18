"""Resolve topical case queries (e.g. 'explain the theft case') to narrative case segments."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

_TOPIC_CASE_RE = re.compile(
    r"\b(?:explain|describe|tell\s+me\s+about|summarize|summary\s+of|what\s+happened\s+in)?\s*"
    r"(?:the\s+)?([a-z][a-z-]{2,24})\s+case\b",
    re.I,
)
_TOPIC_IN_QUERY_RE = re.compile(
    r"\b(?:in|about|for|regarding)\s+the\s+([a-z][a-z-]{2,24})\s+case\b",
    re.I,
)

_TOPIC_STOPWORDS = frozenset(
    {
        "explain",
        "describe",
        "case",
        "the",
        "this",
        "that",
        "same",
        "uploaded",
        "document",
        "detail",
        "brief",
        "full",
        "legal",
        "court",
        "section",
        "ipc",
        "bns",
    }
)

_CRIME_TOPICS = frozenset(
    {
        "theft",
        "murder",
        "cheating",
        "fraud",
        "robbery",
        "rape",
        "bail",
        "cyber",
        "assault",
        "kidnapping",
        "abduction",
        "forgery",
        "defamation",
        "negligence",
        "arson",
        "burglary",
        "extortion",
        "stalking",
        "harassment",
        "confidentiality",
        "breach",
        "contract",
        "divorce",
        "custody",
        "maintenance",
        "permit",
        "property",
        "medical",
        "emergency",
    }
)

_STATUTE_STUB_RE = re.compile(
    r"^(?:Meaning|Punishment)\s*:\s*.+",
    re.M | re.I,
)
_TEST_META_RE = re.compile(
    r"\b(?:rigorously test retrieval|section mapping,?\s*punishment extraction)\b",
    re.I,
)


def is_topic_case_query(query: str) -> bool:
    q = (query or "").strip()
    if not q:
        return False
    if re.search(r"\b\w+\s+vs\.?\s+\w+", q, re.I):
        return False
    m = _TOPIC_CASE_RE.search(q) or _TOPIC_IN_QUERY_RE.search(q)
    if not m:
        return False
    topic = m.group(1).lower()
    return topic not in _TOPIC_STOPWORDS and (
        topic in _CRIME_TOPICS or len(topic) >= 4
    )


def extract_topic_case_needles(query: str) -> List[str]:
    q = (query or "").strip().lower()
    needles: List[str] = []
    for pat in (_TOPIC_CASE_RE, _TOPIC_IN_QUERY_RE):
        m = pat.search(q)
        if m:
            topic = m.group(1).lower()
            if topic not in _TOPIC_STOPWORDS and topic not in needles:
                needles.append(topic)
    for topic in _CRIME_TOPICS:
        if re.search(rf"\b{re.escape(topic)}\b", q) and topic not in needles:
            if "case" in q or re.search(rf"\b{topic}\s+case\b", q):
                needles.append(topic)
    return needles[:4]


def is_topic_only_needles(needles: List[str]) -> bool:
    if not needles:
        return False
    core = [n for n in needles if n.lower() not in _TOPIC_STOPWORDS]
    return bool(core) and all(" " not in n for n in core)


def is_statute_stub_chunk(text: str) -> bool:
    """IPC/BNS field stubs from dense test docs — not case narratives."""
    t = (text or "").strip()
    if not t:
        return True
    if re.search(r"\bCase\s+\d+\s*:", t, re.I):
        return False
    if re.search(r"\bvs\.?\s+", t, re.I) and case_narrative_score(t) >= 1.5:
        return False
    if _TEST_META_RE.search(t):
        return True
    if _STATUTE_STUB_RE.search(t[:400]) and not re.search(
        r"\b(?:accused|petitioner|complainant|prosecution|defense|fir)\b", t, re.I
    ):
        return True
    return False


def case_narrative_score(text: str) -> float:
    try:
        from backend.app.core.case_entity_resolver import case_narrative_score as _s

        return _s(text)
    except ImportError:
        tl = (text or "").lower()
        score = 0.0
        if re.search(r"\bcase\s+\d+:", tl):
            score += 1.5
        if "accused" in tl or "petitioner" in tl:
            score += 2.0
        return score


def chunk_matches_topic_case(chunk: dict, needles: List[str]) -> bool:
    body = (chunk.get("content") or "").strip()
    if not body or is_statute_stub_chunk(body):
        return False
    if case_narrative_score(body) < 1.0:
        return False
    topics = [n.lower() for n in needles if n.lower() not in _TOPIC_STOPWORDS]
    if not topics:
        return False
    header = body[:320].lower()
    for topic in topics:
        if topic in header:
            return True
        if re.search(rf"case\s+\d+:[^\n]*\b{re.escape(topic)}\b", body, re.I):
            return True
    bl = body.lower()
    if re.search(r"\bcase\s+\d+:", bl) and any(topic in bl for topic in topics):
        return True
    return False


def lookup_topic_case_chunks(
    index_dir: Any,
    topics: List[str],
    *,
    top_k: int = 6,
) -> List[Dict[str, Any]]:
    if not topics:
        return []
    try:
        from rag import _load_docstore_only
    except ImportError:
        return []

    try:
        view = _load_docstore_only(Path(index_dir))
    except Exception:
        view = None
    if view is None:
        return []

    try:
        from backend.app.core.case_narrative_engine import (
            is_faq_or_boilerplate,
            segment_cases_in_text,
        )
    except ImportError:
        return []

    ranked: List[tuple[float, Dict[str, Any]]] = []
    topic_l = [t.lower() for t in topics]

    for doc_id in view.index_to_docstore_id.values():
        try:
            doc = view.docstore.search(doc_id)
        except Exception:
            continue
        content = (getattr(doc, "page_content", None) or "").strip()
        if not content:
            continue
        meta = dict(getattr(doc, "metadata", None) or {})

        for seg in segment_cases_in_text(content):
            text = (seg.get("text") or "").strip()
            if len(text) < 80 or is_faq_or_boilerplate(text) or is_statute_stub_chunk(text):
                continue
            header = text[:280].lower()
            if not any(t in header or re.search(rf"case\s+\d+:[^\n]*\b{t}\b", text, re.I) for t in topic_l):
                if not (re.search(r"\bcase\s+\d+:", text, re.I) and any(t in text.lower() for t in topic_l)):
                    continue
            score = case_narrative_score(text)
            for t in topic_l:
                if t in header:
                    score += 5.0
                if re.search(rf"case\s+\d+:[^\n]*\b{t}\b", text, re.I):
                    score += 6.0
            ranked.append(
                (
                    score,
                    {
                        "content": text[:5000],
                        "metadata": meta,
                        "final_score": min(1.4, 0.85 + score * 0.05),
                        "hybrid_score": min(1.4, 0.85 + score * 0.05),
                        "retrieval_mode": "topic_case_lookup",
                    },
                )
            )

    ranked.sort(key=lambda x: -x[0])
    out = [c for _, c in ranked[:top_k]]

    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "T1",
            "case_topic_resolver.py:lookup_topic_case_chunks",
            "topic_case_lookup",
            {
                "topics": topic_l,
                "hit_count": len(out),
                "previews": [(c.get("content") or "")[:100] for c in out[:3]],
            },
        )
    except Exception:
        pass
    # endregion

    return out
