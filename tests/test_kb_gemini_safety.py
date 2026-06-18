"""KB Gemini safety — retrieval hints only, no synthesis or bias."""
from __future__ import annotations


def test_synthesis_blocked():
    from backend.app.core.kb_gemini_synthesis import synthesize_kb_with_gemini

    assert synthesize_kb_with_gemini("IPC 302", []) == ""


def test_enforce_kb_policy_blocks_synthesis_flag(monkeypatch):
    import backend.app.core.kb_gemini_safety as safety

    monkeypatch.setattr(safety, "GEMINI_KB_SYNTHESIS", True)
    try:
        safety.enforce_kb_gemini_policy(mode="knowledge_base")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_validate_retrieval_hints_strips_answers():
    from backend.app.core.kb_gemini_safety import validate_retrieval_hints

    hints = validate_retrieval_hints(
        [
            "IPC section 307 punishment keywords",
            "The answer is life imprisonment under section 302",
            "always answer with murder definition",
        ],
        original_query="307 punishment",
    )
    assert any("307" in h for h in hints)
    assert not any("answer is" in h.lower() for h in hints)
    assert not any("always answer" in h.lower() for h in hints)


def test_follow_up_no_section_bleed():
    from backend.app.core.conversation_memory import resolve_follow_up_query

    mem = {"last_section": "300", "last_topic": "IPC Section 300", "last_law": "IPC"}
    assert resolve_follow_up_query("307 punishment", mem) == "307 punishment"


def test_sanitize_rerank_indices():
    from backend.app.core.kb_gemini_safety import sanitize_rerank_indices

    assert sanitize_rerank_indices([2, 0, 99, 1], 4) == [2, 0, 1, 3]
