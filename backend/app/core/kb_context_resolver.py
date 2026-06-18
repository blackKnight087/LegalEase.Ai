"""
Retrieval context resolver — topic shift vs conversational continuity.

Rules (general, document-type agnostic):
- Every turn performs fresh vector/keyword retrieval on the user's query (or a
  minimally expanded variant for deictic follow-ups only).
- Session memory must NOT replace retrieval; it may only hint intent for pronouns.
- Topic shifts (new entities, new subject matter) block session bleed.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

_DEICTIC_RE = re.compile(
    r"\b(?:it|this|that|same|above|those|they|there|the\s+(?:case|witness|hearing|"
    r"document|agreement|contract|fir|petition|party|accused|complainant|"
    r"respondent|petitioner))\b",
    re.I,
)

_TOPIC_CLUSTERS: Dict[str, Set[str]] = {
    "family": {
        "custody", "child", "children", "divorce", "maintenance", "alimony",
        "guardianship", "adoption", "matrimonial",
    },
    "property": {
        "property", "lease", "tenant", "landlord", "eviction", "plot", "title",
        "possession", "encumbrance", "registry",
    },
    "criminal_case": {
        "witness", "fir", "accused", "complainant", "hearing", "bail", "remand",
        "charge", "police", "investigation", "cyber", "fraud",
    },
    "corporate": {
        "contract", "nda", "agreement", "indemnity", "confidential", "clause",
        "breach", "termination", "vendor", "license",
    },
    "constitutional": {
        "constitutional", "fundamental", "article", "equality", "liberty",
        "freedom", "remedy", "dignity",
    },
    "civil_litigation": {
        "petitioner", "respondent", "plaintiff", "defendant", "injunction",
        "damages", "decree", "appeal",
    },
    "medical": {
        "patient", "diagnosis", "prescription", "hospital", "treatment", "medical",
    },
}

_STATUTE_RE = re.compile(
    r"\b(?:ipc|bns|crpc|bnss)\s*(?:section\s*)?\d{1,4}[a-z]?|"
    r"\bsection\s+\d{1,4}[a-z]?\b",
    re.I,
)


def _tokenize_meaningful(text: str) -> Set[str]:
    stop = {
        "what", "when", "where", "which", "who", "whom", "whose", "how", "why",
        "the", "and", "for", "from", "with", "your", "this", "that", "about",
        "explain", "describe", "tell", "give", "does", "did", "was", "were",
        "are", "is", "be", "been", "have", "has", "had", "under", "into",
    }
    return {
        w.lower()
        for w in re.findall(r"[A-Za-z]{3,}", text or "")
        if w.lower() not in stop
    }


def cluster_for_tokens(tokens: Set[str]) -> Set[str]:
    """Map tokens to topic cluster names."""
    found: Set[str] = set()
    for name, vocab in _TOPIC_CLUSTERS.items():
        if tokens & vocab:
            found.add(name)
    return found


def extract_query_signals(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    ql = q.lower()
    tokens = _tokenize_meaningful(q)
    entities: List[str] = []
    try:
        from backend.app.core.case_entity_resolver import extract_entity_needles, extract_case_parties

        entities = list(extract_entity_needles(q))
        a, b = extract_case_parties(q)
        for p in (a, b):
            if p and p not in entities:
                entities.append(p)
    except Exception:
        pass

    sections: List[str] = []
    try:
        from conversation_context import extract_sections_from_text

        sections = extract_sections_from_text(q)
    except Exception:
        pass

    return {
        "query": q,
        "tokens": sorted(tokens),
        "clusters": sorted(cluster_for_tokens(tokens)),
        "entities": entities[:8],
        "sections": sections,
        "deictic": bool(_DEICTIC_RE.search(q)),
        "statute": bool(_STATUTE_RE.search(q)),
        "vs_case": bool(re.search(r"\b\w+\s+vs\.?\s+\w+", ql)),
    }


def _session_context_text(session_mem: Dict[str, Any]) -> str:
    parts = [
        str(session_mem.get("last_topic") or ""),
        str(session_mem.get("last_case") or ""),
        str(session_mem.get("last_user_query") or ""),
        str(session_mem.get("last_assistant_summary") or "")[:400],
    ]
    return " ".join(p for p in parts if p)


def detect_topic_shift(
    signals: Dict[str, Any],
    session_mem: Dict[str, Any],
) -> bool:
    """True when the query targets a different subject than session memory."""
    if not session_mem:
        return False
    try:
        from conversation_context import is_meta_follow_up

        if is_meta_follow_up(str(signals.get("query") or "")):
            return False
    except ImportError:
        pass
    q_tokens = set(signals.get("tokens") or [])
    if not q_tokens:
        return False

    sess_text = _session_context_text(session_mem).lower()
    sess_tokens = _tokenize_meaningful(sess_text)
    if not sess_tokens:
        return False

    q_clusters = set(signals.get("clusters") or [])
    s_clusters = cluster_for_tokens(sess_tokens)
    if q_clusters and s_clusters and not (q_clusters & s_clusters):
        return True

    # Named entity in query absent from recent session text → new document/case focus
    _skip_entity = {
        "what", "when", "where", "which", "who", "how", "why", "punishment",
        "penalty", "sentence", "explain", "describe", "tell", "meaning",
    }
    for ent in signals.get("entities") or []:
        el = str(ent).lower()
        if el in _skip_entity or len(el) < 4:
            continue
        if el not in sess_text and el not in sess_tokens:
            if not signals.get("deictic"):
                return True

    # Company / party name in query but not in prior turn (e.g. new NDA vs SecureTech)
    q_raw = str(signals.get("query") or "")
    for comp in re.findall(
        r"\b([A-Z][A-Za-z&][\w&.\s]{1,35}?(?:\s+Pvt\.?\s*Ltd\.?|\s+LLP|\s+Inc\.?)?)",
        q_raw,
    ):
        c = re.sub(r"\s+", " ", comp).strip().lower()
        if len(c) >= 5 and c not in sess_text and c not in sess_tokens:
            if not signals.get("deictic"):
                return True

    # Explicit new statute section vs session section
    q_secs = signals.get("sections") or []
    last_sec = str(session_mem.get("last_section") or "").lower()
    if q_secs and last_sec and q_secs[0].lower() != last_sec:
        return True

    # Strong new topic terms with no overlap to session vocabulary
    overlap = q_tokens & sess_tokens
    substantive = {t for t in q_tokens if len(t) >= 5}
    if substantive and len(overlap) == 0 and not signals.get("deictic"):
        if q_clusters or signals.get("vs_case") or signals.get("entities"):
            return True

    return False


def classify_retrieval_context(
    query: str,
    session_mem: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Plan retrieval vs conversational hints for one turn.

    Returns dict with:
      fresh_retrieval, topic_shift, continuity_allowed,
      retrieval_query, context_hint, signals
    """
    session_mem = dict(session_mem or {})
    signals = extract_query_signals(query)
    topic_shift = detect_topic_shift(signals, session_mem)

    meta_follow_up = False
    try:
        from conversation_context import is_meta_follow_up

        meta_follow_up = is_meta_follow_up(query)
    except ImportError:
        pass

    try:
        from backend.app.services.followup_detector import is_new_legal_query

        fresh = is_new_legal_query(query) or (topic_shift and not meta_follow_up)
    except ImportError:
        fresh = (topic_shift and not meta_follow_up) or bool(signals.get("statute")) or bool(
            signals.get("vs_case")
        )
    if meta_follow_up:
        fresh = False
        topic_shift = False

    deictic = bool(signals.get("deictic"))
    continuity_allowed = (
        (deictic or meta_follow_up)
        and not fresh
        and not topic_shift
        and bool(_session_context_text(session_mem))
    )

    retrieval_query = (query or "").strip()
    context_hint = ""

    if continuity_allowed and session_mem.get("last_topic"):
        context_hint = str(session_mem.get("last_topic") or "")

    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "H2",
            "kb_context_resolver.py:classify_retrieval_context",
            "context_classified",
            {
                "query": retrieval_query[:100],
                "fresh_retrieval": fresh,
                "topic_shift": topic_shift,
                "continuity_allowed": continuity_allowed,
                "clusters": signals.get("clusters"),
                "entities": (signals.get("entities") or [])[:4],
            },
            run_id="retrieval-v1",
        )
    except Exception:
        pass
    # endregion

    return {
        "fresh_retrieval": fresh,
        "topic_shift": topic_shift,
        "continuity_allowed": continuity_allowed,
        "retrieval_query": retrieval_query,
        "context_hint": context_hint,
        "signals": signals,
    }


def effective_session_for_query(
    query: str,
    session_mem: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Session memory usable for follow-up expansion (empty when topic shifted)."""
    ctx = classify_retrieval_context(query, session_mem)
    if ctx.get("fresh_retrieval") or ctx.get("topic_shift"):
        return {}
    return dict(session_mem or {})


def build_retrieval_queries(
    query: str,
    session_mem: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict]] = None,
) -> Tuple[str, str]:
    """
    (primary_retrieval_query, orchestrator_hint_query)

    Primary is the user query, expanded for meta follow-ups (simplify, elaborate, etc.).
    """
    ctx = classify_retrieval_context(query, session_mem, history)
    primary = ctx["retrieval_query"]
    hint = primary
    if ctx.get("continuity_allowed") and ctx.get("context_hint"):
        hint = f"{primary} (context: {ctx['context_hint']})"
    try:
        from conversation_context import enrich_query_with_context, is_meta_follow_up

        if is_meta_follow_up(query):
            expanded = enrich_query_with_context(query, history)
            if expanded and expanded.strip() != query.strip():
                primary = expanded.strip()
                hint = primary
    except ImportError:
        pass
    if primary == query.strip() and session_mem:
        try:
            from backend.app.core.conversation_memory import resolve_follow_up_query

            mem_expanded = resolve_follow_up_query(query, session_mem)
            if mem_expanded and mem_expanded.strip() != query.strip():
                primary = mem_expanded.strip()
                hint = primary
        except Exception:
            pass
    return primary, hint
