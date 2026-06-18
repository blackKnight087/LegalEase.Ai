"""
Mode Router — dispatch KB / Open Law / Hybrid with intent-aware overrides.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.legal_engine.query_parser import LegalQueryParse, parse_legal_query


@dataclass
class RouteDecision:
    mode: str
    parse: LegalQueryParse
    effective_query: str
    reason: str = ""


def route_query(
    query: str,
    requested_mode: str,
    history: Optional[List[Dict]] = None,
    *,
    session_state: Optional[Dict[str, Any]] = None,
    has_kb_index: bool = True,
) -> RouteDecision:
    """
    Route user query to the best backend mode while respecting user selection.

    User-selected mode wins. Only auto-fallback when KB is empty and user asked for KB.
    """
    mode = (requested_mode or "knowledge_base").strip().lower()
    if mode in ("kb", "document", "documents"):
        mode = "knowledge_base"
    elif mode in ("open_law", "web", "openlaw", "web_search"):
        mode = "open_law"
    elif mode in ("hybrid", "jurisprudence", "deep", "deep_case", "deepstudy", "deep_study"):
        mode = "hybrid"

    parse = parse_legal_query(query, history, session_state=session_state)
    effective = parse.resolved_query or query

    # Never auto-switch KB mode to Open Law — stay on KB path (empty index handled in KB gate).
    if mode == "knowledge_base":
        return RouteDecision("knowledge_base", parse, effective, "user_kb")

    if mode == "open_law":
        return RouteDecision("open_law", parse, effective, "user_open_law")

    # Hybrid — merge KB + trusted web; uploaded docs take priority
    return RouteDecision("hybrid", parse, effective, "user_hybrid")
