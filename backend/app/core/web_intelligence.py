"""
Native Google Gemini grounded search — Open Law web intelligence.

Replaces legacy Tavily / SerpAPI / DuckDuckGo scrapers with a single
google-genai client using Google Search Grounding (gemini-2.5-flash free tier).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_FREE_MODEL = os.getenv("GEMINI_FREE_MODEL", "gemini-2.5-flash").strip()
WEB_INTELLIGENCE_DEBUG = os.getenv("WEB_INTELLIGENCE_DEBUG", "0").lower() in (
    "1",
    "true",
    "yes",
)

DISCLAIMER = (
    "\n\n---\n*This is legal information for research and education, not legal advice. "
    "Consult a qualified advocate for case-specific strategy.*"
)

# Five legal research dimensions
DIMENSION_NEWS = "news_gazette"
DIMENSION_HEARINGS = "hearing_schedule"
DIMENSION_JUDGMENTS = "historical_judgments"
DIMENSION_SIMILAR = "similar_cases"
DIMENSION_STATUTORY = "statutory_lookup"
DIMENSION_GENERAL = "general_legal"
DIMENSION_JURISPRUDENCE = "jurisprudence"
DIMENSION_QUICK = "quick_fact"
DIMENSION_COMPARISON = "comparison"

DEPTH_QUICK = "quick"
DEPTH_STANDARD = "standard"
DEPTH_DETAILED = "detailed"
DEPTH_COMPARISON = "comparison"

_OPEN_LAW_WORD_LIMITS = {
    DIMENSION_QUICK: 120,
    DIMENSION_COMPARISON: 320,
    DIMENSION_HEARINGS: 280,
    DIMENSION_GENERAL: 260,
    DIMENSION_STATUTORY: 320,
    DIMENSION_JUDGMENTS: 380,
    DIMENSION_NEWS: 320,
    DIMENSION_SIMILAR: 450,
}

_DEPTH_WORD_LIMITS = {
    DEPTH_QUICK: 100,
    DEPTH_STANDARD: 260,
    DEPTH_DETAILED: 480,
    DEPTH_COMPARISON: 350,
}

_JURISPRUDENCE_SECTIONS = [
    "Executive Summary",
    "Document Intelligence (Knowledge Base)",
    "Real-Time Public Legal Intelligence",
    "Statutory & Regulatory Framework",
    "Case Law, Precedents & Cluster Analysis",
    "KB vs Public Source Reconciliation",
    "Strategic Recommendations & Next Steps",
    "Sources & Citations",
]

_DIMENSION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    DIMENSION_NEWS: {
        "title": "Legal News & Gazette Tracker",
        "sections": [
            "Executive Summary",
            "Amendments & Notifications",
            "Official Sources",
            "Practical Implications",
            "Sources",
        ],
        "focus": (
            "Track live legal news, gazette notifications, administrative orders, "
            "and statutory amendments across India. Cite official government portals."
        ),
    },
    DIMENSION_HEARINGS: {
        "title": "Live Case Hearing Schedule",
        "sections": [
            "Direct Answer",
            "Court & Bench",
            "Cause List Details",
            "Next Steps",
            "Sources",
        ],
        "focus": (
            "Find causelist entries, upcoming hearing dates, court room numbers, "
            "and listing status for Indian courts (Supreme Court, High Courts, tribunals)."
        ),
    },
    DIMENSION_JUDGMENTS: {
        "title": "Case Brief",
        "sections": [
            "Direct Answer",
            "Key Facts",
            "Legal Significance",
            "Sources",
        ],
        "focus": (
            "Brief case summary from Indian courts and legal news — facts, holding, and why it matters. "
            "Do not list IPC sections from any uploaded file."
        ),
    },
    DIMENSION_SIMILAR: {
        "title": "Similar Case Cluster Matrix",
        "sections": [
            "Overview",
            "Factual Pattern",
            "Related Precedents",
            "Comparison Matrix",
            "Predictive Notes",
            "Sources",
        ],
        "focus": (
            "Group related Indian case laws by factual patterns, compare outcomes, "
            "and note trends useful for argument strategy. Be cautious on predictions."
        ),
    },
    DIMENSION_STATUTORY: {
        "title": "Statutory Knowledge Lookup",
        "sections": [
            "Direct Answer",
            "Relevant Provisions",
            "Punishment / Remedy",
            "Cross-References (IPC/BNS/BNSS/BSA)",
            "Practical Notes",
            "Sources",
        ],
        "focus": (
            "Exhaustive Indian statutory lookup: BNS, BNSS, BSA, Constitution, IPC legacy, "
            "CrPC, Evidence Act mappings. Name sections precisely."
        ),
    },
    DIMENSION_GENERAL: {
        "title": "Legal Research Brief",
        "sections": [
            "Direct Answer",
            "Key Points",
            "Sources",
        ],
        "focus": (
            "Concise Indian legal answer from authoritative web sources. "
            "Be direct — like a quick legal search result, not a law review article."
        ),
    },
    DIMENSION_QUICK: {
        "title": "Quick Legal Fact",
        "sections": [
            "Direct Answer",
            "Sources",
        ],
        "focus": (
            "Answer the exact question in 2–4 sentences using current Google Search results. "
            "No preamble, no extra sections, no document references."
        ),
    },
    DIMENSION_COMPARISON: {
        "title": "Legal Comparison",
        "sections": [
            "Direct Answer",
            "Comparison Table",
            "Key Takeaways",
            "Sources",
        ],
        "focus": (
            "Compare ONLY what the user asked. Include a markdown table with clear column headers "
            "for each item being compared (e.g. Section | Definition | Punishment). "
            "Keep prose minimal — let the table carry the comparison."
        ),
    },
}


def gemini_configured() -> bool:
    return bool(GEMINI_API_KEY)


def web_intel_status() -> Dict[str, Any]:
    tavily_ok = False
    serp_ok = False
    try:
        from tavily_mcp import mcp_status

        tavily_ok = bool(mcp_status().get("api_key_configured"))
    except Exception:
        tavily_ok = bool(os.getenv("TAVILY_API_KEY", "").strip())
    try:
        from backend.app.core.serp_search import serp_configured

        serp_ok = serp_configured()
    except Exception:
        pass
    return {
        "provider": "gemini_grounded_search",
        "gemini_configured": gemini_configured(),
        "model": GEMINI_FREE_MODEL,
        "debug": WEB_INTELLIGENCE_DEBUG,
        "legacy_search_disabled": False,
        "tavily_configured": tavily_ok,
        "serp_configured": serp_ok,
        "fallback_providers": ["tavily", "serpapi", "duckduckgo"],
    }


def classify_open_law_request(query: str) -> Dict[str, Any]:
    """Pick topic dimension + response depth (quick / standard / detailed / comparison)."""
    q = (query or "").strip()
    ql = q.lower()
    words = len(q.split())

    if re.search(r"\b(compare|comparison|difference|differences|versus|vs\.?|between)\b", ql):
        depth = DEPTH_COMPARISON
        dimension = DIMENSION_COMPARISON
    elif re.search(
        r"\b(in detail|in details|detailed|explain fully|comprehensive|elaborate|deep dive|"
        r"thorough|full analysis|expand on)\b",
        ql,
    ):
        depth = DEPTH_DETAILED
        dimension = detect_research_dimension(q)
    elif (
        words <= 12
        and re.search(
            r"\b(\d+\s+\w+|list|name|enumerate|fundamental|constitutional)\b",
            ql,
        )
        and re.search(r"\b(rights?|articles?|sections?|freedoms?)\b", ql)
    ):
        depth = DEPTH_QUICK
        dimension = DIMENSION_STATUTORY if re.search(r"\b(constitution|constitutional|article|fundamental)\b", ql) else DIMENSION_GENERAL
    elif (
        words <= 10
        and re.search(
            r"\b(who is|who was|who are|what is|what are|when is|when was|where is|"
            r"which|how many|name of|current|present)\b",
            ql,
        )
    ) or re.search(r"\b(cji|chief justice|attorney general|law minister)\b", ql):
        depth = DEPTH_QUICK
        dimension = DIMENSION_QUICK
    else:
        depth = DEPTH_STANDARD
        dimension = detect_research_dimension(q)
        if dimension == DIMENSION_JUDGMENTS and words <= 8:
            dimension = DIMENSION_GENERAL

    word_cap = min(
        _DEPTH_WORD_LIMITS.get(depth, 260),
        _OPEN_LAW_WORD_LIMITS.get(dimension, 260),
    )
    return {
        "dimension": dimension,
        "depth": depth,
        "word_cap": word_cap,
    }


def detect_research_dimension(query: str) -> str:
    q = (query or "").lower()
    if re.search(
        r"\b(compare|comparison|difference|differences|versus|vs\.?|between)\b",
        q,
    ):
        return DIMENSION_COMPARISON
    if re.search(
        r"\b(causelist|cause list|hearing date|listed on|next date|court date|"
        r"item no|bench list|listing)\b",
        q,
    ):
        return DIMENSION_HEARINGS
    if re.search(
        r"\b(gazette|notification|amendment|notified|egazette|administrative order|"
        r"circular|ordinance)\b",
        q,
    ):
        return DIMENSION_NEWS
    if re.search(
        r"\b(similar cases|precedents like|cases like|cluster|compare cases|"
        r"factual pattern|verdict prediction|likely outcome)\b",
        q,
    ):
        return DIMENSION_SIMILAR
    if re.search(
        r"\b(who is|who's)\s+(?:the\s+)?(?:cji|chief justice|cj of india)\b",
        q,
    ) or re.search(r"\bchief justice of india\b", q):
        return DIMENSION_QUICK
    if re.search(
        r"\b(judgment|judgement|verdict|ruling|disposed|held that|ratio decidendi|"
        r"landmark case|case brief)\b",
        q,
    ):
        return DIMENSION_JUDGMENTS
    if re.search(r"\bcase\b", q) or re.search(
        r"\b(?:rg\s*karr?|rg\s*kar|nirbhaya|kesavananda|vishaka|navtej|"
        r"puttaswamy|shayara|maneka\s+gandhi)\b",
        q,
        re.I,
    ):
        return DIMENSION_JUDGMENTS
    if re.search(
        r"\b(bns|bnss|bsa|ipc|crpc|section\s*\d|article\s*\d|constitution|"
        r"statute|act|offence|offense|punishment)\b",
        q,
    ):
        return DIMENSION_STATUTORY
    return DIMENSION_GENERAL


def _filter_open_law_history(
    history: Optional[List[Dict[str, Any]]],
    *,
    limit: int = 4,
) -> List[Dict[str, Any]]:
    """Drop KB/hybrid turns and verbal feedback so Open Law stays web-only."""
    kb_markers = (
        "uploaded document",
        "knowledge base",
        "not found in document",
        "ipc sections mentioned in your document",
        "from your documents",
        "where your uploaded documents",
        "jurisprudence engine",
        "couldn't find a clear reference",
    )
    ack_markers = (
        "glad that helped",
        "you're welcome",
        "thanks for the honest feedback",
        "thanks for the feedback",
        "recorded as **negative feedback**",
    )
    try:
        from legal_web_query import is_conversational_feedback
    except ImportError:
        is_conversational_feedback = None  # type: ignore

    kept: List[Dict[str, Any]] = []
    for msg in history or []:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user" and is_conversational_feedback and is_conversational_feedback(
            content, history
        ):
            continue
        if role == "assistant":
            low = content.lower()
            if any(m in low for m in kb_markers):
                continue
            if any(m in low for m in ack_markers):
                continue
            if len(content) > 2500:
                content = content[:800] + "…"
                msg = {**msg, "content": content}
        kept.append(msg)
    return kept[-limit * 2 :]


def _conversation_block(history: Optional[List[Dict[str, Any]]], limit: int = 2) -> str:
    history = _filter_open_law_history(history, limit=limit)
    if not history:
        return ""
    lines: List[str] = []
    for msg in history[-limit:]:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            label = "User" if role == "user" else "Assistant"
            lines.append(f"{label}: {content[:600]}")
    if not lines:
        return ""
    return "RECENT CONVERSATION (for continuity):\n" + "\n".join(lines)


def _system_prompt(
    dimension: str,
    *,
    persona: str = "",
    memory_block: str = "",
    depth: str = DEPTH_STANDARD,
) -> str:
    tpl = _DIMENSION_TEMPLATES.get(dimension, _DIMENSION_TEMPLATES[DIMENSION_GENERAL])
    sections = "\n".join(f"- ## {s}" for s in tpl["sections"])
    depth_note = {
        DEPTH_QUICK: "RESPONSE LENGTH: Ultra-short — 2–4 sentences in Direct Answer only.",
        DEPTH_STANDARD: "RESPONSE LENGTH: Concise — bullet points OK, no essay.",
        DEPTH_DETAILED: "RESPONSE LENGTH: Structured detail with ## headers, stay focused.",
        DEPTH_COMPARISON: "RESPONSE LENGTH: Table-first — markdown comparison table is mandatory.",
    }.get(depth, "")
    base = (
        "You are LegalEase Open Law Intelligence — India's AI legal research assistant.\n"
        "You have Google Search grounding. Find current, authoritative Indian legal information.\n\n"
        "STRICT RULES:\n"
        "- Output ONLY professional Markdown with ## headers exactly as listed below.\n"
        "- NEVER output JSON, code fences, or raw search dumps.\n"
        "- Answer from live public web sources ONLY — never uploaded documents or knowledge base.\n"
        "- Answer ONLY what was asked — no unrelated IPC lists, no filler, no repetition.\n"
        "- ACCURACY: Use search results before stating facts. Do not invent case names, dates, "
        "sections, or holdings. If unverified, say: 'Could not verify from public sources.'\n"
        "- Prefer indiankanoon.org, sci.gov.in, legislative.gov.in, livelaw.in, barandbench.com.\n"
        "- India jurisdiction unless stated otherwise.\n"
        f"- {depth_note}\n\n"
        f"RESEARCH FOCUS: {tpl['focus']}\n\n"
        f"REQUIRED SECTIONS (in order):\n{sections}\n"
    )
    if persona:
        base += f"\nUSER STYLE: {persona[:500]}\n"
    if memory_block:
        base += f"\nUSER MEMORY:\n{memory_block[:700]}\n"
    return base


def _word_limit(dimension: str) -> int:
    return _OPEN_LAW_WORD_LIMITS.get(dimension, 400)


def _max_tokens(dimension: str, depth: str = DEPTH_STANDARD) -> int:
    if depth == DEPTH_QUICK:
        return 384
    if depth == DEPTH_COMPARISON:
        return 900
    if depth == DEPTH_DETAILED:
        return 1100
    if dimension == DIMENSION_QUICK:
        return 384
    return 700


def _user_prompt(
    query: str,
    dimension: str,
    history: Optional[List[Dict[str, Any]]],
    *,
    depth: str = DEPTH_STANDARD,
    word_cap: int = 260,
) -> str:
    tpl = _DIMENSION_TEMPLATES.get(dimension, _DIMENSION_TEMPLATES[DIMENSION_GENERAL])
    try:
        from legal_web_query import is_self_contained_web_query

        if is_self_contained_web_query(query):
            history = None
    except ImportError:
        pass
    convo = _conversation_block(history)
    parts = []
    if convo:
        parts.append(convo)
    try:
        from legal_web_query import build_web_search_query

        focused = build_web_search_query(query, history)
    except ImportError:
        focused = (query or "").strip()
    topic = (focused or query or "").strip()
    if topic.lower() != (query or "").strip().lower():
        parts.append(f"RESEARCH TOPIC (use Google Search for this):\n{topic}")
        parts.append(f"USER WORDING:\n{(query or '').strip()}")
    else:
        parts.append(f"USER QUESTION:\n{topic}")
    extra = ""
    if depth == DEPTH_COMPARISON:
        extra = " Include a markdown comparison table in ## Comparison Table. "
    elif depth == DEPTH_QUICK:
        extra = " Keep Direct Answer to 2–4 sentences maximum. "
    elif depth == DEPTH_DETAILED:
        extra = " Use bullet points under each ## header. "
    parts.append(
        f"RESPONSE TYPE: {tpl['title']}\n"
        f"Use Google Search grounding. Hard limit: {word_cap} words.{extra} "
        "Web sources only — never uploaded documents. "
        "Do not add a ## Sources section or paste raw URLs in the answer — citations are shown separately."
    )
    return "\n\n".join(parts)


def _get_client():
    from google import genai

    return genai.Client(api_key=GEMINI_API_KEY)


def _extract_sources(response: Any) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    seen: set[str] = set()
    try:
        candidates = getattr(response, "candidates", None) or []
        for cand in candidates:
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if not web:
                    continue
                uri = (getattr(web, "uri", None) or "").strip()
                title = (getattr(web, "title", None) or uri or "Web source").strip()
                if not uri or uri in seen:
                    continue
                seen.add(uri)
                sources.append(
                    {
                        "title": title[:200],
                        "href": uri,
                        "body": "",
                        "date": datetime.now(timezone.utc).date().isoformat(),
                        "provider": "Open Law Web Search",
                    }
                )
    except Exception as exc:
        if WEB_INTELLIGENCE_DEBUG:
            logger.warning("grounding source extract failed: %s", exc)
    return sources


def _extract_text(response: Any) -> str:
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return text
    try:
        candidates = getattr(response, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", None) or []:
                t = getattr(part, "text", None)
                if t:
                    return t.strip()
    except Exception:
        pass
    return ""


def _follow_ups(dimension: str) -> List[str]:
    mapping = {
        DIMENSION_HEARINGS: [
            "Show cause list details",
            "Related judgments on this matter",
            "Explain in simple language",
        ],
        DIMENSION_JUDGMENTS: [
            "Explain judgment in simple language",
            "Similar precedents",
            "Show relevant sections",
        ],
        DIMENSION_SIMILAR: [
            "Compare strongest precedent",
            "Explain in simple language",
            "Statutory basis",
        ],
        DIMENSION_COMPARISON: [
            "Compare with related provision",
            "Explain in simple language",
            "Recent court interpretation",
        ],
        DIMENSION_STATUTORY: [
            "Compare IPC vs BNS equivalent",
            "Explain punishment simply",
            "Recent court interpretation",
        ],
        DIMENSION_NEWS: [
            "Official gazette link",
            "Impact on practitioners",
            "Related sections",
        ],
    }
    return mapping.get(
        dimension,
        ["Explain in simple language", "Summarize key points", "Show official sources"],
    )


def _prepare_open_law_call(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build prompts + config for grounded Open Law (sync or stream)."""
    raw_q = (query or "").strip()
    try:
        from legal_web_query import build_web_search_query

        q = build_web_search_query(raw_q, conversation_history)
    except ImportError:
        q = raw_q
    if not q:
        q = raw_q
    profile = classify_open_law_request(raw_q or q)
    dimension = profile["dimension"]
    depth = profile["depth"]
    word_cap = profile["word_cap"]
    persona = ""
    memory_block = ""
    web_history = conversation_history
    try:
        from legal_web_query import is_self_contained_web_query

        if is_self_contained_web_query(q):
            web_history = None
        else:
            web_history = _filter_open_law_history(conversation_history)
    except ImportError:
        web_history = _filter_open_law_history(conversation_history)

    if user_id and depth != DEPTH_QUICK:
        try:
            from backend.app.core.user_memory import build_memory_context

            mem = build_memory_context(user_id, thread_id=thread_id, query=q)
            if mem.get("enabled"):
                persona = mem.get("persona_prompt", "")
                memory_block = mem.get("memory_block", "")
        except Exception:
            pass

    system = _system_prompt(
        dimension, persona=persona, memory_block=memory_block, depth=depth
    )
    user = _user_prompt(q, dimension, web_history, depth=depth, word_cap=word_cap)
    temp = 0.12 if depth == DEPTH_QUICK else (0.18 if depth == DEPTH_STANDARD else 0.22)
    return {
        "query": q,
        "profile": profile,
        "system": system,
        "user": user,
        "dimension": dimension,
        "depth": depth,
        "temperature": temp,
        "max_output_tokens": _max_tokens(dimension, depth),
    }


def _finalize_open_law_answer(
    answer: str,
    response: Any,
    *,
    dimension: str,
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    text = (answer or _extract_text(response)).strip()
    sources = _extract_sources(response) if response is not None else []
    try:
        from backend.app.core.source_badges import enrich_web_sources

        sources = enrich_web_sources(sources)
    except Exception:
        pass
    if not text:
        text = (
            "## Open Law Intelligence\n\n"
            "No response was returned. Try rephrasing with specific legal context "
            "(statute, section, case name, or court)."
        )
    try:
        from backend.app.core.web_answer_cleaner import polish_research_answer

        text = polish_research_answer(text)
    except ImportError:
        pass
    if DISCLAIMER.strip() not in text:
        text = text.rstrip() + DISCLAIMER
    return text, sources, _follow_ups(dimension)


def stream_grounded_legal_research(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    membership: str = "Free",
) -> Generator[Dict[str, Any], None, None]:
    """
    Stream Gemini grounded legal research token-by-token.
    Yields {"type": "token", "text": "..."} then {"type": "done", ...}.
    """
    if not gemini_configured():
        raise RuntimeError("GEMINI_API_KEY is not configured")

    if user_id:
        try:
            from backend.app.core.gemini_usage import assert_gemini_allowed

            assert_gemini_allowed(str(user_id), membership)
        except RuntimeError:
            raise
        except Exception:
            pass

    from backend.app.core.research_progress import (
        WEB_ANALYZE,
        WEB_COLLECT,
        WEB_COMPOSE,
        WEB_PREP,
        WEB_SEARCH,
        status_event,
    )

    yield status_event(WEB_PREP)
    prep = _prepare_open_law_call(
        query, conversation_history, user_id=user_id, thread_id=thread_id
    )
    q = prep["query"]
    if not q:
        yield {
            "type": "done",
            "answer": "### Open Law\n\nPlease enter a legal research question.",
            "sources": [],
            "follow_ups": [],
        }
        return

    yield status_event(WEB_SEARCH)
    from google.genai import types

    client = _get_client()
    if WEB_INTELLIGENCE_DEBUG:
        logger.info(
            "[WEB INTEL stream] dimension=%s depth=%s query=%s",
            prep["dimension"],
            prep["depth"],
            q[:120],
        )

    final_response: Any = None
    parts: List[str] = []
    saw_tokens = False
    try:
        yield status_event(WEB_COLLECT)
        stream = client.models.generate_content_stream(
            model=GEMINI_FREE_MODEL,
            contents=prep["user"],
            config=types.GenerateContentConfig(
                system_instruction=prep["system"],
                temperature=prep["temperature"],
                max_output_tokens=prep["max_output_tokens"],
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        for chunk in stream:
            final_response = chunk
            piece = (getattr(chunk, "text", None) or "").strip()
            if not piece:
                try:
                    piece = _extract_text(chunk)
                except Exception:
                    piece = ""
            if piece:
                if not saw_tokens:
                    yield status_event(WEB_ANALYZE)
                    saw_tokens = True
                parts.append(piece)
                yield {"type": "token", "text": piece}
    except OSError as exc:
        logger.warning("Open Law stream OSError (%s) — falling back to sync Gemini", exc)
        try:
            response = client.models.generate_content(
                model=GEMINI_FREE_MODEL,
                contents=prep["user"],
                config=types.GenerateContentConfig(
                    system_instruction=prep["system"],
                    temperature=prep["temperature"],
                    max_output_tokens=prep["max_output_tokens"],
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            answer, sources, follow_ups = _finalize_open_law_answer(
                "",
                response,
                dimension=prep["dimension"],
            )
            if answer:
                yield {"type": "token", "text": answer}
            if user_id:
                try:
                    from backend.app.core.gemini_usage import record_gemini_call

                    record_gemini_call(str(user_id))
                except Exception:
                    pass
            yield {"type": "done", "answer": answer, "sources": sources, "follow_ups": follow_ups}
            return
        except Exception as sync_exc:
            logger.warning("Open Law sync fallback also failed: %s", sync_exc)
            raise exc from sync_exc
    except Exception as exc:
        from backend.app.core.gemini_errors import is_gemini_quota_error, mark_gemini_quota_exhausted

        if is_gemini_quota_error(exc):
            mark_gemini_quota_exhausted()
            logger.warning("Open Law stream quota exhausted — skipping sync retry")
            yield {"type": "done", "answer": "", "sources": [], "follow_ups": []}
            return
        logger.warning("Open Law stream failed (%s) — falling back to sync Gemini", exc)
        try:
            response = client.models.generate_content(
                model=GEMINI_FREE_MODEL,
                contents=prep["user"],
                config=types.GenerateContentConfig(
                    system_instruction=prep["system"],
                    temperature=prep["temperature"],
                    max_output_tokens=prep["max_output_tokens"],
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            answer, sources, follow_ups = _finalize_open_law_answer(
                "",
                response,
                dimension=prep["dimension"],
            )
            if answer:
                yield {"type": "token", "text": answer}
            if user_id:
                try:
                    from backend.app.core.gemini_usage import record_gemini_call

                    record_gemini_call(str(user_id))
                except Exception:
                    pass
            yield {"type": "done", "answer": answer, "sources": sources, "follow_ups": follow_ups}
            return
        except Exception as sync_exc:
            logger.warning("Open Law sync fallback also failed: %s", sync_exc)
            raise exc from sync_exc

    if not saw_tokens:
        yield status_event(WEB_ANALYZE)
    yield status_event(WEB_COMPOSE)
    answer, sources, follow_ups = _finalize_open_law_answer(
        "".join(parts),
        final_response,
        dimension=prep["dimension"],
    )

    if user_id:
        try:
            from backend.app.core.gemini_usage import record_gemini_call

            record_gemini_call(str(user_id))
        except Exception:
            pass

    yield {
        "type": "done",
        "answer": answer,
        "sources": sources,
        "follow_ups": follow_ups,
    }


def run_grounded_legal_research(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    membership: str = "Free",
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Execute Gemini grounded legal research.
    Returns (markdown_answer, web_sources, follow_ups).
    """
    if not gemini_configured():
        raise RuntimeError("GEMINI_API_KEY is not configured")

    if user_id:
        try:
            from backend.app.core.gemini_usage import assert_gemini_allowed

            assert_gemini_allowed(str(user_id), membership)
        except RuntimeError:
            raise
        except Exception:
            pass

    q = (query or "").strip()
    if not q:
        return ("### Open Law\n\nPlease enter a legal research question.", [], [])

    prep = _prepare_open_law_call(
        q, conversation_history, user_id=user_id, thread_id=thread_id
    )

    from google.genai import types

    client = _get_client()
    if WEB_INTELLIGENCE_DEBUG:
        logger.info(
            "[WEB INTEL] dimension=%s depth=%s query=%s",
            prep["dimension"],
            prep["depth"],
            q[:120],
        )

    response = client.models.generate_content(
        model=GEMINI_FREE_MODEL,
        contents=prep["user"],
        config=types.GenerateContentConfig(
            system_instruction=prep["system"],
            temperature=prep["temperature"],
            max_output_tokens=prep["max_output_tokens"],
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )

    answer, sources, follow_ups = _finalize_open_law_answer(
        "",
        response,
        dimension=prep["dimension"],
    )

    if user_id:
        try:
            from backend.app.core.gemini_usage import record_gemini_call

            record_gemini_call(str(user_id))
        except Exception:
            pass

    if WEB_INTELLIGENCE_DEBUG:
        logger.info("[WEB INTEL] answer_len=%s sources=%s", len(answer), len(sources))

    return answer, sources, follow_ups


def grounded_search_snippets(
    query: str,
    max_results: int = 6,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Compatibility adapter — returns snippet list for legacy hybrid/search_web callers.
    """
    try:
        answer, sources, _ = run_grounded_legal_research(query, conversation_history)
    except Exception as exc:
        logger.warning("Open Law web search failed: %s", exc)
        return [{
            "title": "Open Law web search error",
            "href": "",
            "body": str(exc),
            "date": datetime.now(timezone.utc).date().isoformat(),
            "provider": "Unavailable",
        }]

    snippets = list(sources[:max_results])
    if not snippets and answer:
        snippets.append({
            "title": "Open Law Web Research",
            "href": "",
            "body": answer[:800],
            "date": datetime.now(timezone.utc).date().isoformat(),
            "provider": "Open Law Web Search",
        })
    return snippets


def auto_improve_from_interaction(
    user_id: str,
    query: str,
    answer: str,
    *,
    signal: str = "thumbs_up",
) -> Dict[str, Any]:
    """
    Hook after successful web turns — feeds adaptive + neural learning pipelines.
    """
    result: Dict[str, Any] = {"ok": True}
    try:
        from backend.app.core.learning_engine import learn_from_web_success

        learn_from_web_success(user_id, query, answer)
        result["learned"] = True
    except Exception as exc:
        result["learned"] = False
        result["learn_error"] = str(exc)

    if signal == "thumbs_up":
        try:
            from backend.app.core.neural_finetuning import maybe_auto_train

            train = maybe_auto_train(user_id)
            if train:
                result["auto_train"] = train
        except Exception:
            pass
    return result


def _format_kb_evidence(kb_answer: str, kb_chunks: Optional[List[Dict[str, Any]]]) -> str:
    """Format KB chunks for Gemini jurisprudence synthesis."""
    parts: List[str] = []
    kb = (kb_answer or "").strip()
    if kb and not kb.startswith("NOT_FOUND") and "couldn't find" not in kb.lower():
        parts.append(f"KB SYNTHESIZED ANSWER:\n{kb[:3000]}")
    chunks = kb_chunks or []
    for i, ch in enumerate(chunks[:14], 1):
        meta = ch.get("metadata") or {}
        if not meta and isinstance(ch, dict):
            meta = ch
        fn = meta.get("filename") or ch.get("filename") or "document"
        sec = meta.get("section") or meta.get("section_label") or ""
        content = (ch.get("content") or ch.get("excerpt") or "")[:900]
        if not content:
            continue
        label = f"[KB-{i}] {fn}"
        if sec:
            label += f" §{sec}"
        score = ch.get("final_score") or ch.get("hybrid_score") or ch.get("score")
        if score is not None:
            label += f" (relevance {float(score):.2f})"
        parts.append(f"{label}\n{content}")
    if not parts:
        return "No indexed document evidence retrieved for this query."
    return "\n\n".join(parts)


def _jurisprudence_system_prompt(*, persona: str = "", memory_block: str = "") -> str:
    sections = "\n".join(f"- ## {s}" for s in _JURISPRUDENCE_SECTIONS)
    base = (
        "You are LegalEase Jurisprudence Engine — India's deepest legal research analyst.\n"
        "You combine uploaded document intelligence (Knowledge Base) with real-time Google Search "
        "grounding across Indian courts, gazettes, statutes, and legal news.\n\n"
        "STRICT RULES:\n"
        "- Output ONLY professional Markdown with ## headers exactly as listed below.\n"
        "- When KB evidence is provided, uploaded documents win on conflict — cite as [KB-1], [KB-2].\n"
        "- When KB says no relevant uploads, use ONLY web sources — never cite [KB-N].\n"
        "- Public/web claims cite as [WEB-1], [WEB-2] with markdown links in Sources.\n"
        "- Use Google Search to fill gaps: live hearings, gazette notifications, recent judgments, "
        "BNS/BNSS/BSA mappings, similar case clusters, and verdict trends.\n"
        "- In Reconciliation, explicitly note any KB vs public law differences.\n"
        "- Be analytical — senior advocate research memo, not a snippet dump.\n"
        "- India jurisdiction unless stated otherwise.\n\n"
        f"REQUIRED SECTIONS (in order):\n{sections}\n"
    )
    if persona:
        base += f"\nUSER STYLE: {persona[:500]}\n"
    if memory_block:
        base += f"\nUSER MEMORY:\n{memory_block[:700]}\n"
    return base


def synthesize_jurisprudence_report(
    query: str,
    kb_answer: str,
    kb_chunks: Optional[List[Dict[str, Any]]],
    web_answer: str,
    web_sources: Optional[List[Dict[str, Any]]],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    membership: str = "Free",
    *,
    use_google_search: bool = True,
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Fuse KB RAG + Gemini web intel into one Jurisprudence Deep Research Report.
    Uses Gemini with Google Search grounding for real-time enrichment.
    """
    if not gemini_configured():
        raise RuntimeError("GEMINI_API_KEY is not configured")

    if user_id:
        try:
            from backend.app.core.gemini_usage import assert_gemini_allowed

            assert_gemini_allowed(str(user_id), membership)
        except RuntimeError:
            raise
        except Exception:
            pass

    from google.genai import types

    q = (query or "").strip()
    kb_has_evidence = bool(kb_chunks) and not (
        (kb_answer or "").strip().startswith("NOT_FOUND")
        or "knowledge base empty" in (kb_answer or "").lower()
    )
    kb_block = (
        _format_kb_evidence(kb_answer, kb_chunks)
        if kb_has_evidence
        else "No relevant uploaded document evidence for this query."
    )
    web = (web_answer or "").strip()
    web_src = web_sources or []

    web_ref = ""
    if web:
        web_ref = f"GEMINI WEB INTELLIGENCE LAYER:\n{web[:4000]}"
    if web_src:
        links = "\n".join(
            f"[WEB-{i}] {s.get('title', 'Source')}: {s.get('href', '')}"
            for i, s in enumerate(web_src[:10], 1)
            if s.get("href")
        )
        if links:
            web_ref += f"\n\nWEB SOURCE LINKS:\n{links}"

    persona = ""
    memory_block = ""
    if user_id:
        try:
            from backend.app.core.user_memory import build_memory_context

            mem = build_memory_context(user_id, thread_id=thread_id, query=q)
            if mem.get("enabled"):
                persona = mem.get("persona_prompt", "")
                memory_block = mem.get("memory_block", "")
        except Exception:
            pass

    convo = _conversation_block(conversation_history)
    user_parts = [f"JURISPRUDENCE RESEARCH BRIEF:\n{q}"]
    if kb_has_evidence:
        user_parts.append(
            f"=== KNOWLEDGE BASE EVIDENCE (PRIORITY — cite [KB-N]) ===\n{kb_block}"
        )
    else:
        user_parts.append(
            "=== KNOWLEDGE BASE ===\n"
            "No uploaded document on this topic. Answer ONLY from public web intelligence. "
            "Do NOT cite [KB-N] or invent facts from unrelated uploaded cases."
        )
    if web_ref:
        user_parts.append(f"=== PUBLIC WEB INTELLIGENCE (cite [WEB-N]) ===\n{web_ref}")
    if convo:
        user_parts.insert(0, convo)
    user_parts.append(
        "Produce the full Jurisprudence Deep Research Report. "
        "Cross-verify KB against live public sources. "
        "Include similar case clusters and practical strategy where relevant."
    )
    user = "\n\n".join(user_parts)

    client = _get_client()
    max_out = int(os.getenv("HYBRID_MAX_OUTPUT_TOKENS", "4096"))
    max_out = max(1024, min(max_out, 8192))
    tools = [types.Tool(google_search=types.GoogleSearch())] if use_google_search else None
    if WEB_INTELLIGENCE_DEBUG:
        logger.info(
            "[JURISPRUDENCE] query=%s kb_chunks=%s web_sources=%s search=%s max_tokens=%s",
            q[:80],
            len(kb_chunks or []),
            len(web_src),
            use_google_search,
            max_out,
        )

    cfg_kw: Dict[str, Any] = {
        "system_instruction": _jurisprudence_system_prompt(persona=persona, memory_block=memory_block),
        "temperature": 0.2,
        "max_output_tokens": max_out,
    }
    if tools:
        cfg_kw["tools"] = tools
    response = client.models.generate_content(
        model=GEMINI_FREE_MODEL,
        contents=user,
        config=types.GenerateContentConfig(**cfg_kw),
    )

    report = _extract_text(response)
    sources = _extract_sources(response)
    # Merge web sources from earlier leg + grounding citations
    merged_sources: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in list(web_src) + sources:
        href = (row.get("href") or "").strip()
        if href and href in seen:
            continue
        if href:
            seen.add(href)
        merged_sources.append(row)

    try:
        from backend.app.core.source_badges import enrich_web_sources

        merged_sources = enrich_web_sources(merged_sources)
    except Exception:
        pass

    if user_id:
        try:
            from backend.app.core.gemini_usage import record_gemini_call

            record_gemini_call(str(user_id))
        except Exception:
            pass

    if not report:
        report = (
            "## Jurisprudence Deep Research Report\n\n"
            "_Gemini returned an empty synthesis. See KB and web layers below._\n\n"
            f"**Knowledge Base**\n{kb_block[:1500]}\n\n**Web Intelligence**\n{web[:1500]}"
        )

    if DISCLAIMER.strip() not in report:
        report = report.rstrip() + DISCLAIMER

    follow_ups = [
        "Expand similar case cluster analysis",
        "Latest hearing / gazette updates",
        "Explain in simple language",
        "Draft client memo from this report",
        "Show only KB document citations",
    ]
    return report, merged_sources, follow_ups


def run_jurisprudence_engine(
    query: str,
    kb_answer: str,
    kb_chunks: Optional[List[Dict[str, Any]]],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[str] = None,
) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    Full Jurisprudence combo: accepts pre-fetched KB, runs Gemini web + fusion report.
    """
    web_answer, web_sources, _ = run_grounded_legal_research(
        query, conversation_history, user_id=user_id
    )
    return synthesize_jurisprudence_report(
        query,
        kb_answer,
        kb_chunks,
        web_answer,
        web_sources,
        conversation_history=conversation_history,
        user_id=user_id,
    )
