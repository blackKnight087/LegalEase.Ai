"""Tests for expanded learning signals."""
from __future__ import annotations


def test_signal_rewards():
    from backend.app.core.learning_signals import signal_reward

    assert signal_reward("thumbs_up") == 1.0
    assert signal_reward("copy") > 0
    assert signal_reward("regenerate") < 0
    assert signal_reward("dwell_time", metadata={"dwell_ms": 50000}) > 0.2


def test_apply_tags_to_preferences():
    from backend.app.core.learning_signals import apply_tags_to_preferences, ensure_signal_schema
    from backend.app.core.user_preferences import get_preference_profile

    ensure_signal_schema()
    uid = "test_signal_tags_user"
    n = apply_tags_to_preferences(uid, ["too_long", "good_structure"])
    assert n >= 1
    prof = get_preference_profile(uid)["profile"]
    assert float(prof.get("prefer_concise", 0)) >= 0.55


def test_record_signal_event():
    from backend.app.core.learning_signals import ensure_signal_schema, record_signal_event, signal_stats

    ensure_signal_schema()
    uid = "test_signal_event_user"
    ev = record_signal_event(uid, "follow_up_click", metadata={"follow_up": "What is punishment?"})
    assert ev.get("ok") is True
    stats = signal_stats(uid)
    assert stats["events_by_signal"].get("follow_up_click", 0) >= 1


def test_regenerate_chain():
    from backend.app.core.adaptive_learning import ensure_learning_schema, record_interaction
    from backend.app.core.learning_signals import (
        ensure_signal_schema,
        register_regenerate,
        resolve_regenerate_chain,
    )

    ensure_learning_schema()
    ensure_signal_schema()
    uid = "test_regen_chain_user"
    iid = record_interaction(
        uid,
        "knowledge_base",
        "Explain IPC 302",
        answer="Short wrong answer.",
        found_in_kb=True,
    )
    chain = register_regenerate(uid, interaction_id=iid, query="Explain IPC 302", answer_preview="Short wrong answer.")
    assert chain
    iid2 = record_interaction(
        uid,
        "knowledge_base",
        "Explain IPC 302",
        answer="Better detailed answer about murder section.",
        found_in_kb=True,
    )
    resolved = resolve_regenerate_chain(
        uid,
        replacement_interaction_id=iid2,
        replacement_answer="Better detailed answer about murder section.",
    )
    assert resolved == chain


def test_edit_diff_pair():
    from backend.app.core.learning_signals import ensure_signal_schema, record_edit_diff_pair

    ensure_signal_schema()
    uid = "test_edit_diff_user"
    res = record_edit_diff_pair(
        uid,
        interaction_id="fake-iid",
        query="What is bail?",
        original_answer="Bail is release from custody pending trial.",
        edited_answer="Bail is release from custody pending trial, subject to conditions.",
    )
    assert res.get("ok") is True


def test_process_learning_signal_copy():
    from backend.app.core.adaptive_learning import ensure_learning_schema, record_interaction
    from backend.app.core.learning_signals import ensure_signal_schema, process_learning_signal

    ensure_learning_schema()
    ensure_signal_schema()
    uid = "test_copy_signal_user"
    iid = record_interaction(
        uid,
        "knowledge_base",
        "Define bail",
        answer="Bail allows release from custody with conditions set by the court.",
        found_in_kb=True,
    )
    result = process_learning_signal(
        uid,
        "copy",
        interaction_id=iid,
        membership="Free",
    )
    assert result.get("ok") is True


def test_process_mode_switch():
    from backend.app.core.learning_signals import ensure_signal_schema, process_mode_switch

    ensure_signal_schema()
    result = process_mode_switch(
        "test_mode_switch_user",
        from_mode="knowledge_base",
        to_mode="open_law",
        interaction_id="x",
        query="IPC 302 punishment",
    )
    assert result.get("ok") is True
