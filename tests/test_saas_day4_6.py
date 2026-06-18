"""Day 4–6: Postgres legacy flag, ML queue helpers."""
from __future__ import annotations

import uuid


def test_should_use_ml_queue_redis(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.delenv("ML_USE_QUEUE", raising=False)
    from backend.app.core.ml_job_queue import should_use_ml_queue

    assert should_use_ml_queue() is True


def test_use_postgres_legacy_production_auto(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("SAAS_PRODUCTION", "1")
    monkeypatch.setenv("SAAS_AUTO_POSTGRES_LEGACY", "1")
    monkeypatch.delenv("SAAS_USE_POSTGRES_LEGACY", raising=False)
    from backend.app.core.legacy_db import use_postgres_legacy

    assert use_postgres_legacy() is True


def test_enqueue_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "ml.db"))
    monkeypatch.delenv("REDIS_URL", raising=False)
    from backend.app.core.saas_ops_schema import ensure_saas_ops_schema
    from backend.app.core.ml_job_queue import enqueue_ml_job

    ensure_saas_ops_schema()
    a = enqueue_ml_job("u1", "kb_reindex", {})
    assert a.get("ok") is True
    b = enqueue_ml_job("u1", "kb_reindex", {})
    assert b.get("deduped") is True


def test_chat_visible_across_connections(tmp_path, monkeypatch):
    """Day 4: two DB connections see the same saved thread (SQLite path)."""
    db = tmp_path / "chat_shared.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SAAS_USE_POSTGRES_LEGACY", raising=False)

    from backend.app.core.chat_persistence import load_chat_thread, save_chat_turn

    uid = "user-shared-test"
    tid = str(uuid.uuid4())
    save_chat_turn(
        uid,
        "Question A",
        "Answer A",
        thread_id=tid,
        mode="knowledge_base",
    )
    rows = load_chat_thread(uid, tid)
    assert len(rows) == 1
    assert rows[0][1] == "Question A"

    from backend.app.core.core_db import core_db_backend

    assert core_db_backend() == "sqlite"


def test_legacy_cursor_adapts_placeholders(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    from backend.app.core.legacy_db import LegacyCursorWrapper

    class _FakeCur:
        last_sql = ""
        last_params = ()

        def execute(self, sql, params):
            self.last_sql = sql
            self.last_params = params

        def fetchall(self):
            return []

    cur = LegacyCursorWrapper(_FakeCur())
    cur.execute("SELECT * FROM chat_history WHERE user_id = ?", ("u1",))
    assert "%s" in cur._cur.last_sql
    assert "?" not in cur._cur.last_sql
    assert cur._cur.last_params == ("u1",)


def test_core_db_backend_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("SAAS_USE_POSTGRES_LEGACY", "1")
    from backend.app.core.core_db import core_db_backend

    assert core_db_backend() == "postgresql"
