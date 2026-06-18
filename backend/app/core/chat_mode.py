"""
Normalize chat mode strings from the web UI and API to backend-canonical values.

The UI may send open_law, hybrid, web_search, or deep_case — all must reach chat_service.
"""
from __future__ import annotations

# Canonical modes consumed by chat_service / mode_router
CANONICAL_MODES = frozenset({"knowledge_base", "web_search", "deep_case", "open_law", "hybrid"})


def normalize_api_chat_mode(mode: str, membership: str = "Free") -> str:
    """
    Map aliases to a mode chat_service understands.

    Returns one of: knowledge_base, web_search, deep_case, open_law, hybrid
    (open_law and hybrid are aliases kept for escalate flows; web_search/deep_case match ModePills).
    """
    raw = (mode or "knowledge_base").strip().lower()
    if raw in ("kb", "document", "documents"):
        out = "knowledge_base"
    elif raw in ("web", "openlaw", "open_law", "web_search"):
        out = "open_law" if raw == "open_law" else "web_search"
    elif raw in ("hybrid", "deep", "deep_case", "deepstudy", "deep_study", "jurisprudence"):
        out = "hybrid" if raw == "hybrid" else "deep_case"
    elif raw in CANONICAL_MODES:
        out = raw
    else:
        out = "knowledge_base"

    if out in ("hybrid", "deep_case") and str(membership) not in ("Pro", "Legal Pro"):
        try:
            from backend.app.core.plan_enforcement import free_hybrid_allowed

            if not free_hybrid_allowed():
                out = "knowledge_base"
        except Exception:
            out = "knowledge_base"

    # region agent log
    if raw != out:
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "H5",
                "chat_mode.py:normalize_api_chat_mode",
                "mode_normalized",
                {"raw": raw, "out": out, "membership": membership},
                run_id="open-law-fix",
            )
        except Exception:
            pass
    # endregion

    return out


def mode_requires_web_intelligence(mode: str) -> bool:
    return (mode or "").strip().lower() in (
        "web_search",
        "open_law",
        "hybrid",
        "deep_case",
    )
