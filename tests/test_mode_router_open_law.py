"""Mode router — ensure Open Law and Hybrid stay separate."""
from __future__ import annotations

from backend.app.services.mode_router import route_query


def test_web_search_stays_open_law():
    decision = route_query("explain rg kar case", "web_search", history=[])
    assert decision.mode == "open_law"
    assert decision.reason == "user_open_law"


def test_deep_case_stays_hybrid_for_pro():
    from backend.app.services.chat_service import _apply_plan_route_guard
    from backend.app.services.mode_router import route_query

    decision = route_query("full analysis section 302", "deep_case", history=[])
    assert decision.mode == "hybrid"
    assert _apply_plan_route_guard(decision.mode, "Pro") == "hybrid"
    assert _apply_plan_route_guard(decision.mode, "Free") == "knowledge_base"


def test_web_search_not_routed_to_hybrid():
    """Regression: web_search must never fall through to hybrid/jurisprudence."""
    decision = route_query("IPC 300 vs 307", "web_search", history=[])
    assert decision.mode != "hybrid"
    assert decision.mode == "open_law"


def test_kb_case_explanation_stays_kb_when_indexed():
    """User-selected KB must not auto-upgrade to Hybrid for case questions."""
    decision = route_query(
        "Explain the Nirbhaya case in simple language",
        "knowledge_base",
        history=[],
        has_kb_index=True,
    )
    assert decision.mode == "knowledge_base"
    assert decision.reason == "user_kb"
