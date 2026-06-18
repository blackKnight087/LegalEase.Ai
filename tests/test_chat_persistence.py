"""Integration tests for SQLite chat persistence."""
import pytest

from backend.app.core import chat_persistence as cp


@pytest.mark.integration
def test_save_and_load_thread(tmp_chat_db):
    user_id = "test-user-saas"
    saved1 = cp.save_chat_turn(user_id, "What is IPC 307?", "Answer about 307.", thread_id="thread-abc")
    tid = saved1["thread_id"]
    cp.save_chat_turn(
        user_id,
        "Explain simply",
        "Simple explanation.",
        thread_id=tid,
    )
    rows = cp.load_chat_thread(user_id, tid)
    assert len(rows) == 2
    assert rows[0][1] == "What is IPC 307?"
    assert rows[1][1] == "Explain simply"


@pytest.mark.integration
def test_list_threads(tmp_chat_db):
    user_id = "test-user-list"
    cp.save_chat_turn(user_id, "Q1", "A1")
    cp.save_chat_turn(user_id, "Q2", "A2")
    threads = cp.list_chat_threads(user_id, limit=10)
    assert len(threads) >= 2
    assert len(threads[0]) == 7


@pytest.mark.integration
def test_list_threads_matter_id_column(tmp_chat_db):
    user_id = "test-user-matter-col"
    cp.save_chat_turn(user_id, "Q", "A", matter_id="matter-xyz")
    row = cp.list_chat_threads(user_id, limit=5)[0]
    assert len(row) == 7
    assert row[6] == "matter-xyz"


@pytest.mark.integration
def test_thread_id_reuse(tmp_chat_db):
    user_id = "test-user-reuse"
    s1 = cp.save_chat_turn(user_id, "First", "Reply", thread_id="fixed-tid")
    s2 = cp.save_chat_turn(user_id, "Second", "Reply2", thread_id=s1["thread_id"])
    assert s2["thread_id"] == s1["thread_id"]
    rows = cp.load_chat_thread(user_id, s1["thread_id"])
    assert len(rows) == 2
