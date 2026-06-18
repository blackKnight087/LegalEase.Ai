"""
Document-agnostic case narrative extraction — any uploaded case PDF, any party names.

Prevents FAQ lists, index boilerplate, and cross-case bleed from polluting answers.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.case_entity_resolver import (
    _clean_party,
    _is_testing_faq_chunk,
    _sanitize_case_block,
    case_narrative_score,
    extract_case_needles,
    extract_case_title,
    segment_matches_case_needles,
)

_NARRATIVE_MARKERS = re.compile(
    r"\b(?:fir\s+no\.?|complainant|accused|petitioner|respondent|appellant|"
    r"prosecution|defense|defence|witness|court\s+(?:held|observed|discussion)|"
    r"hearing\s*\d*|judgment|judgement|plaintiff|defendant|alleged|registered\s+at)\b",
    re.I,
)
_CASE_BOUNDARY_RE = re.compile(
    r"^(?:Case\s+\d+\s*:|In\s+the\s+matter\s+of\b|"
    r"(?:State|Petitioner|Appellant|Union\s+of\s+India).{0,60}\s+vs\.?\s+)",
    re.I | re.M,
)
_VS_TITLE_RE = re.compile(
    r"(?:Case\s+\d+\s*:\s*)?(.+?)\s+vs\.?\s+(.+?)(?:\s*\(|\s*–|\s*-|\n|$)",
    re.I,
)
_BOILERPLATE_RE = re.compile(
    r"\b(?:this\s+document\s+is\s+designed\s+for\s+testing|kb\s+testing\s+document|"
    r"ocr-safe\s+indexing|follow-up\s+memory|document\s+scoping)\b",
    re.I,
)


def classify_chunk_content_kind(text: str) -> str:
    """
    Index-time / runtime label: case_narrative | faq_list | boilerplate | general.
    """
    body = (text or "").strip()
    if not body or len(body) < 30:
        return "general"
    if _is_testing_faq_chunk(body):
        return "faq_list"
    if _BOILERPLATE_RE.search(body) and not _NARRATIVE_MARKERS.search(body):
        return "boilerplate"
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return "general"
    q_lines = sum(1 for ln in lines if ln.endswith("?") or re.match(r"^[\W]*\?", ln))
    bullet_q = sum(
        1
        for ln in lines
        if ("?" in ln and re.match(r"^[\(\[]?cid:\d+[\]\)]?|^\s*[-•*•]", ln))
        or (ln.startswith("?") and len(ln) < 120)
    )
    if (q_lines >= 2 or bullet_q >= 2) and not _NARRATIVE_MARKERS.search(body):
        return "faq_list"
    if _NARRATIVE_MARKERS.search(body) or _CASE_BOUNDARY_RE.search(body):
        return "case_narrative"
    if re.search(r"\bvs\.?\s+", body, re.I) and len(body) > 200:
        return "case_narrative"
    return "general"


def is_faq_or_boilerplate(text: str) -> bool:
    kind = classify_chunk_content_kind(text)
    return kind in ("faq_list", "boilerplate")


def segment_cases_in_text(text: str) -> List[Dict[str, Any]]:
    """Split full document text into case-sized segments (any naming convention)."""
    body = (text or "").strip()
    if not body:
        return []

    starts: List[int] = [0]
    for m in _CASE_BOUNDARY_RE.finditer(body):
        if m.start() > 0:
            starts.append(m.start())
    starts = sorted(set(starts))

    segments: List[Dict[str, Any]] = []
    for i, pos in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(body)
        seg = body[pos:end].strip()
        if len(seg) < 80:
            continue
        if is_faq_or_boilerplate(seg):
            continue
        title = ""
        tm = _VS_TITLE_RE.search(seg[:400])
        if tm:
            title = f"{tm.group(1).strip()} vs {tm.group(2).strip()}".strip()
        segments.append(
            {
                "text": seg,
                "title": title,
                "start": pos,
                "score_base": case_narrative_score(seg),
            }
        )
    if not segments and body and not is_faq_or_boilerplate(body):
        segments.append({"text": body, "title": "", "start": 0, "score_base": case_narrative_score(body)})
    return segments


def _needle_match_score(segment_text: str, needles: List[str]) -> float:
    tl = (segment_text or "").lower()
    score = 0.0
    for n in needles:
        core = _clean_party(n)
        if not core or core in ("case",):
            continue
        if core in tl:
            score += 3.0
            continue
        tokens = [t for t in core.split() if len(t) > 2]
        if len(tokens) >= 2:
            hit = sum(1 for t in tokens if t in tl)
            score += hit * 1.5
        elif len(tokens) == 1 and tokens[0] in tl:
            score += 1.0
    return score


def select_best_case_segment(
    text: str,
    needles: List[str],
    *,
    min_score: float = 2.0,
) -> str:
    """Pick the single best case narrative block for these party needles."""
    segments = segment_cases_in_text(text)
    if not segments:
        try:
            from backend.app.core.kb_landmark_case import (
                extract_landmark_passage,
                landmark_keys_in_query,
            )

            for key in landmark_keys_in_query(" ".join(needles)):
                blurb = extract_landmark_passage(text, key)
                if blurb and len(blurb) >= 35:
                    return _sanitize_case_block(blurb)
            for n in needles:
                nl = n.lower()
                if nl in ("nirbhaya", "kesavananda", "vishaka", "puttaswamy", "navtej", "shayara"):
                    blurb = extract_landmark_passage(text, nl)
                    if blurb:
                        return _sanitize_case_block(blurb)
        except ImportError:
            pass
        return ""

    ranked: List[Tuple[float, str]] = []
    for seg in segments:
        st = seg["text"]
        total = float(seg.get("score_base") or 0) + _needle_match_score(st, needles)
        if is_faq_or_boilerplate(st):
            total -= 10.0
        ranked.append((total, st))

    ranked.sort(key=lambda x: -x[0])
    if not ranked:
        return ""
    if needles:
        matched = [(s, t) for s, t in ranked if segment_matches_case_needles(t, needles)]
        if matched:
            ranked = matched
    best_score, best_text = ranked[0]
    if best_score < min_score:
        return ""
    return _sanitize_case_block(best_text)


def _dedupe_repeated_fragments(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"(?:\bFIR\s+No\.?\s*){2,}", "FIR No. ", t, flags=re.I)
    t = re.sub(r"\b(\w+(?:\s+\w+){0,4})\s+\1\b", r"\1", t, flags=re.I)
    return t.strip()


def _extract_labeled_section(narrative: str, label_pattern: str, max_len: int = 900) -> str:
    m = re.search(
        rf"(?:{label_pattern})\s*[:\-–]?\s*(.+?)(?=\n[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*[:\-]|$)",
        narrative,
        re.I | re.S,
    )
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())[:max_len]
    return ""


def answer_fact_from_narrative(question: str, narrative: str) -> str:
    """Direct wh-answers (who sought custody, who filed, etc.) from narrative text."""
    q = (question or "").lower()
    body = _sanitize_case_block((narrative or "").strip())
    if not body:
        return ""
    patterns: List[str] = []
    if "who" in q and "custody" in q:
        patterns = [
            r"([^.]{0,120}?\bsought[^.]{0,60}custody[^.]{0,80})",
            r"([^.]{0,120}?custody[^.]{0,40}(?:sought|filed|claimed|petitioned)[^.]{0,80})",
            r"(?:petitioner|appellant|father|mother|wife|husband|guardian)[^.]{0,100}custody[^.]{0,60}",
        ]
    elif re.search(r"\bwho\b", q):
        patterns = [
            r"([^.]{0,120}?\b(?:sought|filed|alleged|claimed|petitioned)[^.]{0,120})",
        ]
    for pat in patterns:
        m = re.search(pat, body, re.I)
        if m:
            fact = _dedupe_repeated_fragments(m.group(1) if m.lastindex else m.group(0))
            if len(fact) > 25:
                return f"## Answer\n\n{fact.strip()}\n"
    return ""


def build_structured_case_answer(question: str, narrative: str) -> str:
    """Build markdown sections only from extracted narrative — no hardcoded case facts."""
    body = _dedupe_repeated_fragments(_sanitize_case_block((narrative or "").strip()))
    if not body:
        return ""

    try:
        from kb_query_types import is_document_fact_query

        if is_document_fact_query(question):
            direct = answer_fact_from_narrative(question, body)
            if direct:
                return direct
    except ImportError:
        pass

    title = extract_case_title(question)
    if title and title.lower() not in body.lower()[:150]:
        if not re.search(r"\bvs\.?\b", body[:200], re.I):
            body = f"## {title}\n\n{body}"

    sections: List[str] = []
    if not body.lstrip().startswith("##"):
        sections.append("## Overview")
    sections.append(body)

    parties = _extract_labeled_section(
        body,
        r"(?:^|\n)\s*(?:Parties)\s*[:\-–]",
    )
    if not parties or re.search(r"(?:FIR\s+No\.?\s*){2,}", parties, re.I):
        parties = ""
    fir = _extract_labeled_section(body, r"(?:^|\n)\s*FIR\s+No\.?\s*[:\-–]?\s*\d")
    if parties and len(parties) > 20 and "fir no" not in parties.lower()[:40]:
        sections.extend(["", "### Parties", parties])
    if fir and fir.lower() not in body.lower()[:400] and len(fir) > 15:
        sections.extend(["", "### FIR", fir])

    hearings: List[str] = []
    for hm in re.finditer(
        r"(Hearing\s*\d+[^:\n]*)\s*[:\-]?\s*([^\n]+(?:\n(?!Hearing\s*\d|Case\s*\d)[^\n]+)*)",
        body,
        re.I,
    ):
        htitle = hm.group(1).strip()
        hbody = re.sub(r"\s+", " ", hm.group(2).strip())[:700]
        if hbody and len(hbody) > 30:
            hearings.append(f"### {htitle}\n{hbody}")

    want_detail = bool(
        re.search(
            r"\b(?:detailed|detail|full|in[- ]?depth|hearing|summarize|explain|explanation)\b",
            question,
            re.I,
        )
        or len(body) < 900
    )
    if want_detail and hearings:
        sections.extend(["", "## Hearings"] + hearings[:4])
    return "\n".join(sections).strip()


def collect_text_from_chunks(chunks: List[Dict[str, Any]]) -> str:
    """Merge chunk bodies in stable order for segment analysis."""
    parts: List[str] = []
    seen: set[str] = set()
    for ch in chunks or []:
        meta = ch.get("metadata") or {}
        if meta.get("content_kind") in ("faq_list", "boilerplate"):
            continue
        t = (ch.get("content") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        parts.append(t)
    return "\n\n".join(parts)


def filter_case_chunks(chunks: List[Dict[str, Any]], needles: List[str]) -> List[Dict[str, Any]]:
    """Drop FAQ/boilerplate; prefer case narrative chunks."""
    from backend.app.core.case_entity_resolver import chunk_matches_case

    out: List[Dict[str, Any]] = []
    for ch in chunks or []:
        content = ch.get("content") or ""
        meta = ch.get("metadata") or {}
        kind = meta.get("content_kind") or classify_chunk_content_kind(content)
        if kind in ("faq_list", "boilerplate"):
            continue
        if is_faq_or_boilerplate(content):
            continue
        if needles and not chunk_matches_case(ch, needles):
            continue
        ch = dict(ch)
        ch["metadata"] = {**meta, "content_kind": kind}
        out.append(ch)
    out.sort(
        key=lambda c: -(
            case_narrative_score(c.get("content") or "")
            + (2.0 if (c.get("metadata") or {}).get("content_kind") == "case_narrative" else 0)
        )
    )
    return out


def build_entity_document_answer(question: str, chunks: List[Dict[str, Any]]) -> str:
    """Answer person/company-focused queries with one scoped narrative block."""
    from backend.app.core.case_entity_resolver import extract_entity_needles, is_entity_focus_query

    if not is_entity_focus_query(question):
        return ""
    needles = extract_entity_needles(question) or extract_case_needles(question)
    if not needles:
        return ""
    return build_case_answer_from_chunks(question, chunks)


def build_case_answer_from_chunks(question: str, chunks: List[Dict[str, Any]]) -> str:
    """
    Permanent case Q&A path: one isolated narrative, structured sections, any party names.
    """
    needles = extract_case_needles(question)
    if not needles:
        return ""

    filtered = filter_case_chunks(chunks, needles)
    if not filtered:
        filtered = [c for c in (chunks or []) if not is_faq_or_boilerplate(c.get("content") or "")][:5]

    combined = collect_text_from_chunks(filtered)
    if not combined:
        return ""

    try:
        from backend.app.core.case_topic_resolver import (
            is_topic_case_query,
            is_statute_stub_chunk,
        )

        _topic_case = is_topic_case_query(question)
    except ImportError:
        _topic_case = False
        is_statute_stub_chunk = lambda _t: False  # type: ignore

    narrative = select_best_case_segment(combined, needles)
    if narrative and is_statute_stub_chunk(narrative):
        narrative = ""
    if _topic_case and narrative and case_narrative_score(narrative) < 1.5:
        narrative = ""
    if not narrative or case_narrative_score(narrative) < 1.0:
        from backend.app.core.case_entity_resolver import extract_case_block

        for ch in filtered[:6]:
            block = extract_case_block(ch.get("content") or "", needles, max_chars=4000)
            if block and case_narrative_score(block) >= case_narrative_score(narrative):
                narrative = block

    if narrative and len(narrative.strip()) < 220:
        extra = collect_text_from_chunks(filtered[1:8])
        if extra:
            expanded = select_best_case_segment(
                f"{narrative}\n\n{extra}", needles, min_score=1.0
            )
            if expanded and len(expanded) > len(narrative):
                narrative = expanded

    if not narrative:
        return ""

    if needles and not segment_matches_case_needles(narrative, needles):
        return ""

    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "CASE",
            "case_narrative_engine.py:build_case_answer_from_chunks",
            "narrative_selected",
            {
                "query": question[:80],
                "narrative_len": len(narrative),
                "narrative_score": case_narrative_score(narrative),
                "has_cid": "(cid:" in narrative,
                "needles": needles[:4],
            },
            run_id="permanent-case",
        )
    except Exception:
        pass
    # endregion

    return build_structured_case_answer(question, narrative)
