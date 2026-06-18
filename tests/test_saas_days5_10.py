"""Days 5–10: rest Postgres schema, connect_data_db, ML queue-only path."""
from __future__ import annotations


def test_connect_data_db_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SAAS_USE_POSTGRES_LEGACY", raising=False)
    from backend.app.core.database import connect_data_db
    from backend.app.core.saas_ops_schema import ensure_saas_ops_schema

    ensure_saas_ops_schema()
    conn = connect_data_db()
    conn.execute(
        "INSERT INTO audit_events (id, user_id, action, detail, ip_address, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("a1", "u1", "test.action", "", "", "2026-01-01T00:00:00Z"),
    )
    conn.commit()
    row = conn.execute("SELECT action FROM audit_events WHERE id = ?", ("a1",)).fetchone()
    conn.close()
    assert row[0] == "test.action"


def test_improvement_enqueue_only_when_queue(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("ML_USE_QUEUE", "1")

    from unittest.mock import patch

    from backend.app.core import improvement_automation as ia

    with patch("backend.app.core.ml_job_queue.enqueue_ml_job", return_value={"ok": True, "job_id": "j1"}):
        with patch("backend.app.core.ml_job_queue.user_has_active_ml_job", return_value=False):
            with patch("backend.app.core.ml_job_queue.should_use_ml_queue", return_value=True):
                with patch.object(ia.threading, "Thread") as mock_thread:
                    ia.schedule_improvement_pipeline("user-x", trigger="test")
                    mock_thread.assert_not_called()


def test_sql_compat_table_exists_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from backend.app.core.database import connect_data_db
    from backend.app.core.sql_compat import table_exists
    from backend.app.core.saas_ops_schema import ensure_saas_ops_schema

    ensure_saas_ops_schema()
    conn = connect_data_db()
    assert table_exists(conn, "audit_events")
    conn.close()


def test_email_verify_token_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "ev.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from backend.app.core.email_verify_service import create_verify_token, verify_email_token

    out = create_verify_token("u1", "user@example.com")
    assert out.get("token")
    ok = verify_email_token(str(out["token"]))
    assert ok.get("ok") is True


def test_pg_rest_ddl_has_ml_jobs():
    from backend.app.core.pg_rest_schema import PG_REST_DDL

    joined = " ".join(PG_REST_DDL)
    assert "ml_jobs" in joined
    assert "crm_leads" in joined
    assert "documents" in joined
