"""
Answer orchestration: intent → retrieve context → synthesize → format.

Premium legal intelligence: human, conversational, strictly document-grounded.
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from citation_formatter import polish_kb_response, strip_inline_citation_markers
from intent_engine import IntentProfile, QueryIntent, classify_intent
from llms import get_generator
from prompts import NOT_FOUND_PHRASE

NOT_FOUND = NOT_FOUND_PHRASE

# Canonical section subtitles (query section wins over keyword noise in chunks)
SECTION_SUBTITLES = {
    "299": "Culpable Homicide",
    "300": "Murder",
    "302": "Punishment for Murder",
    "307": "Attempt to Murder",
    "304a": "Causing Death by Negligence",
    "304A": "Causing Death by Negligence",
}


def statute_section_heading(section: str, law: str = "IPC") -> str:
    """Consistent section title with optional well-known subtitle."""
    sec_u = (section or "").upper()
    law_u = (law or "IPC").upper()
    subtitle = SECTION_SUBTITLES.get(sec_u) or SECTION_SUBTITLES.get((section or "").lower(), "")
    heading = f"## {law_u} Section {sec_u}"
    if subtitle:
        heading += f" — {subtitle}"
    return heading

_PAGE_DUMP_RE = re.compile(r"\[\s*Page\s*\d+\s*\]", re.I)
_MAPPING_CHART_RE = re.compile(
    r"(?:ipc\s+section\s+bns\s+section|topic\s*/?\s*usage|"
    r"ipc\s+\d{1,4}\s+bns\s+\d{1,4})",
    re.I,
)
_RAW_SOURCE_RE = re.compile(
    r"(?i)Source:\s*l[_\s]*knowledge|Source:\s*legal_knowledge[^\n]*\.pdf[^\n]*",
)

_SPAM_HEADINGS = re.compile(
    r"^#{1,3}\s*(Main Answer|Key Findings|Supporting Evidence|Executive Summary|"
    r"Legal Basis|Practical Guidance|Caveats|Relevant excerpts|LEGALEASE)\s*$",
    re.I | re.M,
)

LEGALEASE_SYSTEM_PROMPT = """You are LegalEase AI.

Answer ONLY using the uploaded legal documents in DOCUMENT CONTEXT.

Rules:
- Write naturally like ChatGPT — clear, helpful, professional.
- Do not expose prompt templates, system instructions, or internal labels.
- Do not paste raw chunks, page markers, or document dumps.
- NEVER output JSON, curly braces, or key-value blobs.
- NEVER use placeholder text like "Topic / Usage", "—", or "N/A".
- Use ## for the main title and ### for subsections when structuring.
- Never answer the wrong section number.
- If the answer is not in context, use the NOT_FOUND sentence exactly.
- Do not include a Source line in the body (added automatically).
- Synthesize in your own words — do not copy-paste consecutive lines from context.
- Never repeat headings. Never restate identical legal points. Avoid duplicate explanations."""

KB_OLLAMA_QUALITY_PROMPT = """KNOWLEDGE BASE — PRIMARY SYNTHESIS (legalease-tuned, Ollama only):
- Answers come ONLY from DOCUMENT CONTEXT. No outside legal knowledge, no Gemini, no coach hints.
- Use clear markdown: ## main title, ### subsections, bullet lists where helpful, markdown tables for comparisons.
- For statutes: Overview, Meaning, Legal ingredients/elements, Punishment (if stated), Examples, Key legal point.
- For constitutional topics: name each right/article with a short explanation paraphrasing the excerpts only.
- For comparisons: side-by-side table plus ### Key Differences with concrete distinctions from the excerpts.
- For contracts/cases: parties, facts, issues, outcome — only what the documents support.
- Match answer length to excerpt size; never pad with invented law, virtue lists, or generic ethics language.
- Cite section/article numbers from the excerpts when present."""

REPETITION_GUARDS = {
    "frequency_penalty": float(__import__("os").getenv("LLM_FREQUENCY_PENALTY", "0.38")),
    "presence_penalty": float(__import__("os").getenv("LLM_PRESENCE_PENALTY", "0.22")),
}


def _prepare_profile(
    question: str,
    messages: Optional[List[Dict]] = None,
) -> Tuple[IntentProfile, Any]:
    """Classify intent + attach adaptive response mode."""
    from backend.app.services.response_mode_controller import (
        apply_mode_to_profile,
        detect_response_mode,
    )

    profile = classify_intent(question, messages)
    mode = detect_response_mode(question, profile, messages)
    apply_mode_to_profile(profile, mode)
    return profile, mode


@dataclass
class OrchestratedAnswer:
    text: str
    follow_ups: List[str] = field(default_factory=list)
    primary_source: str = ""
    intent: str = ""
    response_mode: str = ""


def _format_context_block(chunks: List[Dict]) -> str:
    from kb_preprocess import clean_legal_text

    parts = []
    for chunk in chunks:
        meta = chunk.get("metadata", {}) or {}
        fname = meta.get("filename", "document")
        body = clean_legal_text((chunk.get("content", "") or "").strip())
        if len(body) < 20:
            continue
        try:
            from kb_content_cleaner import format_statute_section_fields

            sec_m = re.search(
                r"(?:IPC|BNS)\s+Section\s+(\d+[A-Za-z]?)",
                body[:400],
                re.I,
            )
            if sec_m and re.search(r"\bMeaning:\s*", body, re.I):
                law = "BNS" if re.search(r"\bbns\b", body[:200], re.I) else "IPC"
                formatted = format_statute_section_fields(
                    body, section=sec_m.group(1).lower(), law=law
                )
                if formatted and len(formatted) > 80:
                    body = formatted
        except ImportError:
            pass
        parts.append(f"[Excerpt from {fname}]\n{body[:2400]}")
    return "\n\n---\n\n".join(parts) if parts else "(no context)"


def _clean_model_output(text: str) -> str:
    if not text:
        return ""
    from response_cleaner import clean_kb_response

    t = _PAGE_DUMP_RE.sub("", text)
    t = _RAW_SOURCE_RE.sub("", t)
    t = clean_kb_response(t)
    return t.strip()


def _humanize_meaning(
    sentences: List[str],
    section: str,
    law: str,
    *,
    card_has_title: bool = True,
) -> str:
    """Turn chunk sentences into natural explanation — no repeated section headers."""
    from response_cleaner import clean_chunk_text, strip_section_leadin

    subtitle = SECTION_SUBTITLES.get(section.upper(), "")
    cleaned: List[str] = []
    seen = set()
    for s in sentences:
        cs = clean_chunk_text(s)
        if len(cs) < 20:
            continue
        cs = strip_section_leadin(cs, section, law=law, subtitle=subtitle)
        if len(cs) < 20:
            continue
        key = cs.lower()[:90]
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(cs)
    if not cleaned:
        return ""
    text = " ".join(cleaned[:2])[:650]
    text = strip_section_leadin(text, section, law=law, subtitle=subtitle)
    if card_has_title:
        return text.strip()
    sub = subtitle
    if sub and not re.search(rf"\b{re.escape(sub)}\b", text, re.I):
        text = f"{law} Section {section.upper()} deals with **{sub.lower()}**. {text}"
    return text.strip()


def _extract_punishment_from_sentences(sentences: List[str]) -> str:
    from response_cleaner import clean_chunk_text

    for s in sentences:
        if re.search(
            r"\b(imprisonment|punish|fine|life|years|death|rigorous|liable)\b",
            s,
            re.I,
        ):
            return clean_chunk_text(s)[:400]
    return ""


def format_criminal_offences_summary(
    question: str,
    entities: List[Dict[str, str]],
    chunks: List[Dict],
    profile: IntentProfile,
) -> str:
    """Document-wide summary of criminal offences (IPC + IT Act)."""
    if not entities:
        return ""

    lines = ["# Criminal Offences Discussed", ""]
    for i, ent in enumerate(entities, start=1):
        label = ent.get("label") or f"{ent.get('law', 'IPC')} {ent.get('section', '').upper()}"
        title = ent.get("title") or ""
        sec = str(ent.get("section", ""))
        blurb = _offence_blurb_from_chunks(chunks, sec, ent.get("law", "IPC"))
        lines.append(f"{i}. **{label}**")
        if blurb:
            lines.append(f"   {blurb}")
        elif title:
            lines.append(f"   {title}.")
        lines.append("")

    lines.append(
        "_Based only on your uploaded document. Offences not mentioned in the file are omitted._"
    )
    body = "\n".join(lines)
    return polish_kb_response(body, chunks, section_hint="")


def _offence_blurb_from_chunks(chunks: List[Dict], section: str, law: str) -> str:
    from kb_retrieval import section_in_chunk

    for ch in chunks[:12]:
        body = (ch.get("content") or "").strip()
        if law == "IT Act":
            if not re.search(rf"\b{re.escape(section)}\b", body, re.I):
                continue
        elif not section_in_chunk(body, section):
            continue
        sentences = re.split(r"(?<=[.!?])\s+", body)
        for s in sentences:
            if len(s) > 40 and (
                section.lower() in s.lower()
                or re.search(rf"\bsection\s*{re.escape(section)}\b", s, re.I)
            ):
                return re.sub(r"\s+", " ", s).strip()[:200]
    return ""


def format_ipc_sections_list(
    question: str,
    entities: List[Dict[str, str]],
    chunks: List[Dict],
    profile: IntentProfile,
) -> str:
    """Structured list of IPC/BNS sections found across the full document."""
    if not entities:
        return ""

    lines = ["# IPC Sections Mentioned in Your Document", ""]
    for i, ent in enumerate(entities, start=1):
        label = ent.get("label") or f"{ent.get('law', 'IPC')} {ent.get('section', '').upper()}"
        title = ent.get("title") or ""
        if title and title not in label:
            lines.append(f"{i}. **{label}** — {title}")
        else:
            lines.append(f"{i}. **{label}**")

    lines.append("")
    lines.append(
        "This list is extracted only from your uploaded document. "
        "Sections not present in the file are not included."
    )
    body = "\n".join(lines)
    return polish_kb_response(body, chunks, section_hint="")


def format_case_topic_answer(question: str, chunks: List[Dict]) -> str:
    """Document-agnostic case answer — one narrative block, no FAQ / cross-case bleed."""
    try:
        from backend.app.core.kb_landmark_case import (
            build_landmark_case_answer,
            is_landmark_case_query,
        )

        if is_landmark_case_query(question):
            landmark = build_landmark_case_answer(question, chunks)
            if landmark:
                return landmark
            return ""
    except ImportError:
        pass

    from backend.app.core.case_narrative_engine import build_case_answer_from_chunks

    body = build_case_answer_from_chunks(question, chunks)
    if not body:
        return ""
    try:
        from backend.app.core.kb_landmark_case import strip_kb_document_boilerplate

        body = strip_kb_document_boilerplate(body)
    except ImportError:
        pass
    if not body or len(body.strip()) < 30:
        return ""
    return polish_kb_response(body, chunks)


def _rank_constitutional_chunks(chunks: List[Dict]) -> List[Dict]:
    """Prefer constitution/statute chunks over case narratives that mention Article N once."""
    scored: List[tuple] = []
    for ch in chunks or []:
        body = ch.get("content") or ""
        bl = body.lower()
        score = float(ch.get("final_score") or ch.get("hybrid_score") or 0)
        if re.search(r"five constitutional rights|fundamental\s+rights|constitutional\s+rights", bl):
            score += 12.0
        score += 2.0 * len(re.findall(r"Right\s+to\s+", body, re.I))
        if re.search(r"\b(?:bns|ipc)\s+section\s+\d", bl):
            score -= 10.0
        if re.search(r"suggested\s+kb\s+testing|compare\s+ipc|\(cid:\d+\)", bl):
            score -= 8.0
        if re.search(r"\bcase\s+\d+\s*:", bl) and ("fir no" in bl or "hearing" in bl):
            score -= 12.0
        fn = str((ch.get("metadata") or {}).get("filename") or "").lower()
        if re.search(r"constitution|fundamental", fn):
            score += 6.0
        if re.search(r"cases?_vol|case_kb|realistic.*case", fn):
            score -= 4.0
        scored.append((score, ch))
    scored.sort(key=lambda x: -x[0])
    good = [c for s, c in scored if s > -2.0]
    return good if good else list(chunks or [])


def format_constitutional_rights_answer(question: str, chunks: List[Dict]) -> str:
    """List constitutional rights enumerated in the uploaded document."""
    chunks = _rank_constitutional_chunks(chunks)
    try:
        from backend.app.core.kb_explanation_mode import (
            build_explanation_from_chunks,
            explanation_mode_active,
        )

        if explanation_mode_active(question):
            expl = build_explanation_from_chunks(question, chunks, strict=True)
            if expl and len(expl.strip()) > 120:
                return polish_kb_response(expl, chunks)
    except ImportError:
        pass
    combined = "\n".join((c.get("content") or "") for c in chunks)
    try:
        from backend.app.core.constitutional_concept_map import extract_constitutional_rights_block

        combined = extract_constitutional_rights_block(combined)
    except ImportError:
        combined = re.sub(r"\(cid:\d+\)\s*", "", combined)
    items: List[str] = []
    seen: set[str] = set()

    _REJECT_ITEM_RE = re.compile(
        r"\b(?:IPC\s+Section|BNS\s+Section|Explain\s+the|Compare\s+IPC|Difference\s+between|"
        r"Who\s+are|What\s+(?:is|happens)|Name\s+five|Nirbhaya|Kesavananda|NDA|"
        r"Punishment\s+for|warehouse|CCTV|charged\s+under)\b",
        re.I,
    )

    def _add(item: str) -> None:
        item = re.sub(r"\(cid:\d+\)\s*", "", item or "")
        item = re.sub(r"\s+", " ", item.strip()).rstrip(".,;")
        if len(item) < 12:
            return
        if _REJECT_ITEM_RE.search(item):
            return
        if not re.search(r"\bRight\s+(?:to|against)\b", item, re.I):
            return
        if not re.search(r"\bArticle\s+\d{1,3}\b", item, re.I):
            return
        if re.match(r"^Article\s+\d+\s*[—–-]\s*Right\s*$", item, re.I):
            return
        key = item.lower()[:80]
        if key and key not in seen:
            seen.add(key)
            items.append(item)

    for m in re.finditer(
        r"(Right\s+(?:to|against)\s+[^,()]+?\(\s*Article\s+\d{1,3}\s*\))",
        combined,
        re.I,
    ):
        _add(m.group(1))
    for m in re.finditer(
        r"\d+\.\s*(Right[^,(\n]+?\(\s*Article\s+\d{1,3}\s*\))",
        combined,
        re.I,
    ):
        _add(m.group(1))
    for line in combined.splitlines():
        line = line.strip()
        if re.match(r"^\d+\.\s*Right\b", line, re.I):
            _add(re.sub(r"^\d+\.\s*", "", line))

    want = 0
    m_five = re.search(r"\b(?:five|5)\b", (question or "").lower())
    if m_five and "right" in (question or "").lower():
        want = 5

    if len(items) < 2:
        return ""

    title = "Five Constitutional Rights" if want == 5 else "Constitutional Rights"
    lines = [f"## {title} (from your uploaded document)", ""]
    limit = want if want else min(8, len(items))
    for i, item in enumerate(items[:limit], start=1):
        if re.match(r"^Article\s+\d", item, re.I):
            lines.append(f"{i}. **{item}**")
        else:
            lines.append(f"{i}. **{item}**")
    if want and len(items) < want:
        lines.append("")
        lines.append(
            f"_Your document lists {len(items)} enumerated right(s); "
            f"the query asked for {want}._"
        )
  # region agent log
    try:
        from backend.app.core.debug_kb_session import dbg_kb

        dbg_kb(
            "H4",
            "answer_orchestrator.py:format_constitutional_rights_answer",
            "constitutional_list_built",
            {
                "query": (question or "")[:80],
                "item_count": len(items),
                "chunk_count": len(chunks),
                "top_file": str((chunks[0].get("metadata") or {}).get("filename", ""))[:60]
                if chunks
                else "",
            },
            run_id="post-fix",
        )
    except Exception:
        pass
    # endregion
    return polish_kb_response("\n".join(lines), chunks)


def _trim_statute_block(text: str, *, max_chars: int = 1200) -> str:
    """Keep the requested section only — stop at the next topic block in mixed chunks."""
    if not text:
        return ""
    try:
        from kb_content_cleaner import (
            format_statute_section_fields,
            is_kb_test_boilerplate,
            strip_kb_test_boilerplate,
        )
    except ImportError:
        format_statute_section_fields = None  # type: ignore
        is_kb_test_boilerplate = lambda _t: False  # type: ignore
        strip_kb_test_boilerplate = lambda t: t  # type: ignore

    lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if lines:
                lines.append("")
            continue
        if is_kb_test_boilerplate(stripped):
            continue
        if re.match(
            r"^(?:\d+\.|Five Constitutional|Nirbhaya|Kesavananda|Sample Non|Parties involved|\[PAGE:)",
            stripped,
            re.I,
        ):
            break
        if re.match(r"^(?:IPC|BNS|Indian Penal Code)\s+Section\s+\d", stripped, re.I):
            if lines:
                break
        lines.append(stripped)
    block = "\n".join(lines).strip()
    block = strip_kb_test_boilerplate(block)
    if format_statute_section_fields:
        formatted = format_statute_section_fields(block)
        if formatted:
            return formatted[:max_chars]
    if len(block) > max_chars:
        block = block[:max_chars].rsplit(" ", 1)[0].strip()
    return block


def format_statute_section_answer(
    question: str,
    chunks: List[Dict],
    section: str,
    law: str = "",
) -> str:
    """Fast deterministic answer for IPC/BNS section explain — no LLM."""
    if not section or not chunks:
        return ""
    law_l = (law or "").strip().lower()
    if not law_l:
        ql = (question or "").lower()
        law_l = "bns" if re.search(r"\bbns\b", ql) else "ipc"
    law_u = "BNS" if law_l == "bns" else "IPC"
    sec = section.lower()
    try:
        from kb_preprocess import extract_section_content
    except ImportError:
        extract_section_content = None  # type: ignore

    def _chunk_has_section(body: str) -> bool:
        if law_l == "bns":
            return bool(re.search(rf"\bbns\s*(?:section\s*)?{re.escape(sec)}\b", body, re.I))
        if re.search(rf"\bbns\s*(?:section\s*)?{re.escape(sec)}\b", body, re.I):
            return False
        return bool(
            re.search(
                rf"\b(?:ipc|indian penal code)\s*(?:section\s*)?{re.escape(sec)}\b",
                body,
                re.I,
            )
            or re.search(rf"\bsection\s*{re.escape(sec)}\b", body, re.I)
        )

    for ch in chunks:
        body = ch.get("content") or ""
        if not _chunk_has_section(body):
            continue
        isolated = ""
        if extract_section_content:
            isolated = extract_section_content(body, sec) or ""
        if law_l == "bns" and isolated and not re.search(r"\bbns\b", isolated, re.I):
            isolated = ""
        if not isolated or len(isolated) < 40:
            law_pat = "BNS" if law_l == "bns" else r"(?:IPC|Indian Penal Code)"
            m = re.search(
                rf"({law_pat}\s*Section\s*{re.escape(sec)}[^\n]*"
                rf"(?:\n(?!\s*(?:{law_pat}|IPC|BNS)\s*Section\s+\d)[^\n]+)*)",
                body,
                re.I,
            )
            isolated = m.group(1).strip() if m else ""
        if isolated and len(isolated) > 15:
            raw = re.sub(r"\n{3,}", "\n\n", isolated.strip())
            try:
                from kb_content_cleaner import format_statute_section_fields

                body_text = format_statute_section_fields(
                    raw, section=sec, law=law_u
                )
            except ImportError:
                body_text = _trim_statute_block(raw)
            if not body_text:
                continue
            if not body_text.lstrip().startswith("##"):
                header = statute_section_heading(sec, law_u)
                first_line = raw.split("\n", 1)[0].strip()
                sub_m = re.search(
                    rf"(?:{law_u}|IPC|BNS)\s+Section\s+{re.escape(sec)}\s*[—–\-]\s*(.+)$",
                    first_line,
                    re.I,
                )
                if sub_m and sub_m.group(1).strip().lower() not in header.lower():
                    header = f"{header} — {sub_m.group(1).strip()}"
                body_text = f"{header}\n\n{body_text}"
            return polish_kb_response(body_text, [ch], law=law_u)
        if _chunk_has_section(body) and len(body.strip()) >= 50:
            excerpt = _trim_statute_block(body[:1400]) or body.strip()[:900]
            if excerpt:
                return polish_kb_response(
                    f"{statute_section_heading(sec, law_u)}\n\n{excerpt}",
                    [ch],
                    law=law_u,
                )
    return ""


def format_section_card(
    section: str,
    sentences: List[str],
    chunks: List[Dict],
    profile: IntentProfile,
) -> str:
    """Structured human response for section lookups — markdown sections, no chunk dump."""
    from response_cleaner import clean_chunk_text, finalize_display_answer

    sec_u = section.upper()
    law = str((profile.signals or {}).get("law") or "").upper() or "IPC"
    orig = str((profile.signals or {}).get("original_query") or "")
    if re.search(r"\bbns\b", orig, re.I):
        law = "BNS"
    elif re.search(r"\bbns\b", (profile.expanded_query or "") + " ".join(sentences), re.I):
        law = "BNS"
    subtitle = SECTION_SUBTITLES.get(sec_u) or SECTION_SUBTITLES.get(section.lower(), "")
    title = f"# {law} Section {sec_u}"
    if subtitle:
        title += f" — {subtitle}"

    cleaned_sents: List[str] = []
    seen = set()
    for s in sentences:
        cs = clean_chunk_text(s)
        if len(cs) < 20:
            continue
        key = cs.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        cleaned_sents.append(cs)
    if not cleaned_sents:
        return NOT_FOUND

    wants_detail = profile.complexity in ("medium", "deep") or bool(
        profile.signals.get("flags", {}).get("explain_depth")
    )
    punishment_q = bool(
        re.search(r"\bpunishment\b", profile.expanded_query or "", re.I)
        or re.search(r"\bpenalty\b", profile.expanded_query or "", re.I)
    )

    meaning = _humanize_meaning(cleaned_sents, section, law, card_has_title=True)
    if not meaning:
        from response_cleaner import strip_section_leadin

        meaning = strip_section_leadin(
            clean_chunk_text(cleaned_sents[0])[:480],
            section,
            law=law,
            subtitle=subtitle or "",
        )

    try:
        from backend.app.services.legal_query_parser import is_law_replacement_only_answer

        if is_law_replacement_only_answer(meaning):
            return NOT_FOUND
    except ImportError:
        pass

    example = ""
    for s in cleaned_sents[1:5]:
        if re.search(r"\b(if|when|example|intending|attacks|weapon)\b", s, re.I):
            example = clean_chunk_text(s)[:320]
            break

    key_point = ""
    if section == "300":
        key_point = "Murder requires culpable homicide with defined aggravating circumstances."
    elif section == "299":
        key_point = "Culpable homicide is the broader category; murder is a specific form."
    elif section == "302":
        key_point = "This section prescribes the punishment for the offence of murder."
    elif section == "307":
        key_point = "Intent and knowledge are the core elements."

    punishment = _extract_punishment_from_sentences(cleaned_sents)

    parts = [title, "", "## Meaning", "", meaning]
    if example and wants_detail:
        parts.extend(["", "## Example", "", example.strip()])
    if key_point:
        parts.extend(["", "## Key Legal Point", "", key_point])
    if punishment and (wants_detail or punishment_q):
        parts.extend(["", "## Punishment", "", punishment])

    body, _ = finalize_display_answer(
        "\n".join(parts),
        chunks,
        section_hint=f"Section {sec_u}",
        section=section,
        law=law,
    )
    from kb_response_state import enforce_single_state

    return enforce_single_state(body, found=True)


def _format_structured_factual(
    question: str,
    body: str,
    profile: IntentProfile,
    chunks: List[Dict],
) -> str:
    """ChatGPT-style section answer when synthesis is thin or messy."""
    sections = profile.signals.get("sections") or []
    sec_label = f"IPC Section {sections[0].upper()}" if sections else "Legal provision"
    title = sec_label
    if sections:
        sub = SECTION_SUBTITLES.get(sections[0].upper()) or SECTION_SUBTITLES.get(
            sections[0].lower(), ""
        )
        if sub:
            title += f" — {sub}"

    short = body[:280].strip()
    detail = body[280:900].strip() if len(body) > 280 else ""
    parts = [f"## {title}", "", short]
    if detail and profile.complexity != "short":
        parts.extend(["", "### Explanation", "", detail])
    if profile.complexity == "deep" and len(body) > 400:
        parts.extend(["", "### Key legal insight", "", body[400:700].strip()])
    return polish_kb_response("\n".join(parts), chunks, section_hint=sec_label)


def _primary_source_label(chunks: List[Dict]) -> str:
    if not chunks:
        return ""
    from citation_formatter import format_source_label

    return format_source_label(chunks[0].get("metadata", {}) or {})


def _length_instruction(profile: IntentProfile) -> str:
    mode_dict = profile.signals.get("response_mode") or {}
    if isinstance(mode_dict, dict) and mode_dict.get("target_words"):
        return f"LENGTH: {mode_dict['target_words']} words."
    c = profile.complexity
    if c == "short":
        return "LENGTH: Short answer — 50 to 120 words. No headings."
    if c == "deep":
        return "LENGTH: Detailed answer — 300 to 800 words, structured with examples."
    return "LENGTH: Medium answer — 150 to 350 words."


def _intent_instructions(profile: IntentProfile) -> str:
    from backend.app.services.response_mode_controller import (
        ResponseModeSpec,
        mode_instructions,
    )

    mode_dict = profile.signals.get("response_mode") or {}
    if isinstance(mode_dict, dict) and mode_dict.get("mode"):
        spec = ResponseModeSpec(
            mode=mode_dict.get("mode", "quick_answer"),
            complexity=mode_dict.get("complexity", profile.complexity),
            target_words=mode_dict.get("target_words", "50-120"),
            max_tokens=mode_dict.get("max_tokens", profile.max_answer_tokens),
            use_table=mode_dict.get("use_table", False),
            headings=mode_dict.get("headings") or [],
            structure_hint=mode_dict.get("structure_hint", ""),
        )
        return mode_instructions(spec)

    intent = profile.primary
    length = _length_instruction(profile)
    state = profile.conversation_state or {}
    topic = state.get("active_topic", "")

    if intent == QueryIntent.FACTUAL_LOOKUP:
        return (
            f"TASK: Direct factual lookup.\n{length}\n"
            "Open with what the section/provision is in plain language.\n"
            "One key takeaway sentence. Mention a related section only if it appears in context.\n"
            "No bullet lists unless the user asked for a list."
        )
    if intent == QueryIntent.SUMMARIZATION:
        return (
            f"TASK: Document summarization.\n{length}\n"
            "One short intro sentence, then smart bullets (max 8).\n"
            "Each bullet: topic + one-line meaning. No chunk dump."
        )
    if intent == QueryIntent.BEGINNER_EXPLANATION:
        return (
            f"TASK: Beginner-friendly explanation.\n{length}\n"
            "Plain English, analogies welcome, zero jargon where possible.\n"
            "Sound like a patient teacher — not a statute printout."
        )
    if intent == QueryIntent.COMPARISON:
        return (
            f"TASK: Legal comparison.\n{length}\n"
            "Use a Markdown table: | Aspect | First | Second | when comparing two provisions.\n"
            "Then state key difference and practical implication in prose.\n"
            "Only compare items supported by context."
        )
    if intent == QueryIntent.LIST_EXTRACTION:
        return (
            f"TASK: Extract and list from the document.\n{length}\n"
            "Clean bullets only — section number + short label per line."
        )
    if intent == QueryIntent.FOLLOW_UP_CONTEXT:
        hint = f" Active topic: {topic}." if topic else ""
        return (
            f"TASK: Follow-up in ongoing conversation.{hint}\n{length}\n"
            "Resolve pronouns (it/that/this) from conversation context.\n"
            "Answer only what was asked — punishment, simplification, example, etc."
        )
    if intent == QueryIntent.MULTI_INTENT:
        return (
            f"TASK: Multi-part question — answer EVERY part.\n{length}\n"
            "Use ## headings per part. Skip parts with no evidence."
        )
    if intent == QueryIntent.GENERAL_ANALYSIS:
        return (
            f"TASK: Legal analysis.\n{length}\n"
            "Structure: Issue → Reasoning → Interpretation → Conclusion (only if complex).\n"
            "Otherwise a clear flowing paragraph."
        )
    return f"Answer clearly from context only.\n{length}"


def _subtask_instruction(intent: QueryIntent) -> str:
    fake = IntentProfile(primary=intent, response_mode="minimal", complexity="medium")
    return _intent_instructions(fake)


def build_synthesis_prompt(
    question: str,
    chunks: List[Dict],
    profile: IntentProfile,
) -> Tuple[str, str]:
    try:
        from backend.app.core.prompt_budget import budget_rag_chunks

        chunks = budget_rag_chunks(chunks)
    except Exception:
        pass
    context_block = _format_context_block(chunks)
    q = profile.expanded_query or question

    sig = profile.signals or {}
    kb_grounded = bool(sig.get("kb_synthesis") or sig.get("kb_no_learning_inject"))
    persona = "" if kb_grounded else sig.get("persona_prompt", "")
    mem_block = "" if kb_grounded else sig.get("user_memory", "")
    session_ctx = "" if kb_grounded else sig.get("memory_context_block", "")
    pref_block = "" if kb_grounded else sig.get("preference_block", "")
    reward_block = "" if kb_grounded else sig.get("reward_block", "")
    coach_block = "" if kb_grounded else sig.get("runtime_coach_block", "")
    kb_class = sig.get("kb_classification", {})
    system = (
        f"{persona + chr(10) * 2 if persona else ''}"
        f"{LEGALEASE_SYSTEM_PROMPT}\n\n"
        f"NOT_FOUND (use exactly if context lacks the answer):\n{NOT_FOUND}\n\n"
        f"{_intent_instructions(profile)}\n"
    )
    if kb_class:
        try:
            from backend.app.core.kb_request_classifier import kb_depth_instructions

            system += f"\n{kb_depth_instructions(kb_class)}\n"
        except Exception:
            pass
    if pref_block:
        system += f"\n{pref_block}\n"
    if reward_block:
        system += f"\n{reward_block}\n"
    if coach_block:
        system += f"\nRUNTIME COACH GUIDANCE (style only):\n{coach_block}\n"
    if session_ctx:
        system += (
            "\nCONVERSATION MEMORY (follow-up context — still ground answers in documents):\n"
            f"{session_ctx}\n"
        )
    if mem_block:
        system += (
            "\nUSER MEMORY (continuity and preferences only — not a legal source):\n"
            f"{mem_block}\n"
        )
    mem_hint = "" if kb_grounded else sig.get("memory_hint", "")
    if mem_hint:
        system += (
            "\nPRIOR SUCCESSFUL ANSWER HINT (may help phrasing — still ground in documents):\n"
            f"{mem_hint[:500]}\n"
        )
    past_chat = "" if kb_grounded else sig.get("past_chat_block", "")
    if past_chat:
        try:
            from backend.app.core.prompt_budget import budget_past_chat

            past_chat = budget_past_chat(past_chat)
        except Exception:
            pass
        system += (
            "\nPRIOR SESSIONS (historical advice only — verify against documents):\n"
            f"{past_chat}\n"
        )

    scope = (profile.signals or {}).get("document_scope") or {}
    if scope.get("strict"):
        fn = scope.get("filename") or "active document"
        system += (
            f"\nACTIVE DOCUMENT SCOPE: Answer ONLY from `{fn}`. "
            "Do not use information from any other uploaded file. "
            "If the active document does not contain the answer, say exactly:\n"
            f"{NOT_FOUND}\n"
        )

    if profile.primary == QueryIntent.MULTI_INTENT and profile.subtasks:
        parts = ["Answer each part using the same DOCUMENT CONTEXT.\n"]
        for i, (sub_intent, sub_q) in enumerate(profile.subtasks, 1):
            parts.append(f"### Part {i}: {sub_q}\n{_subtask_instruction(sub_intent)}\n")
        user = (
            f"QUESTION:\n{q}\n\n"
            f"{' '.join(parts)}\n\n"
            f"DOCUMENT CONTEXT:\n{context_block}\n\n"
            "ANSWER:"
        )
    else:
        prefill = (sig.get("kb_extractive_prefill") or "").strip()
        prefill_block = ""
        if prefill:
            prefill_block = (
                f"EXTRACTIVE PREFILL (only source — do not add outside facts):\n{prefill}\n\n"
            )
        user = (
            f"QUESTION:\n{q}\n\n"
            f"{prefill_block}"
            f"DOCUMENT CONTEXT:\n{context_block}\n\n"
            "ANSWER:"
        )

    return system, user


def _strip_spam_sections(text: str, profile: IntentProfile) -> str:
    if not text:
        return text
    if profile.response_mode in {"structured", "multi_section"}:
        return text.strip()

    lines = text.split("\n")
    cleaned: List[str] = []
    skip_block = False
    for line in lines:
        if _SPAM_HEADINGS.match(line.strip()):
            skip_block = profile.is_simple
            if skip_block:
                continue
        if skip_block and line.strip().startswith("###"):
            skip_block = False
        if not skip_block:
            cleaned.append(line)

    result = "\n".join(cleaned).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def suggest_follow_ups(
    question: str,
    answer: str,
    profile: IntentProfile,
) -> List[str]:
    ql = question.lower()
    sections = profile.signals.get("sections") or []
    state = profile.conversation_state or {}
    if not sections:
        sections = state.get("active_sections") or []

    if profile.primary == QueryIntent.FACTUAL_LOOKUP and sections:
        sec = sections[0].upper()
        return [
            "Explain in simple language",
            f"What punishment does it carry?",
            "Compare related sections",
        ]

    al = (answer or "").lower()
    # Case/Document-specific suggestion improvements:
    # if the answer already contains FIR/Hearing markers, generate relevant follow-up topics.
    if re.search(r"\bhearing\s*1\b", al, re.I):
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "SUGG",
                "answer_orchestrator.py:suggest_follow_ups",
                "branch_hearing_1",
                {"question": question[:60], "answer_len": len(answer or "")},
            )
        except Exception:
            pass
        return [
            "What happened during Hearing 1?",
            "Summarize key facts",
            "Which sections/charges are implicated in this hearing?",
        ]
    if re.search(r"\bhearing\s*\d+\b", al, re.I):
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "SUGG",
                "answer_orchestrator.py:suggest_follow_ups",
                "branch_hearing_any",
                {"question": question[:60], "answer_len": len(answer or "")},
            )
        except Exception:
            pass
        return [
            "Summarize this hearing",
            "What did the prosecution argue?",
            "What did the defense argue?",
        ]
    if re.search(r"\bfir\b", al, re.I):
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "SUGG",
                "answer_orchestrator.py:suggest_follow_ups",
                "branch_fir",
                {"question": question[:60], "answer_len": len(answer or "")},
            )
        except Exception:
            pass
        return [
            "Who are the parties in the FIR?",
            "What are the key FIR allegations?",
            "Summarize the procedural steps mentioned.",
        ]
    if re.search(r"\bvs\.?\s+", question or "", re.I) or (
        "case 1:" in al and ("fir" in al or "prosecution" in al)
    ):
        return [
            "What happened during Hearing 1?",
            "Summarize key facts",
            "Which IPC sections apply?",
        ]

    if (
        "article" in al
        and ("right to" in al or "constitutional" in al or "fundamental" in al)
    ) or "constitutional rights" in al:
        return [
            "Explain Right to Freedom",
            "Explain Right against Exploitation",
            "What are constitutional rights?",
        ]

    if profile.primary == QueryIntent.SUMMARIZATION:
        return [
            "Explain the most serious offence simply",
            "Compare two key sections",
            "What should a layperson remember?",
        ]

    if profile.primary == QueryIntent.COMPARISON:
        return [
            "Which section has higher punishment?",
            "Explain in beginner-friendly language",
            "List all sections in the document",
        ]

    if profile.primary == QueryIntent.BEGINNER_EXPLANATION:
        return [
            "Summarize criminal offences in the document",
            "What are the punishments?",
            "Compare two important sections",
        ]

    if profile.primary == QueryIntent.LIST_EXTRACTION:
        return [
            "Explain the most important section simply",
            "Summarize the document",
            "Compare two listed sections",
        ]

    return [
        "Summarize key points",
        "Explain in simple language",
        "What should I do next?",
    ]


def _strip_json_and_placeholders(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    if t.startswith("{") or t.startswith("["):
        try:
            import json
            from backend.app.services.response_formatter import format_legal_response

            return format_legal_response(t, intent="general")
        except Exception:
            pass
    t = re.sub(r"Topic\s*/?\s*Usage", "", t, flags=re.I)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _kb_fast_mode() -> bool:
    import os

    return os.getenv("KB_FAST_MODE", "1").lower() in {"1", "true", "yes"}


def _kb_llm_timeout_sec() -> float:
    import os

    default = "60" if _kb_fast_mode() else "180"
    return float(os.getenv("KB_LLM_TIMEOUT_SEC", default))


def _kb_ollama_max_tokens() -> int:
    import os

    default = "1024" if _kb_fast_mode() else "2048"
    return int(os.getenv("KB_OLLAMA_MAX_TOKENS", default))


def _kb_inference_rerank_enabled() -> bool:
    import os

    default = "0" if _kb_fast_mode() else "1"
    return os.getenv("KB_INFERENCE_RERANK", default).lower() in {"1", "true", "yes"}


def _llm_generate_with_timeout(
    generator: Any,
    user: str,
    *,
    system_prompt: str = "",
    temperature: float = 0.15,
    max_tokens: int = 1200,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    timeout_sec: Optional[float] = None,
) -> str:
    """Single Ollama call with hard timeout — prevents KB UI freeze."""
    limit = timeout_sec if timeout_sec is not None else _kb_llm_timeout_sec()

    def _call() -> str:
        return (
            generator.generate(
                user,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
            )
            or ""
        ).strip()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_call).result(timeout=limit)
    except FuturesTimeout:
        try:
            from backend.app.core.kb_pipeline_log import kb_log

            kb_log("LLM_TIMEOUT", seconds=limit)
        except Exception:
            pass
        return ""
    except Exception:
        return ""


def synthesize_from_chunks(
    question: str,
    chunks: List[Dict],
    profile: IntentProfile,
    *,
    user_id: str = "",
    temperature: float = 0.15,
    max_tokens: int = 1200,
    mode_spec: Any = None,
) -> str:
    if not chunks:
        return NOT_FOUND

    mode_dict = profile.signals.get("response_mode") or {}
    max_tokens = min(max_tokens, profile.max_answer_tokens or max_tokens)
    freq_pen = float(mode_dict.get("frequency_penalty", REPETITION_GUARDS["frequency_penalty"]))
    pres_pen = float(mode_dict.get("presence_penalty", REPETITION_GUARDS["presence_penalty"]))
    temp = float(mode_dict.get("temperature", temperature))

    kb_synthesis = bool((profile.signals or {}).get("kb_synthesis"))
    single_shot = bool((profile.signals or {}).get("kb_explanation_single_shot"))

    if profile.complexity == "short" and not kb_synthesis:
        temp = min(temp, 0.10)
        max_tokens = min(max_tokens, 320)
    elif profile.complexity == "deep" or kb_synthesis:
        cap = _kb_ollama_max_tokens()
        if single_shot:
            cap = min(cap, 1536)
        max_tokens = min(max(max_tokens, 1024 if single_shot else 1200), cap)
        profile.max_answer_tokens = max(int(profile.max_answer_tokens or 0), cap)
        if kb_synthesis:
            try:
                from backend.app.core.kb_strict_policy import kb_llm_temperature

                temp = kb_llm_temperature()
            except ImportError:
                temp = 0.0

    try:
        from backend.app.core.llm_orchestrator import get_generator_for_task
        from backend.app.core.llm_task_router import TaskType, router_enabled
        from llms import OLLAMA_MODEL, get_generator, is_ollama_error_response

        # KB answers: Ollama legalease-tuned only (never alternate chat models).
        if kb_synthesis or os.getenv("OLLAMA_KB_LOCK_MODEL", "1").lower() in {"1", "true", "yes"}:
            generator = get_generator(user_id=str(user_id or ""))
            if (getattr(generator, "model", "") or "").lower() != OLLAMA_MODEL.lower():
                generator = get_generator(model=OLLAMA_MODEL, user_id=str(user_id or ""))
        elif router_enabled():
            generator = get_generator_for_task(
                TaskType.LEGAL_REASONING, user_id=str(user_id or ""), allow_fallback=False
            )
        else:
            generator = get_generator(user_id=str(user_id or ""))
    except Exception:
        from llms import get_generator

        generator = get_generator(user_id=str(user_id or ""))
    # region agent log
    try:
        from backend.app.core.kb_runtime_debug import kb_runtime_log

        kb_runtime_log(
            "D",
            "answer_orchestrator.py:synthesize_from_chunks",
            "llm_generator_selected",
            {
                "generator_class": type(generator).__name__,
                "model": str(getattr(generator, "model", "")),
                "backend": str(getattr(generator, "raw_base_url", "") or "")[:80],
                "use_router": bool(router_enabled()),
            },
        )
    except Exception:
        pass
    # endregion
    system, user = build_synthesis_prompt(question, chunks, profile)
    if kb_synthesis:
        system = f"{system}\n\n{KB_OLLAMA_QUALITY_PROMPT}\n"
        try:
            from backend.app.core.kb_strict_policy import STRICT_KB_GROUNDING_PROMPT

            system = f"{system}\n{STRICT_KB_GROUNDING_PROMPT}\n"
        except ImportError:
            pass
        if (profile.signals or {}).get("kb_explanation_mode"):
            try:
                from backend.app.core.kb_explanation_mode import KB_EXPLANATION_MODE_PROMPT

                system = f"{system}\n{KB_EXPLANATION_MODE_PROMPT}\n"
                max_tokens = min(max(max_tokens, 768), 1024)
                temp = min(temp, 0.08)
            except ImportError:
                pass
        extra = (profile.signals or {}).get("kb_ollama_instruction", "")
        if extra:
            system = f"{system}\n{extra}\n"

    try:
        from backend.app.core.kb_pipeline_log import kb_log

        kb_log("FINAL_PROMPT", system=system[:800], user_msg=user[:1200])
    except Exception:
        pass

    try:
        from backend.app.core.reward_inference import (
            RERANK_CANDIDATES,
            select_best_candidate,
            should_rerank_candidates,
        )

        if (
            not single_shot
            and user_id
            and should_rerank_candidates(str(user_id))
            and (kb_synthesis or _kb_inference_rerank_enabled())
        ):
            temps = [temp, min(temp + 0.15, 0.45), min(temp + 0.28, 0.55)][:RERANK_CANDIDATES]
            candidates: List[str] = []
            for t in temps:
                cand = _llm_generate_with_timeout(
                    generator,
                    user,
                    system_prompt=system,
                    temperature=t,
                    max_tokens=max_tokens,
                    frequency_penalty=freq_pen,
                    presence_penalty=pres_pen,
                )
                if cand and not _is_low_information(cand.strip()):
                    candidates.append(cand.strip())
            if len(candidates) >= 2:
                best, rerank_meta = select_best_candidate(str(user_id), question, candidates)
                profile.signals = dict(profile.signals or {})
                profile.signals["inference_rerank"] = rerank_meta
                if best:
                    raw = best
                    cleaned = _strip_json_and_placeholders(raw)
                    from response_cleaner import deduplicate_response

                    return deduplicate_response(cleaned)
    except Exception:
        pass

    llm_timeout = min(_kb_llm_timeout_sec(), 45.0) if single_shot else _kb_llm_timeout_sec()
    answer = _llm_generate_with_timeout(
        generator,
        user,
        system_prompt=system,
        temperature=temp,
        max_tokens=max_tokens,
        frequency_penalty=freq_pen,
        presence_penalty=pres_pen,
        timeout_sec=llm_timeout,
    )
    raw = (answer or "").strip()
    try:
        from llms import is_ollama_error_response
    except ImportError:
        is_ollama_error_response = lambda t: False  # type: ignore
    if is_ollama_error_response(raw):
        try:
            from backend.app.core.kb_pipeline_log import kb_log

            kb_log("OLLAMA_ERROR", response=raw[:400])
        except Exception:
            pass
        raw = ""
    try:
        from backend.app.core.kb_pipeline_log import kb_log

        kb_log("LLM_RAW", response=raw[:800])
    except Exception:
        pass
    from kb_response_state import contains_not_found_phrase, enforce_single_state

    if (contains_not_found_phrase(raw) or _is_low_information(raw)) and not kb_synthesis:
        try:
            from backend.app.core.kb_force_answer import guarantee_kb_answer

            forced = guarantee_kb_answer(question, chunks)
            if forced:
                return enforce_single_state(forced, found=True)
        except Exception:
            pass

    if single_shot and kb_synthesis:
        try:
            from backend.app.core.kb_explanation_mode import (
                build_explanation_from_chunks,
                looks_like_chunk_dump,
            )

            if not raw or _is_low_information(raw) or looks_like_chunk_dump(raw):
                fb = build_explanation_from_chunks(question, chunks, strict=True)
                if fb:
                    from response_cleaner import deduplicate_response

                    return deduplicate_response(fb)
        except ImportError:
            pass

    if _is_low_information(raw) and not single_shot:
        retry_user = (
            f"{user}\n\n"
            "Write a complete, structured legal answer using ONLY the DOCUMENT CONTEXT above. "
            "Use ## and ### headings. Include section or article numbers when present. "
            "Do not refuse if context has relevant text. Be detailed and accurate."
        )
        raw = _llm_generate_with_timeout(
            generator,
            retry_user,
            system_prompt=system,
            temperature=min(temp, 0.08),
            max_tokens=max_tokens,
            frequency_penalty=freq_pen,
            presence_penalty=pres_pen,
            timeout_sec=_kb_llm_timeout_sec(),
        )
        try:
            from backend.app.core.kb_pipeline_log import kb_log

            kb_log("LLM_RETRY", response=raw[:800])
        except Exception:
            pass
    if _is_low_information(raw):
        fallback = intent_aware_fallback(question, chunks, profile)
        if fallback and fallback != NOT_FOUND:
            return fallback
        if kb_synthesis:
            try:
                from backend.app.core.kb_force_answer import guarantee_kb_answer

                forced = guarantee_kb_answer(question, chunks)
                if forced:
                    return enforce_single_state(forced, found=True)
            except Exception:
                pass
        return ""
    cleaned = _strip_json_and_placeholders(raw)
    if (profile.signals or {}).get("kb_explanation_mode"):
        try:
            from backend.app.core.kb_explanation_mode import sanitize_explanation_answer

            cleaned = sanitize_explanation_answer(cleaned, chunks) or cleaned
        except ImportError:
            pass
    from response_cleaner import deduplicate_response

    cleaned = deduplicate_response(cleaned)
    if kb_synthesis:
        try:
            from backend.app.core.kb_claim_audit import (
                answer_has_legal_definition_leak,
                audit_and_prune_answer,
                try_statute_safe_answer,
            )

            if answer_has_legal_definition_leak(cleaned, chunks):
                safe = try_statute_safe_answer(question, chunks)
                cleaned = safe or audit_and_prune_answer(cleaned, chunks) or ""
            else:
                cleaned = audit_and_prune_answer(cleaned, chunks)
        except ImportError:
            pass
        try:
            from backend.app.core.kb_strict_policy import finalize_kb_answer

            cleaned = finalize_kb_answer(cleaned, question, chunks)
        except ImportError:
            pass
    return cleaned


def intent_aware_fallback(
    question: str,
    chunks: List[Dict],
    profile: IntentProfile,
) -> str:
    if not chunks:
        return NOT_FOUND

    try:
        from backend.app.services.legal_query_parser import is_section_lookup_query
        from kb_legal_query_rewrite import extract_law_mapping_answer, is_law_replacement_query

        if not is_section_lookup_query(question) and is_law_replacement_query(question):
            mapped = extract_law_mapping_answer(question, chunks)
            if mapped:
                return polish_kb_response(mapped, chunks)
    except Exception:
        pass

    from kb_preprocess import clean_legal_text, chunk_matches_target

    orig_q = (profile.signals or {}).get("original_query") or question
    primary = str((profile.signals or {}).get("primary_section") or "")
    sections: List[str] = []
    if primary:
        sections = [primary]
    else:
        sections = list(profile.signals.get("sections") or [])
    try:
        from kb_query_types import primary_sections_from_query

        pg_secs = primary_sections_from_query(orig_q)
        if len(pg_secs) == 1:
            sections = pg_secs
    except Exception:
        pass

    content = clean_legal_text(" ".join((c.get("content", "") or "") for c in chunks[:6]))
    raw_sentences = [
        re.sub(r"\s+", " ", s.strip())
        for s in re.split(r"(?<=[.!?])\s+", content)
        if len(s.strip()) > 25
    ]
    if sections:
        sentences = [
            s
            for s in raw_sentences
            if chunk_matches_target(s, sections)
            or any(re.search(rf"\bsection\s*{re.escape(sec)}\b", s, re.I) for sec in sections)
        ]
        if not sentences:
            return NOT_FOUND
    else:
        sentences = raw_sentences
    if not sentences:
        return NOT_FOUND

    source = _primary_source_label(chunks)
    section_hint = f"Section {sections[0].upper()}" if sections else ""

    orig_q = (profile.signals or {}).get("original_query") or question
    from kb_retrieval import is_comparison_query

    if profile.primary == QueryIntent.COMPARISON or (
        is_comparison_query(orig_q) and len(sections) >= 2
    ):
        return format_comparison_answer(question, chunks, profile)

    if len(sections) == 1:
        sec = sections[0]
        ql = (orig_q or question or "").lower()
        law = "bns" if re.search(r"\bbns\b", ql) else "ipc"
        try:
            fast = format_statute_section_answer(question, chunks, sec, law)
            if fast:
                return fast
        except Exception:
            pass
        from kb_preprocess import extract_section_content
        from kb_retrieval import section_in_chunk

        scoped_parts: List[str] = []
        for ch in chunks[:4]:
            body = ch.get("content") or ""
            isolated = extract_section_content(body, sec)
            if isolated:
                scoped_parts.append(isolated)
            elif section_in_chunk(body, sec):
                scoped_parts.append(body)
        if scoped_parts:
            combined = clean_legal_text("\n\n".join(scoped_parts))
            raw_sentences = [
                re.sub(r"\s+", " ", s.strip())
                for s in re.split(r"(?<=[.!?])\s+", combined)
                if len(s.strip()) > 25
            ]
            sec_pat = rf"\b(?:section\s+{re.escape(sec)}|ipc\s+{re.escape(sec)}|bns\s+{re.escape(sec)})\b"
            best = [s for s in raw_sentences if re.search(sec_pat, s, re.I)]
            if not best:
                best = raw_sentences[:4]
            if best and not any(re.search(sec_pat, s, re.I) for s in best):
                return NOT_FOUND
            return format_section_card(sec, best[:4], chunks, profile)

        best: List[str] = []
        for s in sentences:
            if re.search(rf"\bsection\s*{re.escape(sec)}\b", s, re.I):
                best.append(s)
            elif re.search(rf"\b{re.escape(sec)}\b", s, re.I):
                best.append(s)
        if not best:
            best = sentences[:3]
        return format_section_card(sec, best[:3], chunks, profile)

    if profile.primary == QueryIntent.LIST_EXTRACTION:
        items = []
        for s in sentences[:12]:
            m = re.search(r"\b(?:IPC|BNS|Section)\s+\d+[A-Za-z]?", s, re.I)
            label = m.group(0) if m else s[:80]
            items.append(f"• {label}")
        body = "\n".join(items) if items else f"• {sentences[0][:200]}"
        return polish_kb_response(body, chunks, section_hint=section_hint)

    if profile.primary == QueryIntent.SUMMARIZATION:
        bullets = "\n".join(f"- {s[:160]}" for s in sentences[:6])
        body = f"## Summary\n\nHere's a concise read of your document:\n\n{bullets}"
        return polish_kb_response(body, chunks, section_hint=section_hint)

    if profile.complexity == "deep" or profile.signals.get("flags", {}).get(
        "explain_depth"
    ):
        return format_descriptive_answer(question, chunks, profile)

    if profile.primary == QueryIntent.BEGINNER_EXPLANATION:
        intro = (
            "In everyday terms, this part of your document sets out important legal rules. "
            "Here's the simplest reading:"
        )
        body = f"{intro}\n\n{sentences[0][:400]}"
        return polish_kb_response(body, chunks, section_hint=section_hint)

    body = " ".join(sentences[:4])[:900]
    if profile.primary == QueryIntent.FACTUAL_LOOKUP and sections:
        return _format_structured_factual(question, body, profile, chunks)
    if profile.complexity == "short":
        body = sentences[0][:320]
    else:
        body = " ".join(sentences[:3])[:700]
    return polish_kb_response(body, chunks, section_hint=section_hint)


def _snippet_for_section(chunks: List[Dict], section: str, max_len: int = 420) -> str:
    from kb_preprocess import clean_legal_text
    from kb_retrieval import section_in_chunk

    for ch in chunks:
        body = clean_legal_text((ch.get("content") or ""))
        if not section_in_chunk(body, section):
            continue
        lines = []
        for line in re.split(r"\n+", body):
            line = line.strip()
            if not line or len(line) < 12:
                continue
            if re.search(rf"\bsection\s*{re.escape(section)}\b", line, re.I) or (
                len(lines) == 0
            ):
                lines.append(line)
        text = " ".join(lines) if lines else body
        text = re.sub(r"\s*Page\s+\d+\s*[-–—]\s*", " ", text, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_len]
    return ""


def _table_cell(text: str, section: str = "", law: str = "IPC") -> str:
    """Sanitize text for a markdown table cell."""
    from response_cleaner import clean_chunk_text, strip_section_leadin

    subtitle = SECTION_SUBTITLES.get((section or "").upper(), "")
    t = clean_chunk_text(text or "")
    if section:
        t = strip_section_leadin(t, section, law=law, subtitle=subtitle)
    t = t.replace("|", "/").replace("\n", " ").strip()
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"^[.\s:—–\-]+", "", t).strip()
    if not t or t in ("—", "-", "Topic / Usage", "Topic/Usage"):
        return "The uploaded document does not provide this detail."
    return (t[:160] + "…") if len(t) > 160 else t


def format_comparison_answer(
    question: str,
    chunks: List[Dict],
    profile: IntentProfile,
) -> str:
    """Structured comparison — delegates to production compare engine."""
    from kb_compare_engine import extract_typed_entities, format_comparison_pro

    typed = (
        profile.signals.get("typed_entities")
        or extract_typed_entities(question)
    )
    if len(typed) >= 2:
        return format_comparison_pro(question, chunks, typed)

    from kb_retrieval import extract_comparison_sections

    secs = (
        profile.signals.get("entities")
        or profile.signals.get("sections")
        or extract_comparison_sections(question)
    )
    if len(secs) >= 2:
        law = "BNS" if re.search(r"\bbns\b", question or "", re.I) else "IPC"
        if re.search(r"\bipc\b", question or "", re.I) and not re.search(r"\bbns\b", question or "", re.I):
            law = "IPC"
        elif re.search(r"\bcrpc\b", question or "", re.I):
            law = "CrPC"
        fallback_typed = [
            {"type": law, "section": str(secs[0]).lower()},
            {"type": law, "section": str(secs[1]).lower()},
        ]
        try:
            from backend.app.services.legal_query_parser import is_mapping_comparison_intent

            if is_mapping_comparison_intent(question):
                from kb_legal_mapping import enrich_entities_with_mapping

                fallback_typed = enrich_entities_with_mapping(fallback_typed)
        except ImportError:
            pass

        return format_comparison_pro(question, chunks, fallback_typed)

    from kb_response_state import KB_NOT_FOUND_MESSAGE

    return KB_NOT_FOUND_MESSAGE


def _comparison_key_difference(sections: List[str], law: str) -> str:
    pairs = {
        ("299", "300"): (
            f"**{law} Section 299** covers *culpable homicide* — unlawful killing with the "
            "intention or knowledge described in your document.\n\n"
            f"**{law} Section 300** defines when that culpable homicide amounts to *murder* "
            "— with the aggravated circumstances set out in the source."
        ),
        ("300", "307"): (
            f"**{law} Section 300** deals with *murder* — the completed offence when "
            "culpable homicide meets the legal standard for murder.\n\n"
            f"**{law} Section 307** deals with *attempt to murder* — acts done with intent "
            "or knowledge that could cause death, even if the victim does not die."
        ),
    }
    if len(sections) >= 2:
        key = (sections[0], sections[1])
        rev = (sections[1], sections[0])
        if key in pairs:
            return pairs[key]
        if rev in pairs:
            return pairs[rev]
    return (
        f"**{law} Section {sections[0].upper()}** and "
        f"**{law} Section {sections[1].upper()}** address different offences and legal "
        "tests. See the table above for how each is described in your document."
    )


def _comparison_bullet_summary(
    sections: List[str], law: str, definitions: List[str]
) -> str:
    lines = []
    for i, sec in enumerate(sections):
        sub = SECTION_SUBTITLES.get(sec.upper(), "")
        label = f"{law} Section {sec.upper()}"
        if sub:
            label += f" ({sub})"
        snippet = definitions[i] if i < len(definitions) else "The uploaded document does not provide this detail."
        lines.append(f"- **{label}:** {snippet}")
    return "\n".join(lines)


def format_descriptive_answer(
    question: str,
    chunks: List[Dict],
    profile: IntentProfile,
) -> str:
    """Long-form answer with headings, paragraphs, and bullets."""
    from kb_preprocess import clean_legal_text
    from response_cleaner import finalize_display_answer, clean_chunk_text

    content = clean_legal_text(" ".join((c.get("content") or "") for c in chunks[:6]))
    sentences = [
        clean_chunk_text(s.strip())
        for s in re.split(r"(?<=[.!?])\s+", content)
        if len(s.strip()) > 30
    ]
    if not sentences:
        return NOT_FOUND

    title = "## Answer"
    if profile.signals.get("sections"):
        secs = profile.signals["sections"]
        title = f"# {question.strip()[:80]}" if len(question) < 80 else "## Legal Analysis"

    intro = sentences[0][:400]
    body_parts = [title, "", intro]

    if profile.complexity in ("medium", "deep") or profile.signals.get("flags", {}).get(
        "explain_depth"
    ):
        body_parts.extend(["", "### Explanation", ""])
        for s in sentences[1:4]:
            body_parts.append(s[:350])
            body_parts.append("")

    if profile.complexity == "deep" or len(sentences) > 4:
        body_parts.extend(["", "### Key Points", ""])
        for s in sentences[4:8]:
            body_parts.append(f"- {s[:200]}")

    if profile.signals.get("sections"):
        body_parts.extend(["", "### Sections Referenced", ""])
        for sec in profile.signals["sections"][:5]:
            sub = SECTION_SUBTITLES.get(sec.upper(), "")
            line = f"- **Section {sec.upper()}**"
            if sub:
                line += f" — {sub}"
            body_parts.append(line)

    body, _ = finalize_display_answer("\n".join(body_parts), chunks)
    from kb_response_state import enforce_single_state

    return enforce_single_state(body, found=True)


def _looks_like_chunk_dump(text: str) -> bool:
    if not text:
        return True
    if _PAGE_DUMP_RE.search(text):
        return True
    if text.lower().count("[page") >= 1:
        return True
    ipc_rows = len(re.findall(r"\bIPC\s+\d{1,4}\b", text, re.I))
    if _MAPPING_CHART_RE.search(text) and ipc_rows >= 3:
        return True
    if "topic / usage" in text.lower() and ipc_rows >= 2:
        return True
    section_mentions = len(re.findall(r"\bSection\s+\d{1,4}", text, re.I))
    if section_mentions >= 3 and len(text) > 600:
        return True
    if "primary criminal code" in text.lower() and section_mentions >= 1:
        return True
    return False


def synthesize_kb_answer_from_chunks(
    question: str,
    chunks: List[Dict],
    messages: Optional[List[Dict]] = None,
    *,
    temperature: float = 0.12,
    max_tokens: int = 2048,
    user_id: str = "",
) -> str:
    """Generate answer from chunks — never mixes NOT_FOUND with retrieved text."""
    if not chunks:
        return NOT_FOUND

    profile, mode = _prepare_profile(question, messages)
    try:
        from backend.app.core.kb_strict_policy import prepare_kb_synthesis_signals

        profile.signals = prepare_kb_synthesis_signals(profile.signals)
    except ImportError:
        profile.signals = dict(profile.signals or {})
        profile.signals["kb_synthesis"] = True
        profile.signals["kb_no_learning_inject"] = True
    if user_id:
        try:
            from backend.app.core.kb_strict_policy import kb_learning_inject_allowed

            if kb_learning_inject_allowed():
                _attach_learning_preferences(profile, question, user_id)
        except ImportError:
            pass

    try:
        from kb_compare_engine import (
            extract_all_comparison_entities,
            format_comparison_pro,
            is_compare_query,
        )

        if mode.mode == "comparison" or profile.primary == QueryIntent.COMPARISON or is_compare_query(question):
            typed = (
                profile.signals.get("typed_entities")
                or extract_all_comparison_entities(question)
            )
            orig_q = (profile.signals or {}).get("original_query") or question
            if len(typed) >= 2 and is_compare_query(orig_q):
                structured = format_comparison_pro(question, chunks, typed)
                if structured and "not found" not in structured.lower():
                    return _strip_json_and_placeholders(structured)
    except Exception:
        pass

    try:
        from backend.app.services.legal_query_parser import is_section_lookup_query
        from kb_legal_query_rewrite import extract_law_mapping_answer, is_law_replacement_query

        if not is_section_lookup_query(question) and is_law_replacement_query(question):
            mapped = extract_law_mapping_answer(question, chunks)
            if mapped:
                text = _strip_json_and_placeholders(mapped)
                if mode.mode == "quick_answer":
                    first = re.split(r"\n{2,}", text.strip())[0]
                    return first[:500].strip() or text
                return text
    except Exception:
        pass

    from kb_response_state import build_found_answer

    use_llm = True

    result = build_found_answer(
        question,
        chunks,
        profile,
        messages,
        use_llm=use_llm,
        temperature=mode.temperature,
        max_tokens=mode.max_tokens,
        user_id=user_id,
    ) or intent_aware_fallback(question, chunks, profile)
    from response_cleaner import deduplicate_response

    out = deduplicate_response(_strip_json_and_placeholders(result))
    try:
        from backend.app.core.kb_strict_policy import finalize_kb_answer

        out = finalize_kb_answer(out, question, chunks)
    except ImportError:
        pass
    return out


def _attach_learning_preferences(
    profile: Any,
    question: str,
    user_id: str,
    session_memory: Optional[Dict[str, Any]] = None,
) -> None:
    """Inject persistent preferences + KB depth classification into synthesis profile."""
    if not user_id:
        return
    try:
        from backend.app.core.kb_strict_policy import kb_learning_inject_allowed

        if not kb_learning_inject_allowed():
            return
    except ImportError:
        pass
    if (profile.signals or {}).get("kb_no_learning_inject"):
        return
    try:
        from backend.app.core.follow_up_intent import classify_follow_up_intent
        from backend.app.core.kb_request_classifier import classify_kb_request
        from backend.app.core.user_preferences import (
            build_preference_prompt_block,
            get_preference_profile,
            record_session_hint,
        )

        prefs = get_preference_profile(str(user_id))["profile"]
        intent_info = classify_follow_up_intent(question, session_memory or {})
        intent = intent_info.get("intent") or ""
        if intent_info.get("is_follow_up") and intent:
            record_session_hint(str(user_id), "last_follow_up_intent", intent)
        kb_class = classify_kb_request(question, user_prefs=prefs, follow_up_intent=intent)
        profile.signals = dict(profile.signals or {})
        profile.signals["preference_block"] = build_preference_prompt_block(
            str(user_id), kb_depth=kb_class.get("depth", "")
        )
        profile.signals["kb_classification"] = kb_class
        profile.signals["follow_up_intent"] = intent
        try:
            from backend.app.core.reward_inference import enrich_profile_rewards

            enrich_profile_rewards(profile, str(user_id), question)
        except Exception:
            pass
        try:
            from backend.app.core.chat_coach_runtime import get_runtime_coach_block

            coach_block = get_runtime_coach_block(str(user_id))
            if coach_block:
                profile.signals["runtime_coach_block"] = coach_block
        except Exception:
            pass
    except Exception:
        pass


def orchestrate_kb_answer(
    question: str,
    chunks: List[Dict],
    messages: Optional[List[Dict]] = None,
    *,
    temperature: float = 0.12,
    max_tokens: int = 2048,
    user_id: str = "",
) -> OrchestratedAnswer:
    profile, mode = _prepare_profile(question, messages)
    _attach_learning_preferences(profile, question, user_id)

    if not chunks:
        return OrchestratedAnswer(
            text=NOT_FOUND,
            follow_ups=["Upload a relevant PDF and re-index", "Try Open Law Intelligence"],
            intent=profile.primary.value,
            response_mode=profile.response_mode,
        )

    raw = synthesize_kb_answer_from_chunks(
        question,
        chunks,
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    cleaned = _clean_model_output(_strip_spam_sections(raw, profile))
    cleaned = strip_inline_citation_markers(cleaned)

    if _looks_like_chunk_dump(cleaned):
        orig_q = (profile.signals or {}).get("original_query") or question
        from kb_retrieval import is_comparison_query

        if (
            profile.primary == QueryIntent.COMPARISON
            and is_comparison_query(orig_q)
            and len(profile.signals.get("sections") or []) >= 2
        ):
            cleaned = format_comparison_answer(question, chunks, profile)
        else:
            fallback = intent_aware_fallback(question, chunks, profile)
            if fallback and "not found" not in fallback.lower():
                cleaned = fallback
            else:
                cleaned = _format_structured_factual(
                    question,
                    " ".join((c.get("content", "") or "")[:500] for c in chunks[:2]),
                    profile,
                    chunks,
                )

    sections = profile.signals.get("sections") or []
    section_hint = f"Section {sections[0].upper()}" if sections else ""
    if profile.primary == QueryIntent.FACTUAL_LOOKUP and sections and len(cleaned) < 120:
        cleaned = _format_structured_factual(question, cleaned, profile, chunks)

    final = polish_kb_response(cleaned, chunks, section_hint=section_hint)
    from kb_response_state import enforce_single_state

    final = enforce_single_state(final, found=True)
    if not final:
        final = enforce_single_state(
            intent_aware_fallback(question, chunks, profile), found=True
        )
    follow_ups = suggest_follow_ups(question, final, profile)

    return OrchestratedAnswer(
        text=final or NOT_FOUND,
        follow_ups=follow_ups,
        primary_source=_primary_source_label(chunks),
        intent=profile.primary.value,
        response_mode=mode.mode,
    )


def _is_low_information(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return True
    if normalized in {"{}", "{ }", "[]", "null", "none"}:
        return True
    if len(re.findall(r"[A-Za-z0-9]", normalized)) < 8:
        return True
    return False


def orchestrate_web_answer(
    question: str,
    snippets: List[Dict],
    messages: Optional[List[Dict]] = None,
    *,
    user_id: Optional[str] = None,
) -> OrchestratedAnswer:
    from legal_web_engine import (
        rank_legal_snippets,
        resolve_web_response_kind,
        synthesize_legal_web_answer,
    )
    from legal_web_query import is_self_contained_web_query

    hist = None if is_self_contained_web_query(question) else messages
    profile = classify_intent(question, hist)
    ranked = rank_legal_snippets(snippets or [], question)
    kind = resolve_web_response_kind(question, profile)
    text, follow_ups = synthesize_legal_web_answer(
        question, ranked, messages, user_id=user_id
    )
    cleaned = _strip_spam_sections(text, profile)
    if not follow_ups:
        follow_ups = suggest_follow_ups(question, cleaned, profile)
    return OrchestratedAnswer(
        text=cleaned,
        follow_ups=follow_ups,
        intent=profile.primary.value,
        response_mode=kind,
    )
