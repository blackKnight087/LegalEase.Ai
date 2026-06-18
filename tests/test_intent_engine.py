"""Tests for query intent classification."""
from intent_engine import QueryIntent, classify_intent, decompose_multi_intent


def test_factual_lookup():
    p = classify_intent("What is IPC 307?")
    assert p.primary == QueryIntent.FACTUAL_LOOKUP
    assert p.response_mode == "minimal"


def test_summarization():
    p = classify_intent("Summarize the criminal offences discussed in the document")
    assert p.primary == QueryIntent.SUMMARIZATION


def test_beginner():
    p = classify_intent("Explain the document in beginner-friendly language")
    assert p.primary == QueryIntent.BEGINNER_EXPLANATION


def test_comparison():
    p = classify_intent("Difference between IPC 299 and 300")
    assert p.primary == QueryIntent.COMPARISON
    assert p.response_mode == "table"


def test_list_extraction():
    p = classify_intent("List all IPC sections mentioned")
    assert p.primary == QueryIntent.LIST_EXTRACTION


def test_multi_intent():
    p = classify_intent("Difference between 299 and 300 and list all sections")
    assert p.primary == QueryIntent.MULTI_INTENT
    assert len(p.subtasks) >= 2


def test_follow_up():
    messages = [
        {"role": "user", "content": "What is IPC 307?"},
        {"role": "assistant", "content": "IPC 307 deals with attempt to murder."},
    ]
    p = classify_intent("What punishment does it carry?", messages)
    assert p.primary == QueryIntent.FOLLOW_UP_CONTEXT
    assert p.is_follow_up
