"""
Strict legal query parser — section entities MUST win over IPC→BNS replacement logic.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_REPLACEMENT_PHRASES = (
    "what replaced ipc",
    "what replaced crpc",
    "what replaced the ipc",
    "new law replacing ipc",
    "is ipc replaced",
    "ipc replaced by",
    "which law replaced",
    "successor to ipc",
    "ipc to bns",
    "new criminal law",
    "what changed in criminal law",
    "did ipc change",
)

LEGAL_PATTERNS: Dict[str, re.Pattern[str]] = {
    "ipc": re.compile(r"\bipc\s*(\d{1,4}[a-z]?)\b", re.I),
    "bns": re.compile(r"\bbns\s*(\d{1,4}[a-z]?)\b", re.I),
    "section": re.compile(r"\bsection\s*(\d{1,4}[a-z]?)\b", re.I),
    "article": re.compile(r"\barticle\s*(\d{1,4}[a-z]?)\b", re.I),
    "reverse_ipc": re.compile(r"\b(\d{1,4}[a-z]?)\s*ipc\b", re.I),
    "reverse_bns": re.compile(r"\b(\d{1,4}[a-z]?)\s*bns\b", re.I),
}

_COMPARE_RE = re.compile(
    r"\b(compare|comparison|difference|differences|differentiate|distinguish|versus|vs\.?|between)\b",
    re.I,
)
_PUNISH_RE = re.compile(
    r"\b(punishment|penalty|sentence|imprisonment|jail|fine|maximum|minimum)\b",
    re.I,
)
_EXPLAIN_RE = re.compile(
    r"\b(explain|describe|walk me through|break down|tell me about|what is|what's|define|meaning of)\b",
    re.I,
)
_MAPPING_COMPARE_RE = re.compile(
    r"\b(equivalent|counterpart|correspond|mapped|mapping|replace|replaced|successor|old\s+vs\s+new|bns\s+equivalent)\b",
    re.I,
)
_BARE_NUM_PUNISH_RE = re.compile(
    r"\b(\d{1,4}[a-z]?)\s+(?:punishment|penalty|sentence|fine|imprisonment)\b",
    re.I,
)
_PUNISH_BARE_NUM_RE = re.compile(
    r"\b(?:punishment|penalty|sentence|fine|imprisonment|jail\s+term)\s+(?:for|under|of)?\s*(\d{1,4}[a-z]?)\b",
    re.I,
)
_EXPLAIN_BARE_RE = re.compile(r"\bexplain\s+(\d{1,4}[a-z]?)\b", re.I)

_TYPE_TO_LAW = {
    "ipc": "ipc",
    "reverse_ipc": "ipc",
    "bns": "bns",
    "reverse_bns": "bns",
    "section": "ipc",
    "article": "article",
}

_REPLACEMENT_ANSWER_RE = re.compile(
    r"\bhas been replaced by\b|\breplaced by the\b|\bnew criminal law framework\b",
    re.I,
)


def extract_legal_entities(query: str) -> List[Dict[str, Any]]:
    """Extract all IPC/BNS/section/article references anywhere in the query."""
    q = (query or "").strip()
    if not q:
        return []

    ql = q.lower()
    entities: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for label, pattern in LEGAL_PATTERNS.items():
        for match in pattern.finditer(q):
            number = match.group(1).lower()
            key = (label, number)
            if key in seen:
                continue
            seen.add(key)
            entities.append({"type": label, "number": number, "law": _TYPE_TO_LAW.get(label, "ipc")})

    if _COMPARE_RE.search(ql) or len({e["number"] for e in entities}) >= 2:
        try:
            from kb_retrieval import extract_comparison_sections

            for sec in extract_comparison_sections(q):
                key = ("section", sec)
                if key in seen:
                    continue
                seen.add(key)
                law = default_law_for_query(q)
                if re.search(rf"\bbns\s*{re.escape(sec)}\b", ql):
                    law = "bns"
                elif re.search(rf"\bipc\s*{re.escape(sec)}\b", ql):
                    law = "ipc"
                entities.append({"type": "section", "number": sec, "law": law})
        except ImportError:
            for m in re.finditer(
                r"\b(?:and|or|vs\.?|versus|,|between)\s*(\d{1,4}[a-z]?)\b",
                q,
                re.I,
            ):
                number = m.group(1).lower()
                key = ("section", number)
                if key in seen:
                    continue
                seen.add(key)
                entities.append({"type": "section", "number": number, "law": "ipc"})

    em = re.search(r"\bexplain\s+(\d{1,4}[a-z]?)\b", ql)
    if em:
        number = em.group(1).lower()
        key = ("section", number)
        if key not in seen:
            seen.add(key)
            entities.append({"type": "section", "number": number, "law": "ipc"})

    um = re.search(r"\bunder\s+(\d{1,4}[a-z]?)\b", ql)
    if um:
        number = um.group(1).lower()
        key = ("section", number)
        if key not in seen:
            seen.add(key)
            entities.append({"type": "section", "number": number, "law": "ipc"})

    bare = re.match(r"^(?:section\s+)?(\d{1,4}[a-z]?)$", q.strip(), re.I)
    if bare:
        number = bare.group(1).lower()
        key = ("section", number)
        if key not in seen:
            seen.add(key)
            entities.append({"type": "section", "number": number, "law": "ipc"})

    for pat in (_BARE_NUM_PUNISH_RE, _PUNISH_BARE_NUM_RE, _EXPLAIN_BARE_RE):
        for m in pat.finditer(q):
            number = m.group(1).lower()
            key = ("section", number)
            if key not in seen:
                seen.add(key)
                entities.append({"type": "section", "number": number, "law": default_law_for_query(q)})

    return entities


def default_law_for_query(query: str) -> str:
    """Default law when user omits explicit code — IPC for criminal section queries."""
    ql = (query or "").lower()
    try:
        from backend.app.core.constitutional_concept_map import is_constitutional_query

        if is_constitutional_query(query):
            return "article"
    except ImportError:
        pass
    if re.search(r"\bbns\b|\bbharatiya nyaya\b", ql) and not re.search(r"\bipc\b|\bindian penal\b", ql):
        return "bns"
    if re.search(r"\bcrpc\b|\bcriminal procedure\b", ql) and not re.search(r"\bbnss\b", ql):
        return "crpc"
    if re.search(r"\bevidence act\b", ql) and not re.search(r"\bbsa\b", ql):
        return "evidence"
    return "ipc"


def is_mapping_comparison_intent(query: str) -> bool:
    """True only when user asks IPC↔BNS mapping, not same-law section compare."""
    ql = (query or "").lower().strip()
    if not ql:
        return False
    if _MAPPING_COMPARE_RE.search(ql):
        return True
    if is_cross_law_comparison_query(query):
        return True
    return False


def is_same_law_comparison(query: str) -> bool:
    """299 vs 300 → IPC 299 vs IPC 300 (not BNS mapping)."""
    if not is_comparison_query(query):
        return False
    if is_mapping_comparison_intent(query):
        return False
    nums = section_numbers_from_query(query)
    return len(nums) >= 2


def parse_legal_query_structured(query: str) -> Dict[str, Any]:
    """
    Deterministic structured parse before retrieval.

    Examples:
      "307 punishment" → legal_section, ipc, 307, punishment
      "299 vs 300" → comparison, ipc, left=299, right=300
    """
    q = (query or "").strip()
    out: Dict[str, Any] = {
        "query": q,
        "type": "general",
        "law": default_law_for_query(q),
        "sections": [],
        "intent": "general",
        "comparison": None,
    }
    if not q:
        return out

    nums = section_numbers_from_query(q)
    out["sections"] = nums
    out["law"] = default_law_for_query(q)
    for ent in extract_legal_entities(q):
        if ent.get("law"):
            out["law"] = ent["law"]
            break

    route = route_legal_query(q)
    out["intent"] = route

    if route == "comparison" or (len(nums) >= 2 and is_comparison_query(q)):
        out["type"] = "comparison"
        left, right = nums[0], nums[1] if len(nums) > 1 else ""
        out["comparison"] = {
            "law": out["law"],
            "left_section": left,
            "right_section": right,
            "same_law": is_same_law_comparison(q),
            "mapping_mode": is_mapping_comparison_intent(q),
        }
    elif nums and route in ("punishment", "section_explanation", "section_lookup"):
        out["type"] = "legal_section"
        out["section"] = nums[0]
    elif nums:
        out["type"] = "legal_section"
        out["section"] = nums[0]

    return out


def section_numbers_from_query(query: str) -> List[str]:
    """Unique section numbers in query order."""
    nums: List[str] = []
    seen: set[str] = set()
    for ent in extract_legal_entities(query):
        n = ent["number"]
        if n not in seen:
            seen.add(n)
            nums.append(n)
    return nums


def has_legal_section_entities(query: str) -> bool:
    return bool(extract_legal_entities(query))


def is_comparison_query(query: str) -> bool:
    ql = (query or "").lower()
    if _COMPARE_RE.search(ql):
        return True
    if _MAPPING_COMPARE_RE.search(ql):
        return True
    if _EXPLAIN_RE.search(ql) and re.search(r"\b(?:and|&|,)\b", ql):
        return False
    return False


def is_cross_law_comparison_query(query: str) -> bool:
    """IPC section vs BNS equivalent-style comparisons."""
    ql = (query or "").lower()
    if not _COMPARE_RE.search(ql) and "equivalent" not in ql:
        return False
    has_ipc = bool(re.search(r"\bipc\s*\d{1,4}\b", ql) or re.search(r"\b\d{1,4}\s*ipc\b", ql))
    has_bns = bool(re.search(r"\bbns\b", ql))
    return has_ipc and has_bns


def route_legal_query(query: str) -> str:
    """
    Priority legal router — section entities always beat replacement logic.
    Returns: comparison | punishment | section_explanation | section_lookup | law_replacement | general
    """
    q = (query or "").strip()
    if not q:
        return "general"

    entities = extract_legal_entities(q)
    if entities:
        ql = q.lower()
        nums = section_numbers_from_query(q)
        if is_mapping_comparison_intent(q) or is_cross_law_comparison_query(q):
            return "comparison"
        if len(nums) >= 2 and is_comparison_query(q):
            return "comparison"
        if _PUNISH_RE.search(ql):
            return "punishment"
        if _EXPLAIN_RE.search(ql):
            return "section_explanation"
        if re.match(
            r"^(?:\d{1,4}[a-z]?|(?:section|sec\.?)\s*\d{1,4}[a-z]?|(?:ipc|bns)\s*\d{1,4}[a-z]?)$",
            q.strip(),
            re.I,
        ):
            return "section_lookup"
        return "section_explanation"

    if is_law_replacement_intent(q):
        return "law_replacement"
    return "general"


def parse_legal_query(query: str) -> Optional[Dict[str, Any]]:
    """Return structured info for the primary section entity, or None."""
    q = (query or "").strip()
    if not q:
        return None
    if is_law_replacement_intent(q) and not has_legal_section_entities(q):
        return None

    entities = extract_legal_entities(q)
    if not entities:
        return None

    ent = entities[0]
    result = {
        "type": ent["type"],
        "number": ent["number"],
        "law": ent.get("law") or _TYPE_TO_LAW.get(ent["type"], "ipc"),
        "entities": entities,
    }
    log_parse(q, result)
    return result


def is_section_lookup_query(query: str) -> bool:
    """True when ANY legal section entity is present — blocks replacement routing."""
    return has_legal_section_entities(query)


def is_law_replacement_intent(query: str) -> bool:
    """Replacement intent only when NO section numbers exist in the query."""
    q = (query or "").strip()
    if not q:
        return False
    if has_legal_section_entities(q):
        return False

    ql = q.lower()
    if any(phrase in ql for phrase in _REPLACEMENT_PHRASES):
        return True
    if re.search(r"\b(replaced|replacement|successor|new\s+law)\b", ql):
        if re.search(r"\b(ipc|crpc|evidence act|indian penal|bns|bnss|bsa)\b", ql):
            return True
    return False


def log_parse(query: str, parsed: Optional[Dict[str, Any]], intent: str = "") -> None:
    print("Parsed query:", parsed)
    if intent:
        print("Intent selected:", intent)


def is_law_replacement_only_answer(answer: str) -> bool:
    """True when the answer is only IPC→BNS (or similar) mapping text."""
    text = (answer or "").strip()
    if not text or not _REPLACEMENT_ANSWER_RE.search(text):
        return False
    if re.search(
        r"\b(?:ipc|bns)\s*(?:section\s*)?\d{1,4}[a-z]?\b",
        text,
        re.I,
    ) and re.search(
        r"\b(punishment|murder|attempt|imprison|fine|death|life|offence|offense)\b",
        text,
        re.I,
    ):
        return False
    al = text.lower()
    if re.search(r"\b(?:section\s+\d{1,4}|ipc\s+\d{1,4}|bns\s+\d{1,4})\b", al):
        body_without_headers = re.sub(r"^#+\s.*$", "", text, flags=re.M).strip()
        if len(body_without_headers) > 180 and not _REPLACEMENT_ANSWER_RE.search(body_without_headers[:120]):
            return False
    stripped = re.sub(r"^#+\s.*$", "", text, flags=re.M)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if len(stripped) <= 220:
        return True
    replacement_sents = [
        s
        for s in re.split(r"(?<=[.!?])\s+", stripped)
        if _REPLACEMENT_ANSWER_RE.search(s)
    ]
    substantive = [
        s
        for s in re.split(r"(?<=[.!?])\s+", stripped)
        if len(s) > 40
        and not _REPLACEMENT_ANSWER_RE.search(s)
        and re.search(r"\b(punishment|attempt|murder|offence|offense|imprison|fine|years|homicide)\b", s, re.I)
    ]
    return bool(replacement_sents) and not substantive


def answer_satisfies_section_query(query: str, answer: str) -> bool:
    """Reject section/punishment answers that only restate law-replacement mapping."""
    if not is_section_lookup_query(query):
        return True
    if not is_law_replacement_only_answer(answer):
        return True
    return False


def filter_chunks_for_section_query(query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop intro/mapping chunks; keep only chunks with substantive section text."""
    nums = section_numbers_from_query(query)
    if not nums or not chunks:
        return list(chunks or [])
    section = nums[0]

    try:
        from kb_legal_query_rewrite import is_law_mapping_chunk
        from kb_preprocess import extract_section_content, filter_chunks_for_section
        from kb_retrieval import section_in_chunk
    except ImportError:
        return list(chunks)

    scoped = filter_chunks_for_section(chunks, section)
    if scoped:
        return scoped

    kept: List[Dict[str, Any]] = []
    for ch in chunks:
        body = ch.get("content") or ""
        if is_law_mapping_chunk(body) and not section_in_chunk(body, section):
            continue
        isolated = extract_section_content(body, section)
        if isolated and not is_law_replacement_only_answer(isolated):
            kept.append({**ch, "content": isolated})
        elif section_in_chunk(body, section) and not is_law_mapping_chunk(body):
            kept.append(ch)
    return kept
