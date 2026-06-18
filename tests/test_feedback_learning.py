"""Feedback learning queue tests."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.ci_gate

from backend.app.core.feedback_learning import (
    enqueue_feedback,
    ensure_feedback_learning_schema,
    list_review_queue,
    review_item,
)


def test_enqueue_thumbs_down():
    ensure_feedback_learning_schema()
    out = enqueue_feedback(
        "user-fl-1",
        signal="thumbs_down",
        query_text="What is Section 302?",
        answer_text="Not found.",
        mode="knowledge_base",
        confidence=0.2,
    )
    assert out.get("ok") is True
    assert out.get("queue_id")


def test_review_approve():
    ensure_feedback_learning_schema()
    en = enqueue_feedback("user-fl-2", signal="thumbs_down", query_text="q", answer_text="a")
    qid = en["queue_id"]
    items = list_review_queue(status="pending", user_id="user-fl-2")
    assert any(i["queue_id"] == qid for i in items)
    rev = review_item(qid, "admin-1", action="approve", notes="ok")
    assert rev.get("ok") is True
    assert rev.get("status") == "approved"


def test_low_confidence_signal():
    out = enqueue_feedback(
        "user-fl-3",
        signal="low_confidence",
        confidence=0.35,
    )
    assert out.get("ok") is True
