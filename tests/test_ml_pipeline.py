"""Tests for ML pipeline: preferences, follow-ups, guards, schedules."""
from __future__ import annotations

import json

import pytest


def test_kb_request_classifier_depth():
    from backend.app.core.kb_request_classifier import classify_kb_request, DEPTH_DETAILED

    c = classify_kb_request("Explain IPC 302 in detail with all elements")
    assert c["depth"] == DEPTH_DETAILED
    assert c["needs_citations"] is True


def test_follow_up_intent_punishment():
    from backend.app.core.follow_up_intent import classify_follow_up_intent, INTENT_PUNISHMENT

    mem = {"last_section": "307", "last_law": "IPC", "last_topic": "IPC Section 307"}
    info = classify_follow_up_intent("What is the punishment?", mem)
    assert info["intent"] == INTENT_PUNISHMENT
    assert info["is_follow_up"] is True


def test_follow_up_intent_new_topic():
    from backend.app.core.follow_up_intent import classify_follow_up_intent, INTENT_NEW_TOPIC

    info = classify_follow_up_intent("What is contract law?", {})
    assert info["intent"] == INTENT_NEW_TOPIC


def test_coach_guards_block_legal_substance():
    from backend.app.core.coach_guards import sanitize_coach_style_text, validate_coach_insights

    assert sanitize_coach_style_text("IPC Section 302 punishment is life imprisonment") == ""
    raw = {
        "persona_suggestion": "concise",
        "communication_notes_addition": "Use bullet points for clarity",
        "suggested_facts": [{"key": "ipc_section", "value": "302 is murder"}],
        "training_pairs": [{"q": "x", "a": "y"}],
        "preference_updates": {"detail_level": 0.9, "illegal_key": "bad"},
    }
    cleaned, rejections = validate_coach_insights(raw)
    assert cleaned.get("persona_suggestion") == "concise"
    assert "training_pairs" not in cleaned
    assert cleaned.get("preference_updates", {}).get("detail_level") == 0.9
    assert any("fact_blocked" in r or "pref_key_blocked" in r for r in rejections)


def test_user_preferences_learn_from_feedback():
    from backend.app.core.user_preferences import (
        ensure_preferences_schema,
        get_preference_profile,
        learn_from_feedback_signal,
    )

    ensure_preferences_schema()
    uid = "test_pref_user_1"
    learn_from_feedback_signal(
        uid,
        "thumbs_up",
        query="Explain in detail the elements of murder",
        answer_preview="## Elements\n- Intention\n- Act\n",
    )
    prof = get_preference_profile(uid)["profile"]
    assert float(prof.get("detail_level", 0)) >= 0.55
    assert prof.get("depth") in ("detailed", "standard", "comparison", "quick")


def test_human_training_label_and_sft_export(tmp_path, monkeypatch):
    from backend.app.core.adaptive_learning import ensure_learning_schema, record_interaction, record_feedback
    from backend.app.core.human_training import (
        ensure_human_training_schema,
        export_sft_jsonl,
        record_human_label,
        training_pipeline_status,
    )

    ensure_learning_schema()
    ensure_human_training_schema()
    uid = "test_train_user_1"
    iid = record_interaction(
        uid,
        "knowledge_base",
        "What is IPC 302?",
        answer="IPC Section 302 deals with murder and prescribes punishment.",
        found_in_kb=True,
    )
    record_feedback(uid, interaction_id=iid, signal="thumbs_up")
    label = record_human_label(
        uid,
        interaction_id=iid,
        signal="thumbs_up",
        query="What is IPC 302?",
        answer_preview="IPC Section 302 deals with murder.",
    )
    assert label.get("ok") is True
    status = training_pipeline_status(uid)
    assert status["human_labels"] >= 1
    export = export_sft_jsonl(uid, limit=10)
    assert export.get("record_count", 0) >= 0


def test_coach_schedule_tiers():
    from backend.app.core.coach_scheduler import get_schedule_prefs

    sched = get_schedule_prefs("nonexistent_user_schedule_test")
    assert "daily" in sched
    assert "weekly" in sched
    assert "monthly" in sched
    assert sched["daily"]["interval_days"] >= 1


def test_retrieval_learning_expansion():
    from backend.app.core.retrieval_learning import build_semantic_expansion

    exp = build_semantic_expansion(
        "What is IPC 302?",
        "Section 302 IPC murder punishment life imprisonment",
    )
    assert "302" in exp or "ipc" in exp.lower()


def test_resolve_follow_up_with_semantic_intent():
    from backend.app.core.conversation_memory import resolve_follow_up_query

    mem = {"last_section": "307", "last_law": "IPC", "last_topic": "IPC Section 307"}
    resolved = resolve_follow_up_query("What is punishment?", mem)
    assert "307" in resolved or "punishment" in resolved.lower()
