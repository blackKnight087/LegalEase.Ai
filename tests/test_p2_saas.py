"""P2 SaaS: email, GDPR, onboarding, password reset."""
from __future__ import annotations

import io
import zipfile

import pytest


def test_password_reset_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "p2.db"))
    from backend.app.core.p2_saas_schema import ensure_p2_saas_schema
    from backend.app.core.password_reset_service import (
        request_password_reset,
        reset_password_with_token,
    )
    from legalease_auth import authenticate_user, create_user, ensure_db

    ensure_db()
    ensure_p2_saas_schema()
    assert create_user("reset_user", "oldpass12")
    request_password_reset("reset_user")
    conn_path = tmp_path / "p2.db"
    import sqlite3

    conn = sqlite3.connect(conn_path)
    row = conn.execute(
        "SELECT token_hash FROM password_reset_tokens LIMIT 1"
    ).fetchone()
    conn.close()
    assert row
    raw = "test-token-for-unit-test-only-32chars!!"
    from backend.app.core.password_reset_service import _hash_token

    th = _hash_token(raw)
    conn = sqlite3.connect(conn_path)
    conn.execute("UPDATE password_reset_tokens SET token_hash = ?", (th,))
    conn.commit()
    conn.close()
    reset_password_with_token(raw, "newpass99")
    assert authenticate_user("reset_user", "newpass99")
    assert not authenticate_user("reset_user", "oldpass12")


def test_onboarding_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "onb.db"))
    from backend.app.core.onboarding_service import dismiss_onboarding, get_onboarding_state
    from backend.app.core.p2_saas_schema import ensure_p2_saas_schema
    from legalease_auth import create_user, ensure_db

    ensure_db()
    ensure_p2_saas_schema()
    create_user("onb_user", "pass12345")
    from legalease_auth import authenticate_user

    user = authenticate_user("onb_user", "pass12345")
    assert user
    st = get_onboarding_state(user["id"], "Free")
    assert st["total"] >= 5
    assert st["steps"][0]["done"] is True
    dismiss_onboarding(user["id"])
    st2 = get_onboarding_state(user["id"])
    assert st2["dismissed"] is True


def test_account_export_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "gdpr.db"))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss"))
    from backend.app.core.account_service import delete_user_account, export_user_data_zip
    from backend.app.core.p2_saas_schema import ensure_p2_saas_schema
    from legalease_auth import create_user, ensure_db, get_user_by_id

    ensure_db()
    ensure_p2_saas_schema()
    create_user("gdpr_user", "pass12345")
    from legalease_auth import authenticate_user

    user = authenticate_user("gdpr_user", "pass12345")
    assert user
    blob = export_user_data_zip(user["id"], user["username"])
    zf = zipfile.ZipFile(io.BytesIO(blob))
    assert "manifest.json" in zf.namelist()
    delete_user_account(user["id"])
    assert get_user_by_id(user["id"]) is None


def test_email_console_provider():
    from backend.app.core.email_service import send_email

    assert send_email("dev@test.com", "Test", "<p>hi</p>") is True
