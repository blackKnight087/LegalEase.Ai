"""Structured matter Q&A — synthesis without raw document dumps."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_WITNESS_BLOCK = re.compile(
    r"WITNESS\s+STATEMENT\s*[–\-]\s*([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\r?\n([^\r\n]+)",
    re.I | re.M,
)
_TIMELINE_LINE = re.compile(
    r"^(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\s*[|\-–]\s*(.+)$",
    re.I | re.M,
)
_HEARING_BLOCK = re.compile(
    r"HEARING\s+NOTES?\s*\n(.*?)(?=\n(?:WITNESS|TIMELINE|EVIDENCE|CASE)|\Z)",
    re.I | re.S,
)


def classify_matter_intent(query: str) -> str:
    q = (query or "").lower()
    try:
        from backend.app.core.llm_orchestrator import classify_fast
        from backend.app.core.llm_task_router import router_enabled

        if router_enabled() and len((query or "").strip()) > 12:
            llm = classify_fast(query)
            if llm.get("source") != "skipped_same_model":
                subtype = (llm.get("subtype") or "").lower()
                intent_map = {
                    "witness": "witness",
                    "evidence": "evidence",
                    "hearing": "hearing",
                    "timeline": "timeline",
                    "chronolog": "timeline",
                    "contradict": "contradiction",
                    "summary": "summary",
                }
                for key, intent in intent_map.items():
                    if key in subtype or key in (llm.get("intent") or "").lower():
                        return intent
    except Exception:
        pass
    if any(w in q for w in ("witness", "statement", "deponent", "testimony")):
        return "witness"
    if any(w in q for w in ("evidence", "cctv", "forensic", "exhibit")):
        return "evidence"
    if any(w in q for w in ("hearing", "next date", "adjourn", "court date")):
        return "hearing"
    if any(w in q for w in ("timeline", "chronolog", "sequence of events", "when did")):
        return "timeline"
    if any(w in q for w in ("ipc", "section", "bns", "statute", "offence", "offense")):
        return "law"
    if any(w in q for w in ("accused", "defendant", "who is charged")):
        return "accused"
    if any(w in q for w in ("victim", "deceased", "complainant")):
        return "victim"
    if any(w in q for w in ("summary", "overview", "what happened", "facts")):
        return "summary"
    if any(w in q for w in ("contradict", "inconsist", "conflict")):
        return "contradiction"
    return "general"


def _load_text(user_id: str, matter_id: str) -> str:
    from backend.app.core.matter_autopilot import load_matter_doc_texts

    chunks = load_matter_doc_texts(user_id, matter_id)
    return "\n\n".join(c.get("content", "") for c in chunks)


def _answer_witness(text: str) -> Optional[str]:
    blocks = list(_WITNESS_BLOCK.finditer(text))
    if not blocks:
        return None
    lines = ["**Witness statements found**\n"]
    seen_names: set = set()
    idx = 0
    for m in blocks:
        name = " ".join(w.capitalize() for w in m.group(1).split())
        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        idx += 1
        body = re.sub(r"\s+", " ", m.group(2).strip())[:400]
        lines.append(f"{idx}. **{name}**\n   {body}\n")
    lines.append(
        "\n*Observation:* Review whether statements are consistent on time, location, and identification."
    )
    return "\n".join(lines)


def _answer_timeline(text: str) -> Optional[str]:
    events: List[Tuple[str, str]] = []
    for m in _TIMELINE_LINE.finditer(text):
        events.append((m.group(1).strip(), m.group(2).strip()[:200]))
    if len(events) < 2:
        return None
    lines = ["**Case chronology**\n"]
    for dt, title in events[:12]:
        lines.append(f"- **{dt}** — {title}")
    return "\n".join(lines)


def _answer_law(text: str) -> Optional[str]:
    nums = sorted(set(re.findall(r"\bIPC\s*(\d{1,4})\b", text, re.I)))
    if not nums:
        nums = sorted(set(re.findall(r"\bSection\s*(\d{1,4})\b", text, re.I)))
    if not nums:
        return None
    return "**Applicable sections**\n\n" + "\n".join(f"- IPC {n}" for n in nums[:15])


def _answer_party(text: str, role: str) -> Optional[str]:
    pat = rf"^{role}\s*\n\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,3}})\s*$"
    m = re.search(pat, text[:4000], re.I | re.M)
    if m:
        return f"**{role.title()}:** {m.group(1).strip()}"
    return None


def _answer_hearing(text: str) -> Optional[str]:
    m = _HEARING_BLOCK.search(text)
    if not m:
        return None
    block = m.group(1)
    dates = re.findall(
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
        block,
        re.I,
    )
    court = ""
    cm = re.search(r"Court\s*\n\s*([^\n]+)", text[:3000], re.I)
    if cm:
        court = cm.group(1).strip()
    lines = ["**Hearings**\n"]
    for d in dates[:4]:
        lines.append(f"- **{d}**" + (f" — {court}" if court else ""))
    nh = re.search(r"Next Hearing\s*\n\s*(\d{1,2}\s+\w+\s+\d{4})", text[:4000], re.I)
    if nh:
        lines.append(f"\n**Next hearing:** {nh.group(1)}")
    return "\n".join(lines) if len(lines) > 1 else None


def _answer_evidence(text: str) -> Optional[str]:
    from backend.app.core.matter_evidence import _dedupe_evidence, _regex_extract_evidence

    items = _dedupe_evidence(_regex_extract_evidence(text))
    if not items:
        return None
    lines = ["**Evidence identified**\n"]
    for i, it in enumerate(items[:12], 1):
        lines.append(
            f"{i}. **{it.get('title', 'Evidence')}** ({it.get('category', 'other')}) — "
            f"{(it.get('notes') or '')[:200]}"
        )
    return "\n".join(lines)


def answer_matter_query(user_id: str, matter_id: str, query: str) -> Optional[str]:
    """Return a structured answer when we can parse the matter text; else None for RAG fallback."""
    text = _load_text(user_id, matter_id)
    if len(text) < 80:
        return None

    intent = classify_matter_intent(query)
    handlers = {
        "witness": lambda: _answer_witness(text),
        "timeline": lambda: _answer_timeline(text),
        "law": lambda: _answer_law(text),
        "accused": lambda: _answer_party(text, "Accused"),
        "victim": lambda: _answer_party(text, "Victim"),
        "hearing": lambda: _answer_hearing(text),
        "evidence": lambda: _answer_evidence(text),
    }
    fn = handlers.get(intent)
    if fn:
        ans = fn()
        if ans:
            return _annotate_matter(ans, text)

    if intent == "summary":
        accused = _answer_party(text, "Accused")
        victim = _answer_party(text, "Victim")
        law = _answer_law(text)
        parts = [p for p in (victim, accused, law) if p]
        if parts:
            ans = "**Case summary (from documents)**\n\n" + "\n\n".join(parts)
            return _annotate_matter(ans, text)

    return None


def _annotate_matter(answer: str, matter_text: str) -> str:
    try:
        from backend.app.core.citation_verifier import annotate_matter_legal_claims

        return annotate_matter_legal_claims(answer, matter_text)
    except Exception:
        return answer
