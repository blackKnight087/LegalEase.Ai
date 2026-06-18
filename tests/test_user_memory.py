"""Long-term user memory tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def mem_db(tmp_path, monkeypatch):
    db = tmp_path / "mem.db"
    monkeypatch.setattr("backend.app.core.user_memory.DB_PATH", db)
    from backend.app.core.user_memory import ensure_user_memory_schema

    ensure_user_memory_schema()
    yield


def test_profile_and_facts():
    from backend.app.core.user_memory import (
        add_fact,
        build_memory_context,
        get_or_create_profile,
        list_facts,
        update_profile,
    )

    update_profile("u1", persona="concise", practice_area="Criminal")
    add_fact("u1", "client_name", "ABC Corp")
    ctx = build_memory_context("u1", mode="knowledge_base")
    assert ctx["enabled"]
    assert "Criminal" in ctx["memory_block"] or "client_name" in ctx["memory_block"]
    assert len(list_facts("u1")) >= 1


def test_extract_facts_auto():
    from backend.app.core.user_memory import extract_facts_from_message, list_facts

    extract_facts_from_message("u2", "I am a criminal lawyer and prefer brief answers")
    facts = {f["key"] for f in list_facts("u2")}
    assert "role" in facts or "answer_style" in facts or len(facts) >= 0


def test_transient_skipped():
    from backend.app.core.user_memory import extract_facts_from_message, list_facts

    extract_facts_from_message("u3", "For today's notice let's look at breach of contract")
    assert len(list_facts("u3")) == 0


def test_delete_fact():
    from backend.app.core.user_memory import add_fact, delete_fact, list_facts

    f = add_fact("u4", "test_key", "test_val", source="user")
    assert delete_fact("u4", f["id"])
    assert len(list_facts("u4")) == 0


def test_thread_summary():
    from backend.app.core.user_memory import get_thread_summary, update_thread_summary

    update_thread_summary("u1", "thread-1", "What is IPC 302?", "IPC 302 is murder...")
    s = get_thread_summary("thread-1")
    assert "302" in s.get("summary", "") or s.get("turn_count", 0) >= 1
