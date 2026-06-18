"""
Map natural-language offence phrases to IPC/BNS sections for multi-hop comparisons.

Example: "difference between murder and attempt to murder" → IPC 300 vs IPC 307.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Longest / most specific patterns first
_OFFENCE_TO_SECTION: List[Tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\battempt\s+to\s+commit\s+culpable\s+homicide\b", re.I), "308", "attempt culpable homicide"),
    (re.compile(r"\battempt\s+to\s+murder\b", re.I), "307", "attempt to murder"),
    (re.compile(r"\battempt\s+to\s+kill\b", re.I), "307", "attempt to murder"),
    (re.compile(r"\bculpable\s+homicide\b", re.I), "299", "culpable homicide"),
    (re.compile(r"\bmurder\b", re.I), "300", "murder"),
    (re.compile(r"\bcheating\b", re.I), "420", "cheating"),
    (re.compile(r"\btheft\b", re.I), "378", "theft"),
    (re.compile(r"\brobbery\b", re.I), "392", "robbery"),
    (re.compile(r"\brape\b", re.I), "376", "rape"),
    (re.compile(r"\battempt\b", re.I), "307", "attempt"),
]

_COMPARE_SPLIT_RE = re.compile(
    r"(?:what\s+is\s+the\s+)?(?:difference|compare|comparison|distinguish|differentiate|contrast)"
    r"\s+(?:between|of)\s+(.+?)\s+and\s+(.+?)\s*\??\s*$",
    re.I,
)

_VS_SPLIT_RE = re.compile(
    r"(.+?)\s+(?:vs\.?|versus)\s+(.+?)\s*\??\s*$",
    re.I,
)


def _primary_law(query: str) -> str:
    ql = (query or "").lower()
    if re.search(r"\bbns\b", ql):
        return "BNS"
    return "IPC"


def resolve_offence_phrase(phrase: str, *, law: str = "IPC") -> Optional[Dict[str, str]]:
    """Return {type, section, concept} for a phrase like 'attempt to murder'."""
    p = (phrase or "").strip().rstrip("?.")
    if not p:
        return None
    for pat, sec, label in _OFFENCE_TO_SECTION:
        if pat.search(p):
            ent: Dict[str, str] = {"type": law, "section": sec, "concept": label}
            if law == "BNS":
                try:
                    from kb_legal_mapping import map_section

                    mapped = map_section("IPC", sec)
                    if mapped:
                        ent["section"] = mapped
                        ent["mirrored_ipc"] = sec
                except Exception:
                    pass
            return ent
    return None


def extract_conceptual_comparison_entities(query: str) -> List[Dict[str, str]]:
    """
    Infer typed entities from offence language (no section numbers in query).

    "What is the difference between murder and attempt to murder?"
    → [{IPC, 300}, {IPC, 307}]
    """
    q = (query or "").strip()
    if not q:
        return []

    law = _primary_law(q)
    left_p = right_p = ""

    m = _COMPARE_SPLIT_RE.search(q)
    if m:
        left_p, right_p = m.group(1).strip(), m.group(2).strip()
    else:
        m2 = _VS_SPLIT_RE.search(q)
        if m2 and re.search(r"\b(difference|compare|versus|vs)\b", q, re.I):
            left_p, right_p = m2.group(1).strip(), m2.group(2).strip()

    if not left_p or not right_p:
        return []

    left_p = re.sub(r"^(?:the|a|an)\s+", "", left_p, flags=re.I)
    right_p = re.sub(r"^(?:the|a|an)\s+", "", right_p, flags=re.I)

    entities: List[Dict[str, str]] = []
    seen: set[str] = set()
    for phrase in (left_p, right_p):
        ent = resolve_offence_phrase(phrase, law=law)
        if not ent:
            continue
        key = f"{ent['type']}:{ent['section']}"
        if key in seen:
            continue
        seen.add(key)
        entities.append(ent)

    # region agent log
    if entities:
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "OFF",
                "legal_offence_resolver.py:extract_conceptual_comparison_entities",
                "conceptual_comparison",
                {
                    "query": q[:120],
                    "entities": [f"{e.get('type')}:{e.get('section')}" for e in entities],
                    "concepts": [e.get("concept", "") for e in entities],
                },
            )
        except Exception:
            pass
    # endregion

    return entities


def is_conceptual_comparison_query(query: str) -> bool:
    return len(extract_conceptual_comparison_entities(query)) >= 2
