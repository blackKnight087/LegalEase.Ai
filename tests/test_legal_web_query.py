"""Open Law query isolation — no prior-turn pollution in web search."""
from __future__ import annotations

from legal_web_query import (
    build_web_search_query,
    enrich_web_query,
    is_detail_follow_up,
    is_self_contained_web_query,
    is_vague_web_follow_up,
    resolve_web_conversation_query,
    search_api_query,
)

def test_self_contained_section_comparison():
    q = "section 300 difference with 307"
    assert is_self_contained_web_query(q)
    api = search_api_query(q, _history_after_rg_kar())
    assert "rg karr" not in api.lower()
    assert "302" not in api
    assert "300" in api or "307" in api
    assert enrich_web_query(q, _history_after_rg_kar()) == q


def test_self_contained_rg_kar_case():
    q = "rg karr case"
    assert is_self_contained_web_query(q)
    api = search_api_query(q, _history_after_comparison())
    assert "302" not in api
    assert "rg" in api.lower() or "kar" in api.lower()
    assert enrich_web_query(q, _history_after_comparison()) == q


def test_vague_follow_up_gets_topic_not_full_answer():
    history = [
        {"role": "user", "content": "Explain IPC Section 307"},
        {"role": "assistant", "content": "IPC Section 307 covers attempt to murder with imprisonment up to ten years under the Indian Penal Code." * 3},
    ]
    q = "What punishment applies?"
    assert not is_self_contained_web_query(q)
    enriched = enrich_web_query(q, history)
    assert "307" in enriched or "attempt" in enriched.lower()
    assert "Prior answer excerpt" not in enriched


def _history_after_rg_kar():
    return [
        {"role": "user", "content": "rg karr case"},
        {"role": "assistant", "content": "RG Kar Medical College case Kolkata Supreme Court." * 5},
    ]


def _history_after_comparison():
    return [
        {"role": "user", "content": "Compare IPC 302 and BNS 103"},
        {"role": "assistant", "content": "IPC 302 is murder. BNS 103 is the new code equivalent." * 5},
    ]


def test_non_legal_query_rejected():
    from legal_web_query import looks_legal_query_for_web, non_legal_web_refusal

    history = [{"role": "user", "content": "Explain IPC 307"}]
    assert not looks_legal_query_for_web("is he single", history)
    assert "legal questions only" in non_legal_web_refusal("is he single").lower()
    q = build_web_search_query("section 300 difference with 307", None)
    assert "300" in q and "307" in q
    assert "difference" in q.lower() or "vs" in q.lower()


def test_explain_in_details_resolves_prior_topic():
    history = [
        {"role": "user", "content": "tell me more about epstein file"},
        {"role": "assistant", "content": "Brief summary about Epstein document releases." * 3},
    ]
    q = "explain in details"
    assert is_detail_follow_up(q)
    assert is_vague_web_follow_up(q)
    resolved = resolve_web_conversation_query(q, history)
    assert "epstein" in resolved.lower()
    assert "detail" in resolved.lower() or "comprehensive" in resolved.lower()
    assert resolved != q
    api = search_api_query(q, history)
    assert "epstein" in api.lower()


def test_prior_topic_skips_vague_user_turns():
    history = [
        {"role": "user", "content": "IPC Section 307 punishment"},
        {"role": "assistant", "content": "Section 307 covers attempt to murder." * 4},
        {"role": "user", "content": "explain in details"},
        {"role": "assistant", "content": "Short answer." * 2},
    ]
    q = "tell me more"
    resolved = resolve_web_conversation_query(q, history)
    assert "307" in resolved or "attempt" in resolved.lower()
    assert "explain in details" not in resolved.lower()


def test_tell_me_more_about_topic_is_self_contained():
    q = "tell me more about epstein file"
    assert is_self_contained_web_query(q)
    assert not is_vague_web_follow_up(q)


def test_compliment_not_expanded_to_prior_topic():
    from legal_web_query import (
        FEEDBACK_POSITIVE,
        build_acknowledgment_response,
        classify_conversational_feedback,
        is_conversational_acknowledgment,
    )

    history = [
        {"role": "user", "content": "What are fundamental rights under the Indian Constitution?"},
        {
            "role": "assistant",
            "content": "Fundamental rights are enshrined in Part III of the Constitution including equality, freedom, and remedy." * 4,
        },
    ]
    q = "good"
    assert classify_conversational_feedback(q, history) == FEEDBACK_POSITIVE
    assert is_conversational_acknowledgment(q, history)
    assert resolve_web_conversation_query(q, history) == q
    assert search_api_query(q, history) == q
    reply = build_acknowledgment_response(q, history)
    assert "Glad that helped" in reply
    assert "feedback" in reply.lower()
    assert "fundamental rights" in reply.lower() or "constitution" in reply.lower()


def test_negative_verbal_feedback_detected():
    from legal_web_query import (
        FEEDBACK_NEGATIVE,
        build_negative_feedback_response,
        classify_conversational_feedback,
        is_conversational_feedback,
    )

    history = [
        {"role": "user", "content": "Explain IPC Section 307 punishment"},
        {"role": "assistant", "content": "Section 307 covers attempt to murder under IPC." * 5},
    ]
    for q in ("not relevant", "missing details", "wrong answer", "can do better", "error"):
        assert classify_conversational_feedback(q, history) == FEEDBACK_NEGATIVE, q
        assert is_conversational_feedback(q, history)
        assert resolve_web_conversation_query(q, history) == q
    reply = build_negative_feedback_response("not relevant", history)
    assert "negative feedback" in reply.lower()
    assert "307" in reply or "attempt" in reply.lower()


def test_good_faith_is_not_acknowledgment():
    from legal_web_query import (
        classify_conversational_feedback,
        is_conversational_acknowledgment,
    )

    history = [
        {"role": "user", "content": "Explain contract law"},
        {"role": "assistant", "content": "Contract law governs agreements between parties." * 5},
    ]
    assert classify_conversational_feedback("good faith doctrine", history) is None
    assert not is_conversational_acknowledgment("good faith doctrine", history)
    assert classify_conversational_feedback("good", []) is None
