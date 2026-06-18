"""
User-visible progress labels for Web Intel / Hybrid streaming (SSE status events).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

StatusEvent = Dict[str, str]
ResultEvent = Dict[str, Any]


def clean_status_text(text: str) -> str:
    """Plain UI line — no markdown bullets or trailing newlines."""
    t = re.sub(r"\*+", "", (text or "").strip())
    t = re.sub(r"\s+", " ", t).strip()
    return t


def status_event(message: str) -> StatusEvent:
    return {"type": "status", "message": clean_status_text(message)}


def result_event(
    content: str,
    similar_cases: List[Dict],
    web_sources: List[Dict],
    follow_ups: Optional[List[str]] = None,
) -> ResultEvent:
    return {
        "type": "result",
        "content": content,
        "similar_cases": similar_cases,
        "web_sources": web_sources,
        "follow_ups": follow_ups or [],
    }


# Hybrid / Jurisprudence
HYBRID_SEARCH_KB = "Searching your uploaded documents…"
HYBRID_COLLECT_WEB = "Collecting live legal information…"
HYBRID_ANALYZE = "Analyzing and cross-checking sources…"
HYBRID_COMPOSE = "Composing your research report…"
HYBRID_FINALIZE = "Finalizing answer…"

# Web Intel / Open Law
WEB_PREP = "Understanding your question…"
WEB_SEARCH = "Searching live legal sources…"
WEB_COLLECT = "Collecting relevant information…"
WEB_ANALYZE = "Analyzing legal sources…"
WEB_COMPOSE = "Composing your answer…"
