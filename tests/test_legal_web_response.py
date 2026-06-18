"""Legal web engine — no JSON, source ranking, case detection."""
from __future__ import annotations

import pytest

from intent_engine import classify_intent
from legal_web_engine import (
    clean_snippet_body,
    intent_compose_from_snippets,
    is_case_law_query,
    json_response_to_markdown,
    looks_like_json_response,
    needs_llm_synthesis,
    rank_legal_snippets,
    resolve_web_response_kind,
    sanitize_legal_display,
    wants_detailed_explain,
    wants_plain_language_explain,
)


def test_rejects_json_display():
    raw = '{"Nirbhaya Case": 2012, "Fearless": "", "Justice Reform": ""}'
    assert looks_like_json_response(raw)
    out = sanitize_legal_display(raw)
    assert "{" not in out[:20] or "**Nirbhaya" in out
    assert "2012" in out


def test_case_law_detection():
    assert is_case_law_query("Nirbhaya case")
    assert is_case_law_query("Kesavananda Bharati judgment")
    assert not is_case_law_query("what is the weather today")


def test_source_ranking_deprioritizes_wikipedia():
    snippets = [
        {"title": "Wiki", "href": "https://en.wikipedia.org/wiki/X", "body": "x"},
        {"title": "IK", "href": "https://indiankanoon.org/doc/1", "body": "y" * 100},
        {"title": "LiveLaw", "href": "https://livelaw.in/news/1", "body": "z" * 50},
    ]
    ranked = rank_legal_snippets(snippets)
    assert "indiankanoon" in ranked[0]["href"]


def test_plain_explain_intent():
    assert wants_plain_language_explain("Explain in simple language")
    assert wants_plain_language_explain("explain")
    assert wants_detailed_explain("explain in details")
    assert wants_detailed_explain("go deeper")


def test_clean_snippet_body_strips_junk():
    raw = (
        "Skip to main content. Getty Images Epstein is wearing a brown hooded top. "
        "Our editors will review what you've submitted. "
        "The Epstein files refer to court documents released in 2024 regarding Jeffrey Epstein."
    )
    cleaned = clean_snippet_body(raw)
    assert "getty images" not in cleaned.lower()
    assert "editors will review" not in cleaned.lower()
    assert "epstein files" in cleaned.lower()


def test_needs_llm_synthesis_for_detail_queries():
    snippets = [
        {"title": "T", "href": "https://livelaw.in/x", "body": "Legal context about the topic."},
    ]
    assert needs_llm_synthesis(
        "Provide a comprehensive detailed explanation about epstein files",
        [{"role": "user", "content": "epstein files"}],
        "general",
        snippets,
    )


@pytest.mark.parametrize(
    "query",
    ["Kesavananda Bharati", "Vishaka Case", "fake_case_xyz_999_not_real"],
)
def test_hallucination_safe_fallback_markdown(query):
    """Fake case should still return markdown structure from fallback, not JSON."""
    from legal_web_engine import _fallback_markdown_from_snippets

    out = _fallback_markdown_from_snippets(query, [])
    assert "##" in out
    assert not looks_like_json_response(out)


def test_intent_templates():
    assert resolve_web_response_kind("Nirbhaya case", classify_intent("Nirbhaya case")) == "case_brief"
    assert resolve_web_response_kind("cji of india", classify_intent("cji of india")) == "factual"
    assert resolve_web_response_kind(
        "difference between IPC 302 and 304",
        classify_intent("difference between IPC 302 and 304"),
    ) == "comparison"


def test_intent_compose_has_sections():
    snippets = [
        {"title": "CJI", "href": "https://main.sci.gov.in/chief-justice", "body": "Chief Justice of India is ..."},
        {"title": "News", "href": "https://livelaw.in/cji", "body": "Appointment details ..."},
    ]
    text, fus = intent_compose_from_snippets("cji of india", snippets, "factual")
    assert "## Direct Answer" in text
    assert "## Sources" in text
    assert fus
