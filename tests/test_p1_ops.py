"""P1 ops: admin, audit, ML jobs."""
from __future__ import annotations


def test_audit_log(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "audit.db"))
    from legalease_auth import ensure_db
    from backend.app.core.audit_service import list_audit_events, log_audit
    from backend.app.core.saas_ops_schema import ensure_saas_ops_schema

    ensure_db()
    ensure_saas_ops_schema()
    log_audit("test_action", user_id="u1", detail="hello")
    events = list_audit_events(limit=5, action_prefix="test")
    assert len(events) == 1
    assert events[0]["action"] == "test_action"


def test_ml_job_enqueue_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "ml.db"))
    monkeypatch.delenv("REDIS_URL", raising=False)
    from legalease_auth import ensure_db
    from backend.app.core.ml_job_queue import enqueue_ml_job, get_ml_job
    from backend.app.core.saas_ops_schema import ensure_saas_ops_schema

    ensure_db()
    ensure_saas_ops_schema()
    out = enqueue_ml_job("user-1", "improvement_pipeline", {"trigger": "test"})
    assert out["job_id"]
    job = get_ml_job(out["job_id"])
    assert job
    assert job["status"] == "QUEUED"


def test_admin_list_users(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "adm.db"))
    from backend.app.core.admin_service import list_users, set_user_suspended
    from backend.app.core.saas_ops_schema import ensure_saas_ops_schema
    from legalease_auth import create_user, ensure_db

    ensure_db()
    ensure_saas_ops_schema()
    create_user("adm_test", "pass12345")
    users = list_users()
    assert any(u["username"] == "adm_test" for u in users)
    uid = next(u["id"] for u in users if u["username"] == "adm_test")
    assert set_user_suspended(uid, True)
    users2 = list_users()
    row = next(u for u in users2 if u["id"] == uid)
    assert row["suspended"] is True


def test_superadmin_check():
    from backend.app.core.admin_auth import is_superadmin

    assert is_superadmin({"username": "admin", "role": "user"})
    assert is_superadmin({"username": "x", "role": "admin"})
    assert not is_superadmin({"username": "bob", "role": "user"})
