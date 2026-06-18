"""
Extract case party names and titles from natural-language queries.

Supports: State vs Rohan Mehta, Priya Verma vs Rajesh Verma, Explain X v Y case.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

_VS_RE = re.compile(
    r"\b(?:explain|describe|summarize|what\s+happened\s+in|tell\s+me\s+about)?\s*"
    r"(?:the\s+)?(.+?)\s+vs\.?\s+(.+?)(?:\s+case)?\b",
    re.I,
)
_CASE_CUE_RE = re.compile(
    r"\b(?:case|judgment|judgement|verdict|ruling|petition|fir|hearing)\b|"
    r"\b(?:nirbhaya|kesavananda|vishaka|puttaswamy)\b|"
    r"\b\w+\s+vs\.?\s+\w+",
    re.I,
)
_LANDMARK_KEYS = ("nirbhaya", "kesavananda", "vishaka", "puttaswamy", "navtej", "shayara")
_PARTY_SUFFIX_RE = re.compile(
    r"\s+(?:detailed|detail|briefly|brief|summary|summarize|full|overview|"
    r"explain|describe|case|matter|judgment|judgement|hearing\s*\d*)\s*$",
    re.I,
)


def _clean_party(name: str) -> str:
    n = (name or "").strip().rstrip("?.")
    return _PARTY_SUFFIX_RE.sub("", n).strip().lower()


def _is_testing_faq_chunk(body: str) -> bool:
    bl = (body or "").lower()
    # If the chunk contains real case narrative markers, don't classify it as an FAQ list.
    # Some PDFs end up producing a single chunk that contains BOTH the narrative and
    # "Suggested KB Testing Questions" (cid:127 bullets).
    has_narrative = any(
        k in bl
        for k in (
            "fir no",
            "fir ",
            "hearing",
            "complainant",
            "accused",
            "petitioner",
            "respondent",
            "witness",
            "court observation",
        )
    )
    if re.search(r"suggested\s+(?:kb\s+)?testing\s+questions", bl):
        return not has_narrative
    if "(cid:127)" in bl and "fir no" not in bl and "fir " not in bl:
        return True
    if bl.count("(cid:127)") >= 2:
        return not has_narrative
    return False


def _strip_query_noise(query: str) -> str:
    q = (query or "").strip()
    q = re.sub(r"^[\s:;,.]+", "", q)
    q = re.sub(r"^(?:#+\s+[^\n]+\n+)+", "", q).strip()
    return q


def is_case_style_query(query: str) -> bool:
    q = _strip_query_noise(query)
    if not q:
        return False
    if _VS_RE.search(q):
        return True
    if re.search(r"\b\w+\s+vs\.?\s+\w+", q, re.I):
        return True
    return bool(_CASE_CUE_RE.search(q))


def extract_case_parties(query: str) -> Tuple[str, str]:
    """Return (party_a, party_b) lowercased, may be empty."""
    q = _strip_query_noise(query)
    m = re.search(r"\bvs\.?\s+(.+?)(?:\s+case\b)?\s*$", q, re.I)
    if not m:
        m = _VS_RE.search(q)
        if not m:
            return "", ""
        a = re.sub(
            r"^(?:explain|describe|summarize|the)\s+",
            "",
            m.group(1).strip(),
            flags=re.I,
        )
        b = _clean_party(m.group(2))
        return _clean_party(a), b
    b = _clean_party(m.group(1))
    left = q[: m.start()].strip()
    left = re.sub(
        r"^(?:explain|describe|summarize|what\s+happened\s+in|tell\s+me\s+about)\s+",
        "",
        left,
        flags=re.I,
    )
    left = re.sub(r"^the\s+", "", left, flags=re.I)
    return _clean_party(left), b


_COMPANY_RE = re.compile(
    r"\b([A-Z][\w&.\s]{2,40}?(?:Pvt\.?\s*Ltd\.?|Pte\.?\s*Ltd\.?|Limited|LLP|Inc\.?|Corporation))\b",
    re.I,
)
_PERSON_RE = re.compile(r"\b([A-Z][a-z]{2,20})\s+([A-Z][a-z]{2,20})\b")
_SINGLE_NAME_STOPWORDS = {
    "state",
    "court",
    "hearing",
    "fir",
    "case",
    "petitioner",
    "respondent",
    "accused",
    "prosecution",
    "defense",
    "defence",
    "union",
    "india",
    "supreme",
    "high",
    "district",
}


def extract_entity_needles(query: str) -> List[str]:
    """Person / company names in short KB queries (no vs required)."""
    q = (query or "").strip()
    needles: List[str] = []
    for m in _COMPANY_RE.finditer(q):
        name = _clean_party(m.group(1))
        if len(name) >= 4 and name not in needles:
            needles.append(name)
        for token in name.replace(".", " ").split():
            if len(token) >= 5 and token not in needles:
                needles.append(token)
    for m in _PERSON_RE.finditer(q):
        full = _clean_party(f"{m.group(1)} {m.group(2)}")
        if full and full not in needles:
            needles.append(full)
        for token in (m.group(1).lower(), m.group(2).lower()):
            if len(token) >= 4 and token not in needles:
                needles.append(token)
    # Support single-token person/company-like queries (e.g. "Rahul") only when the
    # user actually typed one word — never strip spaces from "What punishment?" etc.
    words = [w for w in re.findall(r"[A-Za-z]{3,}", q)]
    if len(words) == 1:
        cand = words[0].strip().lower()
        if cand and cand not in _SINGLE_NAME_STOPWORDS and cand not in needles:
            needles.append(cand)
    return needles[:8]


def is_entity_focus_query(query: str) -> bool:
    """Short queries about a person or company in uploaded case/contract PDFs."""
    q = _strip_query_noise(query)
    if not q or len(q) > 160:
        return False
    try:
        from backend.app.core.universal_kb import is_statute_focused_query

        if is_statute_focused_query(q):
            return False
    except Exception:
        pass
    try:
        from kb_query_types import is_document_fact_query

        if is_document_fact_query(q):
            return True
    except ImportError:
        pass
    if is_case_style_query(q):
        return True
    needles = extract_entity_needles(q)
    if not needles:
        return False
    ok = len(q.split()) <= 12
    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "ENT",
            "case_entity_resolver.py:is_entity_focus_query",
            "entity_focus_decision",
            {
                "query": q[:60],
                "needles": needles[:6],
                "token_count": len(q.split()),
                "ok": ok,
            },
        )
    except Exception:
        pass
    # endregion
    return ok


def extract_case_needles(query: str) -> List[str]:
    """Search needles for docstore / chunk filtering."""
    try:
        from backend.app.core.kb_case_context_lock import normalize_case_query

        q = normalize_case_query(query)
    except ImportError:
        q = (query or "").strip()
    try:
        from backend.app.core.case_topic_resolver import (
            extract_topic_case_needles,
            is_topic_case_query,
        )

        if is_topic_case_query(q):
            topics = extract_topic_case_needles(q)
            if topics:
                return topics
    except ImportError:
        pass
    ql = q.lower()
    needles: List[str] = []
    a, b = extract_case_parties(q)
    for name in (a, b):
        name = name.strip()
        if len(name) >= 3 and name not in needles:
            needles.append(name)
    if b and len(b) > 4 and b not in needles:
        needles.append(b)
    for name in (a, b):
        for token in name.split():
            if len(token) >= 4 and token not in needles:
                needles.append(token)
    for key in _LANDMARK_KEYS:
        if key in ql:
            needles.append(key)
    if re.search(r"\b(case|judgment|judgement)\b", ql) and not needles:
        needles.append("case")
    for n in extract_entity_needles(q):
        if n not in needles:
            needles.append(n)
    if not a and not b:
        for tok in re.findall(r"[a-z]{5,}", ql):
            if tok in _SINGLE_NAME_STOPWORDS or tok in needles:
                continue
            needles.append(tok)
    return needles[:8]


def extract_case_title(query: str) -> str:
    a, b = extract_case_parties(query)
    if a and b:
        return f"{a.title()} vs {b.title()}"
    for key in _LANDMARK_KEYS:
        if key in (query or "").lower():
            return " ".join(w.capitalize() for w in key.split()) + " Case"
    return "Case summary"


def _primary_party_needles(needles: List[str]) -> List[str]:
    out: List[str] = []
    for n in needles:
        core = _clean_party(n)
        if not core or core in ("case",) or len(core) < 4:
            continue
        if core not in out:
            out.append(core)
    return out[:4]


def _name_in_text(body: str, name: str) -> bool:
    n = _clean_party(name)
    if not n or len(n) < 3:
        return False
    if n in body:
        return True
    tokens = [t for t in n.split() if len(t) > 2]
    return len(tokens) >= 2 and all(t in body for t in tokens)


def segment_matches_case_needles(text: str, needles: List[str]) -> bool:
    """Require both caption parties when the query names two sides (not bare 'State vs X')."""
    body = (text or "").lower()
    primary = _primary_party_needles(needles)
    state_labels = frozenset({"state", "union of india"})
    if len(primary) >= 2 and primary[0] in state_labels:
        return _name_in_text(body, primary[1])
    if len(primary) >= 2:
        return all(_name_in_text(body, n) for n in primary[:2])
    if len(primary) == 1:
        return _name_in_text(body, primary[0])
    if "state" in [n.lower() for n in needles] and " vs " in body:
        for n in needles:
            if n.lower() in ("case", "state"):
                continue
            if _name_in_text(body, n):
                return True
    return any(_name_in_text(body, n) for n in needles if n not in ("case",))


def chunk_matches_case(chunk: dict, needles: List[str]) -> bool:
    if not needles:
        return False
    try:
        from backend.app.core.kb_landmark_case import (
            chunk_supports_landmark,
            landmark_keys_in_query,
        )

        keys = landmark_keys_in_query(" ".join(needles))
        if keys:
            return chunk_supports_landmark(chunk, keys[0])
    except ImportError:
        pass
    try:
        from backend.app.core.case_topic_resolver import (
            chunk_matches_topic_case,
            is_topic_only_needles,
        )

        if is_topic_only_needles(needles):
            return chunk_matches_topic_case(chunk, needles)
    except ImportError:
        pass
    body = (chunk.get("content") or "").lower()
    if _is_testing_faq_chunk(body):
        return False
    try:
        from backend.app.core.case_topic_resolver import is_statute_stub_chunk

        if is_statute_stub_chunk(chunk.get("content") or ""):
            return False
    except ImportError:
        pass
    return segment_matches_case_needles(body, needles)


def _sanitize_case_block(text: str) -> str:
    """Remove PDF FAQ bullets and testing sections from a case excerpt."""
    cleaned: List[str] = []
    for line in (text or "").splitlines():
        ll = line.strip().lower()
        if "suggested kb testing" in ll or "suggested questions" in ll:
            break
        if re.match(r"^\(cid:\d+\)", line.strip()):
            continue
        if re.match(r"^[-•*]\s+", line.strip()) and "?" in line and "fir" not in ll:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def case_narrative_score(text: str) -> float:
    """Higher = more likely a real case narrative (not FAQ list)."""
    tl = (text or "").lower()
    score = 0.0
    if "fir no" in tl or re.search(r"\bfir\b", tl):
        score += 4.0
    if "complainant" in tl or "accused" in tl or "petitioner" in tl:
        score += 2.0
    if "hearing" in tl or "court observation" in tl:
        score += 2.0
    if "witness" in tl or "prosecution" in tl or "defense" in tl:
        score += 1.0
    if re.search(r"\bcase\s+\d+:", tl):
        score += 1.5
    if _is_testing_faq_chunk(tl):
        score -= 8.0
    if "(cid:127)" in tl:
        score -= 6.0
    return score


def extract_case_block(text: str, needles: List[str], *, max_chars: int = 2200) -> str:
    """Isolate one case narrative from a chunk or page."""
    body = (text or "").strip()
    if not body:
        return ""
    lines = body.split("\n")
    start = -1
    norm_needles = [_clean_party(n) for n in needles if len(n) > 2]

    def _line_matches(line: str) -> bool:
        ll = line.lower()
        return any(n in ll for n in norm_needles if len(n) > 3) or any(
            all(t in ll for t in n.split() if len(t) > 2)
            for n in norm_needles
            if len(n.split()) >= 2
        )

    for i, line in enumerate(lines):
        ll = line.lower()
        if _line_matches(line):
            if re.search(r"\bcase\s+\d+:", ll) or " vs " in ll or "fir no" in ll:
                start = i
                break
    if start < 0:
        for i, line in enumerate(lines):
            if _line_matches(line):
                start = i
                break
    if start < 0:
        return _sanitize_case_block(body[:max_chars])

    out: List[str] = []
    for line in lines[start:]:
        ll = line.strip().lower()
        if "suggested kb testing" in ll or "suggested questions" in ll:
            break
        if re.match(r"^\(cid:\d+\)", line.strip()):
            break
        if re.match(r"^Case\s+\d+:", line.strip(), re.I) and out and len(out) > 3:
            break
        out.append(line)
        if sum(len(x) for x in out) > max_chars:
            break
    block = _sanitize_case_block("\n".join(out).strip())
    return block[:max_chars] if block else _sanitize_case_block(body[:max_chars])
