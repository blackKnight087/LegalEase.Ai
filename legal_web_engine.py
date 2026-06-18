"""
Professional legal web intelligence — source ranking, structured case briefs, no raw JSON.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from intent_engine import IntentProfile, QueryIntent, classify_intent

# Fast mode: REST-first search, structured snippet answers (LLM optional)
WEB_INTEL_FAST = os.getenv("WEB_INTEL_FAST", "1").lower() in ("1", "true", "yes")
WEB_INTEL_USE_LLM = os.getenv("WEB_INTEL_USE_LLM", "0").lower() in ("1", "true", "yes")
WEB_LLM_TIMEOUT_SEC = float(os.getenv("WEB_LLM_TIMEOUT_SEC", "45"))
WEB_MAX_SNIPPETS = int(os.getenv("WEB_MAX_SNIPPETS", "5"))
WEB_SNIPPET_CHARS = int(os.getenv("WEB_SNIPPET_CHARS", "320"))
WEB_LLM_MAX_TOKENS_FAST = int(os.getenv("WEB_LLM_MAX_TOKENS_FAST", "900"))
WEB_LLM_MAX_TOKENS_CASE = int(os.getenv("WEB_LLM_MAX_TOKENS_CASE", "1100"))

# Priority 1 — highest trust (official / primary legal)
PRIORITY_1_DOMAINS = (
    "sci.gov.in",
    "main.sci.gov.in",
    "indiankanoon.org",
    "legislative.gov.in",
    "lawcommissionofindia.nic.in",
    "egazette.nic.in",
    "indiacode.nic.in",
    "lddashboard.legislative.gov.in",
    "supremecourt.gov.in",
    "hcservices.ecourts.gov.in",
    "ecourts.gov.in",
)

# Priority 2 — reputable legal media / databases
PRIORITY_2_DOMAINS = (
    "scconline.com",
    "livelaw.in",
    "barandbench.com",
    "manupatra.com",
    "casemine.com",
    "bharatlaw",
    "lawctopus.com",
    "spicyip.com",
)

# Priority 3 — scholarship / PDF / journals
PRIORITY_3_DOMAINS = (
    ".edu",
    ".ac.in",
    "ssrn.com",
    "jstor.org",
    "researchgate.net",
    "ncbi.nlm.nih.gov",
)

# Priority 4 — general context only
PRIORITY_4_DOMAINS = ("wikipedia.org", "wikimedia.org")

CASE_QUERY_PATTERNS = (
    r"\bcase\b",
    r"\bjudgment\b",
    r"\bverdict\b",
    r"\bpetition\b",
    r"\bsuo\s+motu\b",
    r"rg\s*kar",
    r"nirbhaya",
    r"kesavananda",
    r"vishaka",
    r"navtej",
    r"shayara",
    r"maneka\s+gandhi",
    r"puttaswamy",
    r"indira\s+gandhi",
    r"basic\s+structure",
    r"landmark",
)

# Intent-driven Open Law response shapes (Markdown ## headers only)
_WEB_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "case_brief": {
        "title": "Legal Case Brief",
        "sections": [
            "Overview",
            "Facts",
            "Issues",
            "Judgement",
            "Significance",
            "Present Legal Position",
            "Citation Block",
            "Sources",
        ],
        "max_tokens": WEB_LLM_MAX_TOKENS_CASE,
    },
    "factual": {
        "title": "Legal Fact Sheet",
        "sections": [
            "Direct Answer",
            "Key Points",
            "Legal / Official Context",
            "Sources",
        ],
        "max_tokens": WEB_LLM_MAX_TOKENS_FAST,
    },
    "summary": {
        "title": "Legal Summary",
        "sections": [
            "Executive Summary",
            "Key Points",
            "Legal Significance",
            "Sources",
        ],
        "max_tokens": WEB_LLM_MAX_TOKENS_FAST,
    },
    "comparison": {
        "title": "Legal Comparison",
        "sections": [
            "Overview",
            "Side-by-Side Comparison",
            "Practical Difference",
            "Sources",
        ],
        "max_tokens": WEB_LLM_MAX_TOKENS_CASE,
    },
    "list": {
        "title": "Legal Reference List",
        "sections": [
            "Overview",
            "Items (use bullet lists)",
            "Notes",
            "Sources",
        ],
        "max_tokens": WEB_LLM_MAX_TOKENS_FAST,
    },
    "beginner": {
        "title": "Plain-Language Legal Guide",
        "sections": [
            "Simple Overview",
            "What This Means for You",
            "Example",
            "Sources",
        ],
        "max_tokens": WEB_LLM_MAX_TOKENS_FAST,
    },
    "statute": {
        "title": "Statute & Provision Analysis",
        "sections": [
            "Summary",
            "Relevant Provisions",
            "Punishment / Remedy",
            "Practical Notes",
            "Sources",
        ],
        "max_tokens": WEB_LLM_MAX_TOKENS_CASE,
    },
    "general": {
        "title": "Legal Research Brief",
        "sections": [
            "Summary",
            "Legal Analysis",
            "Practical Implications",
            "Sources",
        ],
        "max_tokens": WEB_LLM_MAX_TOKENS_FAST,
    },
}

DISCLAIMER = (
    "\n\n---\n*This is legal information for research and education, not legal advice. "
    "Consult a qualified advocate for case-specific strategy.*"
)

_JUNK_LINE_RES = (
    re.compile(r"our editors will review", re.I),
    re.compile(r"encyclopaedia britannica", re.I),
    re.compile(r"skip to (more|main|content|navigation)", re.I),
    re.compile(r"getty images", re.I),
    re.compile(r"^\s*#\s+\S", re.M),
    re.compile(r"^\s*\[\s*ref\s*\]", re.I),
    re.compile(r"cookie(s)? (policy|settings)", re.I),
    re.compile(r"subscribe (to|for)", re.I),
    re.compile(r"sign up (for|to)", re.I),
    re.compile(r"^\s*share (on|this)", re.I),
    re.compile(r"^\s*read more\s*$", re.I),
    re.compile(r"^\s*advertisement\s*$", re.I),
)


def clean_snippet_body(text: str) -> str:
    """Remove scraped navigation, image alt-text, and editor boilerplate."""
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    for p in _JUNK_LINE_RES:
        t = p.sub(" ", t)
    # Drop short junk fragments and image-caption sentences
    sentences = re.split(r"(?<=[.!?])\s+", t)
    kept: List[str] = []
    for sent in sentences:
        s = sent.strip()
        if len(s) < 25:
            continue
        sl = s.lower()
        if "getty images" in sl or "skip to" in sl:
            continue
        if "editors will review" in sl:
            continue
        kept.append(s)
    cleaned = " ".join(kept).strip()
    if not cleaned:
        cleaned = t
    return cleaned[:WEB_SNIPPET_CHARS]


def _clean_snippets(snippets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in snippets:
        row = dict(s)
        row["body"] = clean_snippet_body(str(row.get("body") or ""))
        out.append(row)
    return out


def _conversation_context_block(messages: Optional[List[Dict]], limit: int = 4) -> str:
    if not messages:
        return ""
    recent = messages[-limit:]
    parts: List[str] = []
    for msg in recent:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        label = "User" if role == "user" else "Assistant"
        parts.append(f"{label}: {content[:500]}")
    if not parts:
        return ""
    return "RECENT CONVERSATION (for continuity — answer the current question):\n" + "\n".join(parts)


def needs_llm_synthesis(
    question: str,
    messages: Optional[List[Dict]],
    kind: str,
    ranked: List[Dict[str, Any]],
) -> bool:
    """Use LLM synthesis for conversational/detail queries — not raw snippet paste."""
    if WEB_INTEL_USE_LLM:
        return True
    ql = (question or "").lower()
    try:
        from legal_web_query import is_detail_follow_up, is_vague_web_follow_up

        if is_detail_follow_up(question) or is_vague_web_follow_up(question):
            return True
    except ImportError:
        pass
    if re.search(
        r"\b(explain|detail|details|elaborate|comprehensive|analysis|overview|significance|tell me more)\b",
        ql,
    ):
        return True
    if kind in ("general", "case_brief", "beginner", "summary", "statute", "comparison"):
        return True
    if messages and len((question or "").split()) <= 12:
        return True
    if ranked:
        bodies = " ".join(clean_snippet_body(str(s.get("body") or "")) for s in ranked[:3])
        if len(bodies.strip()) < 120:
            return True
    profile = classify_intent(question, messages)
    if kind == "factual" and is_simple_factual_query(question, profile):
        return False
    return True


def _display_title(question: str) -> str:
    q = (question or "").strip()
    try:
        from legal_web_query import is_detail_follow_up, is_vague_web_follow_up

        if is_detail_follow_up(q) or is_vague_web_follow_up(q):
            m = re.search(r"about\s+(.+)$", q, re.I)
            if m:
                return m.group(1).strip()[:120]
            m = re.search(r"continuing discussion about:\s*(.+)$", q, re.I)
            if m:
                return m.group(1).strip()[:120]
    except ImportError:
        pass
    return q[:120]


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url or "").netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def source_trust_tier(href: str) -> int:
    """Lower number = higher trust (1 best, 5 worst)."""
    d = _domain_of(href)
    if not d:
        return 4
    for p in PRIORITY_1_DOMAINS:
        if p in d:
            return 1
    for p in PRIORITY_2_DOMAINS:
        if p in d:
            return 2
    for p in PRIORITY_3_DOMAINS:
        if p in d:
            return 3
    for p in PRIORITY_4_DOMAINS:
        if p in d:
            return 4
    if "gov.in" in d or ".gov" in d:
        return 1
    return 3


def rank_legal_snippets(
    snippets: List[Dict[str, Any]],
    query: str = "",
) -> List[Dict[str, Any]]:
    """Sort by trust tier and query relevance; deprioritize off-topic results."""
    if not snippets:
        return []

    snippets = _clean_snippets(snippets)

    ql = (query or "").lower()
    try:
        from legal_web_query import _KNOWN_CASE_RE
    except ImportError:
        _KNOWN_CASE_RE = re.compile(r"$^")
    query_terms = [
        t for t in re.findall(r"[a-z0-9]{3,}", ql)
        if t not in {"the", "and", "for", "with", "what", "how", "section", "india", "legal"}
    ]
    secs = re.findall(r"\b(\d{1,4}[a-z]?)\b", query or "")

    def score(row: Dict[str, Any]) -> Tuple[int, int, int]:
        tier = source_trust_tier(str(row.get("href", "")))
        body = str(row.get("body", "") or "")
        title = str(row.get("title", "") or "")
        blob = f"{title} {body}".lower()
        body_len = len(body)
        wiki_penalty = 1 if "wikipedia" in _domain_of(str(row.get("href", ""))) else 0
        term_hits = sum(1 for t in query_terms if t in blob)
        sec_hits = sum(1 for s in secs if re.search(rf"\b{s}\b", blob))
        off_topic = 0
        if _KNOWN_CASE_RE.search(query or "") and not re.search(r"rg\s*kar|kolkata|medical", blob):
            off_topic += 3
        if secs and len(secs) >= 2 and re.search(r"rg\s*kar|kolkata medical", blob):
            off_topic += 4
        return (tier + wiki_penalty * 2 + off_topic, -(term_hits * 3 + sec_hits * 5), -body_len)

    ranked = sorted(snippets, key=score)
    if query and query_terms:
        relevant = [
            r for r in ranked
            if any(t in f"{r.get('title', '')} {r.get('body', '')}".lower() for t in query_terms)
            or any(re.search(rf"\b{s}\b", f"{r.get('title', '')} {r.get('body', '')}", re.I) for s in secs)
        ]
        if len(relevant) >= 2:
            ranked = relevant + [r for r in ranked if r not in relevant]
    non_wiki = [r for r in ranked if source_trust_tier(str(r.get("href", ""))) < 4]
    return non_wiki[:8] if len(non_wiki) >= 2 else ranked[:8]


def is_case_law_query(question: str) -> bool:
    q = (question or "").lower().strip()
    if not q:
        return False
    if any(re.search(p, q) for p in CASE_QUERY_PATTERNS):
        return True
    if re.search(r"\bguidelines?\b", q) and re.search(
        r"\b(vishaka|sexual harassment|workplace|supreme court|landmark)\b", q
    ):
        return True
    if re.search(r"\bcase\b", q) or "judgment" in q or "judgement" in q or "verdict" in q:
        return len(q.split()) <= 12
    if re.search(r"\brg\s*karr?\b|\brg\s*kar\b", q):
        return True
    return False


def looks_like_json_response(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t.startswith("{") or t.startswith("["):
        try:
            json.loads(t)
            return True
        except json.JSONDecodeError:
            pass
    # Inline JSON object dominating the message
    if re.match(r"^\s*\{[\s\S]*\}\s*$", t) and '"' in t and ":" in t:
        return True
    return False


def json_response_to_markdown(text: str) -> str:
    """Convert accidental JSON LLM output into readable markdown."""
    t = (text or "").strip()
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return _strip_json_artifacts(t)

    lines: List[str] = []

    def walk(obj: Any, depth: int = 0) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).strip()
                if isinstance(v, (dict, list)):
                    lines.append(f"{'##' if depth == 0 else '###'} {key}")
                    walk(v, depth + 1)
                elif v not in (None, "", [], {}):
                    lines.append(f"**{key}:** {v}")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    walk(item, depth)
                else:
                    lines.append(f"- {item}")

    walk(data)
    out = "\n\n".join(lines).strip()
    return out if len(out) > 40 else _strip_json_artifacts(t)


def _strip_json_artifacts(text: str) -> str:
    t = re.sub(r"^\s*[\{\[]\s*", "", text)
    t = re.sub(r"\s*[\}\]]\s*$", "", t)
    t = re.sub(r'"\s*([^"]+?)\s*"\s*:', r"**\1:**", t)
    t = re.sub(r'"\s*,\s*"', "\n", t)
    return t.strip()


def sanitize_legal_display(text: str, fallback: str = "") -> str:
    normalized = (text or "").strip()
    if not normalized or normalized in ("{}", "[]", "null"):
        return fallback
    if looks_like_json_response(normalized):
        converted = json_response_to_markdown(normalized)
        if len(converted) > 60:
            return converted + DISCLAIMER
        return fallback or converted
    try:
        from backend.app.core.web_answer_cleaner import polish_research_answer

        normalized = polish_research_answer(normalized)
    except ImportError:
        pass
    return normalized


def _snippet_block(snippets: List[Dict[str, Any]], limit: Optional[int] = None) -> str:
    cap = limit or WEB_MAX_SNIPPETS
    parts = []
    for i, s in enumerate(snippets[:cap], 1):
        tier = source_trust_tier(str(s.get("href", "")))
        conf = "HIGH" if tier == 1 else "MEDIUM" if tier <= 2 else "LOW"
        parts.append(
            f"[{i}] [{conf}] {s.get('title', 'Source')}\n"
            f"URL: {s.get('href', '')}\n"
            f"{(s.get('body') or '')[:WEB_SNIPPET_CHARS]}"
        )
    return "\n\n".join(parts)


def _has_statute_signals(question: str, profile: IntentProfile) -> bool:
    q = (question or "").lower()
    sections = profile.signals.get("sections") or []
    return bool(sections) or bool(
        re.search(r"\b(section|ipc|bns|article|act|offence|offense|punishment|penalty)\b", q)
    )


def resolve_web_response_kind(question: str, profile: IntentProfile) -> str:
    """Pick structured template from question + intent."""
    q = (question or "").strip()
    ql = q.lower()
    if is_case_law_query(q):
        return "case_brief"
    if profile.primary == QueryIntent.COMPARISON or (
        re.search(r"\b(difference|compare|versus|vs\.?)\b", ql)
        and len(re.findall(r"\b\d{1,4}[a-z]?\b", q)) >= 2
    ):
        return "comparison"
    if profile.primary == QueryIntent.LIST_EXTRACTION:
        return "list"
    if profile.primary == QueryIntent.SUMMARIZATION:
        return "summary"
    if profile.primary in (QueryIntent.BEGINNER_EXPLANATION, QueryIntent.FOLLOW_UP_CONTEXT):
        if re.search(r"\b(simple|plain|beginner|explain)\b", q.lower()):
            return "beginner"
    ql = q.lower()
    factual_cues = (
        r"\b(who is|who's|who was|current|name of|when did|where is|what is the role)\b",
        r"\b(cji|chief justice|attorney general|law minister)\b",
        r"^(what is|what's|define)\b",
    )
    if profile.primary == QueryIntent.FACTUAL_LOOKUP or any(
        re.search(p, ql) for p in factual_cues
    ):
        return "factual"
    if _has_statute_signals(question, profile):
        return "statute"
    if profile.primary == QueryIntent.GENERAL_ANALYSIS:
        return "general"
    if re.search(r"\b(explain|describe|how does)\b", q.lower()):
        return "beginner" if re.search(r"\b(simple|plain)\b", q.lower()) else "general"
    return "general"


def is_simple_factual_query(question: str, profile: IntentProfile) -> bool:
    kind = resolve_web_response_kind(question, profile)
    if kind != "factual":
        return False
    q = (question or "").strip()
    return len(q.split()) <= 16


def _format_sources_block(snippets: List[Dict[str, Any]]) -> List[str]:
    lines = ["## Sources", ""]
    for i, s in enumerate(snippets[:WEB_MAX_SNIPPETS], 1):
        tier = source_trust_tier(str(s.get("href", "")))
        badge = "VERIFIED" if tier <= 2 else "REF"
        lines.append(
            f"- **[{i}] [{badge}]** [{s.get('title', 'Source')}]({s.get('href', '')})"
        )
    return lines


def intent_compose_from_snippets(
    question: str,
    snippets: List[Dict[str, Any]],
    kind: str,
) -> Tuple[str, List[str]]:
    """Structured digest without LLM — shaped by question type."""
    ranked = rank_legal_snippets(snippets, question)[:WEB_MAX_SNIPPETS]
    tpl = _WEB_TEMPLATES.get(kind, _WEB_TEMPLATES["general"])
    title = tpl.get("title", "Legal Research Brief")
    topic_label = _display_title(question)
    lines = [f"## {title}: {topic_label}", ""]

    if kind == "case_brief":
        top = ranked[0] if ranked else {}
        body = (top.get("body") or "").strip()
        title = top.get("title", "Source")
        lines.extend(["## Overview", "", body[:700] if body else "_See sources below._", ""])
        lines.extend([
            "## Citation Block",
            "",
            f"- **Source:** [{title}]({top.get('href', '')})",
            "- **Court:** (from sources)",
            "- **Bench:** (from sources)",
            "- **Year:** (from sources)",
            "- **Citation:** (from sources)",
            "- **Legal Principle:** (from sources)",
            "",
        ])
        if len(ranked) > 1:
            lines.extend(["## Facts", ""])
            for s in ranked[1:3]:
                b = (s.get("body") or "").strip()[:280]
                if b:
                    lines.append(f"- {b}")
            lines.append("")
    elif kind == "factual":
        top = ranked[0] if ranked else {}
        body = (top.get("body") or "").strip()
        lines.extend(["## Direct Answer", "", body[:650] if body else "_See sources._", ""])
        if len(ranked) > 1:
            lines.extend(["## Key Points", ""])
            for s in ranked[1:4]:
                b = (s.get("body") or "").strip()[:200]
                if b:
                    lines.append(f"- {b}")
            lines.append("")
    elif kind == "comparison":
        lines.extend([
            "## Overview",
            "",
            "Comparison based on retrieved web sources (verify against primary statutes).",
            "",
            "## Side-by-Side Comparison",
            "",
        ])
        for i, s in enumerate(ranked[:4], 1):
            lines.append(f"**Topic {i} — {s.get('title', 'Source')}**")
            lines.append((s.get("body") or "")[:300])
            lines.append("")
    elif kind == "list":
        lines.extend(["## Overview", "", "Key items from sources:", "", "## Items", ""])
        for s in ranked:
            b = (s.get("body") or "").strip()[:220]
            if b:
                lines.append(f"- {b}")
        lines.append("")
    else:
        top = ranked[0] if ranked else {}
        summary_parts: List[str] = []
        for s in ranked[:3]:
            b = clean_snippet_body(str(s.get("body") or ""))
            if b and b not in summary_parts:
                summary_parts.append(b)
        summary_text = " ".join(summary_parts)[:900] if summary_parts else "_See sources below._"
        lines.extend([
            "## Summary",
            "",
            summary_text,
            "",
        ])
        if len(ranked) > 1:
            lines.extend(["## Legal Analysis", ""])
            for s in ranked[1:4]:
                b = clean_snippet_body(str(s.get("body") or ""))
                if b and b not in summary_text:
                    lines.append(f"- {b[:320]}")
            lines.append("")

    lines.extend(_format_sources_block(ranked))
    lines.append(DISCLAIMER)
    return "\n".join(lines), _legal_follow_ups(question, kind)


def quick_compose_from_snippets(
    question: str, snippets: List[Dict[str, Any]], kind: str = "factual"
) -> Tuple[str, List[str]]:
    return intent_compose_from_snippets(question, snippets, kind)


def _web_system_prompt(kind: str, *, memory_block: str = "", persona: str = "") -> str:
    tpl = _WEB_TEMPLATES.get(kind, _WEB_TEMPLATES["general"])
    sections = "\n".join(f"- ## {s}" for s in tpl["sections"])
    base = (
        "You are LegalEase Open Law Intelligence — a conversational legal research assistant "
        "for advocates and students in India.\n"
        "STRICT RULES:\n"
        "- Output ONLY professional Markdown using ## headers (exactly as listed below).\n"
        "- NEVER output JSON, Python dicts, code fences, or raw key-value objects.\n"
        "- NEVER paste raw web snippets, navigation text, image captions, or editor boilerplate.\n"
        "- Synthesize sources into clear prose — like ChatGPT/Gemini, not a search dump.\n"
        "- Ground every claim in the numbered sources; cite inline as [1], [2].\n"
        "- For case briefs, include ## Citation Block with Source, Court, Bench, Year, Citation, Legal Principle.\n"
        "- Prefer official court/government and reputable legal media over Wikipedia alone.\n"
        "- If sources are thin or conflicting, say so clearly — do not invent facts.\n"
        "- Write for the user's question type; be direct, structured, and conversational.\n"
        f"\nREQUIRED SECTIONS (use these ## headers in order):\n{sections}\n"
    )
    if persona:
        base += f"\nUSER STYLE PREFERENCE:\n{persona[:600]}\n"
    if memory_block:
        base += f"\nUSER MEMORY (respect preferences, do not contradict):\n{memory_block[:800]}\n"
    return base


def _web_user_prompt(
    question: str,
    snippets: List[Dict[str, Any]],
    kind: str,
    *,
    compact: bool = False,
    messages: Optional[List[Dict]] = None,
) -> str:
    tpl = _WEB_TEMPLATES.get(kind, _WEB_TEMPLATES["general"])
    headers = " ".join(f"## {s}" for s in tpl["sections"])
    word_hint = "under 350 words" if compact else "under 800 words"
    convo = _conversation_context_block(messages)
    kind_hints = {
        "case_brief": "Focus on Indian case law: parties, court, bench, ratio, outcome, reform impact. "
        "Fill Citation Block from sources only.",
        "factual": "Lead with a clear direct answer in 2–4 sentences, then supporting points.",
        "summary": "Condense the topic; bullet key takeaways where helpful.",
        "comparison": "Use a clear comparison (table or bullets) — do not merge unrelated topics.",
        "list": "Extract enumerated items from sources; use bullet lists under ## Items.",
        "beginner": "Avoid jargon; explain terms in parentheses when needed.",
        "statute": "Name the Act/sections; state punishment/remedy if sources mention it.",
        "general": "Balanced legal analysis with practical implications. Synthesize — do not copy snippets.",
    }
    parts = []
    if convo:
        parts.append(convo)
    parts.append(f"USER QUESTION: {question}")
    parts.append(f"NUMBERED WEB SOURCES:\n{_snippet_block(snippets)}")
    parts.append(
        f"RESPONSE TYPE: {tpl.get('title', 'Legal brief')}\n"
        f"INSTRUCTION: {kind_hints.get(kind, kind_hints['general'])}\n"
        f"Write {word_hint}. Headers: {headers}\n"
        "Cite [1], [2]. No JSON. Synthesize in your own words."
    )
    return "\n\n".join(parts)


def synthesize_legal_web_answer(
    question: str,
    snippets: List[Dict[str, Any]],
    messages: Optional[List[Dict]] = None,
    *,
    user_id: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """
    Returns (markdown_answer, follow_ups) — structure depends on question intent.
    """
    from llms import get_generator

    ranked = rank_legal_snippets(snippets, question)
    mode = None
    memory_block = ""
    persona = ""
    if user_id:
        try:
            from backend.app.core.user_memory import build_memory_context

            mem = build_memory_context(user_id, question, history=messages)
            if mem.get("enabled"):
                memory_block = mem.get("memory_block", "")
                persona = mem.get("persona_prompt", "")
        except Exception:
            pass
    try:
        from backend.app.services.response_mode_controller import (
            apply_mode_to_profile,
            detect_response_mode,
        )
        from legal_web_query import is_self_contained_web_query

        hist = None if is_self_contained_web_query(question) else messages
        profile = classify_intent(question, hist)
        mode = detect_response_mode(question, profile, messages)
        apply_mode_to_profile(profile, mode)
    except Exception:
        profile = classify_intent(question, messages)
    kind = resolve_web_response_kind(question, profile)

    use_llm = needs_llm_synthesis(question, messages, kind, ranked)
    if WEB_INTEL_FAST and ranked and not use_llm:
        return intent_compose_from_snippets(question, ranked, kind)

    try:
        from backend.app.core.llm_orchestrator import get_generator_for_task
        from backend.app.core.llm_task_router import TaskType, router_enabled

        generator = (
            get_generator_for_task(TaskType.LEGAL_REASONING)
            if router_enabled()
            else get_generator()
        )
    except Exception:
        generator = get_generator()
    if not getattr(generator, "available", True):
        return intent_compose_from_snippets(question, ranked, kind)
    compact = WEB_INTEL_FAST and kind == "factual"
    tpl = _WEB_TEMPLATES.get(kind, _WEB_TEMPLATES["general"])
    max_tokens = int(tpl.get("max_tokens", WEB_LLM_MAX_TOKENS_FAST))
    if mode:
        max_tokens = mode.max_tokens
    if not compact and kind == "case_brief":
        max_tokens = max(max_tokens, 1600)
    try:
        from legal_web_query import is_detail_follow_up

        if is_detail_follow_up(question):
            max_tokens = max(max_tokens, 1200)
    except ImportError:
        pass

    freq_pen = mode.frequency_penalty if mode else 0.35
    pres_pen = mode.presence_penalty if mode else 0.22
    temp = mode.temperature if mode else (0.15 if compact else 0.25)

    system = _web_system_prompt(kind, memory_block=memory_block, persona=persona) + (
        "\nKeep concise — clarity over length." if compact else ""
    )
    if mode:
        try:
            from backend.app.services.response_mode_controller import mode_instructions

            system += "\n\n" + mode_instructions(mode)
        except Exception:
            pass
    user = _web_user_prompt(question, ranked, kind, compact=compact, messages=messages)

    def _run_llm() -> str:
        return (
            generator.generate(
                user,
                temperature=temp,
                max_tokens=max_tokens,
                system_prompt=system,
                frequency_penalty=freq_pen,
                presence_penalty=pres_pen,
            )
            or ""
        ).strip()

    raw = ""
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        with ThreadPoolExecutor(max_workers=1) as pool:
            raw = pool.submit(_run_llm).result(timeout=WEB_LLM_TIMEOUT_SEC)
    except FuturesTimeout:
        raw = ""
    except Exception:
        raw = ""

    cleaned = sanitize_legal_display(raw, fallback="")
    if not cleaned or len(cleaned) < 80 or not re.search(r"^##\s", cleaned, re.M):
        text, follow_ups = intent_compose_from_snippets(question, ranked, kind)
        return text, follow_ups

    if DISCLAIMER.strip() not in cleaned:
        cleaned += DISCLAIMER

    follow_ups = _legal_follow_ups(question, kind)
    return cleaned, follow_ups


def _fallback_markdown_from_snippets(
    question: str,
    snippets: List[Dict[str, Any]],
    kind: Optional[str] = None,
) -> str:
    """Structured digest when LLM returns garbage."""
    profile = classify_intent(question, None)
    k = kind or resolve_web_response_kind(question, profile)
    text, _ = intent_compose_from_snippets(question, snippets, k)
    return text.replace(DISCLAIMER, "").strip() + (
        "\n\n*Synthesized from web snippets; retry for a fuller LLM brief.*"
    )


def _legal_follow_ups(question: str, kind: str) -> List[str]:
    if kind == "case_brief":
        return [
            "Explain judgment in simple language",
            "Summarize the facts only",
            "What laws changed after this case?",
            "Show relevant IPC/BNS sections",
            "Related precedents",
        ]
    if kind == "factual":
        return [
            "Explain in simple language",
            "Latest official position",
            "Related legal provisions",
        ]
    if kind == "comparison":
        return [
            "Which applies in practice?",
            "Explain in simple language",
            "Show relevant sections",
        ]
    if kind == "statute":
        return [
            "Explain punishment in simple language",
            "Compare with related sections",
            "Recent court interpretation",
        ]
    return [
        "Explain in simple language",
        "Summarize key points",
        "Show relevant sections",
        "Official sources only",
    ]


def wants_detailed_explain(prompt: str) -> bool:
    p = (prompt or "").lower().strip()
    cues = (
        "explain in detail",
        "explain in details",
        "in detail",
        "in details",
        "more detail",
        "more details",
        "detailed explanation",
        "go deeper",
        "elaborate",
        "expand on",
        "break it down",
        "explain further",
    )
    if any(c in p for c in cues):
        return True
    if len(p.split()) <= 5 and re.search(r"\b(detail|details|elaborate|deeper)\b", p):
        return True
    return False


def wants_plain_language_explain(prompt: str) -> bool:
    p = (prompt or "").lower().strip()
    if wants_detailed_explain(p):
        return False
    cues = (
        "explain in simple",
        "simple language",
        "plain english",
        "like i'm not a lawyer",
        "eli5",
        "dumb it down",
        "explain judgment",
        "explain the judgment",
        "explain in simple language",
    )
    return any(c in p for c in cues) or p in ("explain", "explain.")


def expand_web_answer_detail(full_markdown: str, question: str = "") -> str:
    """Expand prior answer with deeper analysis — conversational follow-up."""
    from llms import get_generator

    system = (
        "You are a conversational legal research assistant. The user asked for MORE DETAIL "
        "on the previous answer.\n"
        "Expand with clear paragraphs, context, timeline, and legal significance.\n"
        "Use ## headers. NEVER paste raw web snippets or navigation text. NEVER output JSON.\n"
        "Keep source links if present. Write like ChatGPT — analyze and explain, don't dump text."
    )
    user = (
        f"USER REQUEST: {question}\n\n"
        f"PRIOR ANSWER:\n{full_markdown[:12000]}\n\n"
        "DETAILED EXPANDED VERSION:"
    )
    try:
        from backend.app.core.llm_orchestrator import get_generator_for_task
        from backend.app.core.llm_task_router import TaskType, router_enabled

        generator = (
            get_generator_for_task(TaskType.LEGAL_REASONING)
            if router_enabled()
            else get_generator()
        )
    except Exception:
        generator = get_generator()
    max_t = 1000 if WEB_INTEL_FAST else 1600
    raw = generator.generate(user, temperature=0.3, max_tokens=max_t, system_prompt=system) or ""
    out = sanitize_legal_display(raw, fallback=full_markdown)
    if DISCLAIMER.strip() not in out:
        out += DISCLAIMER
    return out


def plain_language_explain(full_markdown: str, question: str = "") -> str:
    """Rewrite legal answer for lay readers."""
    from llms import get_generator

    system = (
        "Rewrite the legal content in plain English for a non-lawyer Indian reader.\n"
        "Remove jargon or explain it in parentheses. Use short paragraphs and examples.\n"
        "Keep ## headers. NEVER output JSON. Keep source links if present."
    )
    user = f"ORIGINAL QUESTION: {question}\n\nLEGAL TEXT:\n{full_markdown[:12000]}\n\nPLAIN ENGLISH VERSION:"
    try:
        from backend.app.core.llm_orchestrator import get_generator_for_task
        from backend.app.core.llm_task_router import TaskType, router_enabled

        generator = (
            get_generator_for_task(TaskType.LEGAL_REASONING)
            if router_enabled()
            else get_generator()
        )
    except Exception:
        generator = get_generator()
    max_t = 700 if WEB_INTEL_FAST else 1200
    raw = generator.generate(user, temperature=0.25, max_tokens=max_t, system_prompt=system) or ""
    return sanitize_legal_display(raw, fallback=full_markdown)
