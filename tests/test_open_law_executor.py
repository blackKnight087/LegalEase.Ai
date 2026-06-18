"""Contract tests for Open Law executor — prevents tuple unpack regressions."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.chat_turn_types import ChatTurnResult
from backend.app.services.open_law_executor import (
    fetch_open_law_answer,
    merge_stream_buffer,
    needs_open_law_fallback,
)


def test_chat_turn_result_as_tuple_has_four_fields():
    turn = ChatTurnResult(
        content="Bail is conditional release.",
        similar_cases=[{"title": "Case A"}],
        web_sources=[{"title": "Source"}],
        follow_ups=["Explain in simple language"],
    )
    packed = turn.as_tuple()
    assert len(packed) == 4
    content, similar_cases, web_sources, follow_ups = packed
    assert "Bail" in content
    assert similar_cases[0]["title"] == "Case A"
    assert web_sources[0]["title"] == "Source"
    assert follow_ups[0] == "Explain in simple language"


def test_chat_turn_result_from_tuple_rejects_wrong_arity():
    with pytest.raises(ValueError, match="expects 4 values"):
        ChatTurnResult.from_tuple(("only", "three", "values"))  # type: ignore[arg-type]


def test_merge_stream_buffer_uses_tokens_when_answer_empty():
    assert merge_stream_buffer("", ["Bail ", "is release."]) == "Bail is release."


def test_needs_open_law_fallback_false_when_stream_has_text():
    assert needs_open_law_fallback("", ["Bail definition here."]) is False


@patch("backend.app.services.open_law_executor._from_web_search")
@patch("backend.app.services.open_law_executor._from_grounded_research")
@patch("backend.app.core.learning_engine.lookup_answer_memory", return_value=None)
@patch("backend.app.core.web_intelligence.gemini_configured", return_value=True)
@patch("app.sanitize_assistant_response", side_effect=lambda t, **_: t)
def test_fetch_open_law_answer_normalizes_grounded_research(
    _sanitize,
    _gemini_cfg,
    _memory,
    mock_grounded,
    mock_web,
):
    mock_grounded.return_value = ChatTurnResult(
        content="Bail lets an accused stay free pending trial.",
        web_sources=[{"title": "CrPC"}],
        follow_ups=["What is anticipatory bail?"],
    )

    result = fetch_open_law_answer(
        "u1",
        "What is bail?",
        "What is bail?",
        [],
        membership="Free",
        thread_id="t1",
        mode="open_law",
    )

    assert isinstance(result, ChatTurnResult)
    assert result.has_content()
    assert len(result.as_tuple()) == 4
    mock_web.assert_not_called()


def test_stream_open_law_turn_empty_stream_uses_executor_fallback():
    """Regression: empty Gemini stream must not crash on tuple unpack during fallback."""
    from backend.app.services.chat_service import _stream_open_law_turn

    events = [{"type": "done", "answer": "", "sources": [], "follow_ups": []}]
    fallback = ChatTurnResult(
        content="Bail is release from custody with conditions.",
        web_sources=[{"title": "Indian Kanoon"}],
        follow_ups=["Explain anticipatory bail"],
    )

    with patch(
        "backend.app.core.web_intelligence.gemini_configured",
        return_value=True,
    ), patch(
        "backend.app.core.web_intelligence.stream_grounded_legal_research",
        return_value=iter(events),
    ), patch(
        "backend.app.services.chat_service.fetch_open_law_answer",
        return_value=fallback,
    ), patch(
        "backend.app.services.chat_service._persist_chat_turn_fast",
        return_value={"chat_id": "c1", "thread_id": "t1"},
    ), patch(
        "backend.app.services.chat_service._record_mode_interaction",
        return_value="i1",
    ), patch(
        "backend.app.services.chat_service._defer_chat_indexing",
    ), patch(
        "backend.app.services.chat_service.get_or_create_session",
        return_value="sess1",
    ), patch(
        "backend.app.services.chat_service.get_session_state",
        return_value={},
    ), patch(
        "backend.app.services.chat_service.append_turn",
    ), patch(
        "backend.app.core.learning_engine.lookup_answer_memory",
        return_value=None,
    ):
        chunks = list(
            _stream_open_law_turn(
                "u1",
                "What is bail in simple language?",
                "open_law",
                thread_id="t1",
            )
        )

    body = "".join(chunks)
    assert "too many values to unpack" not in body
    assert "Web Intelligence Error" not in body
    assert "Bail is release" in body or "data:" in body


def test_run_open_law_turn_returns_chat_turn_result():
    from backend.app.services.chat_service import _run_open_law_turn

    turn = ChatTurnResult(
        content="Thanks — noted for learning.",
        follow_ups=["Summarize key points"],
    )
    with patch(
        "backend.app.services.chat_service._try_conversational_feedback",
        return_value=turn,
    ):
        result = _run_open_law_turn("u1", "good", [{"role": "assistant", "content": "Prior answer"}])

    assert isinstance(result, ChatTurnResult)
    assert result.has_content()
    assert len(result.as_tuple()) == 4
