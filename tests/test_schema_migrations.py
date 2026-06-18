"""Schema migration and verify_schema tests."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_legalease.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            membership TEXT NOT NULL DEFAULT 'Free',
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            uploader_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            saved_path TEXT NOT NULL,
            pages INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL
        )"""
        )
        conn.commit()
        conn.close()
        monkeypatch.setenv("LEGALEASE_DB_PATH", str(db_path))
        yield db_path


def test_verify_schema_detects_missing_email(temp_db):
    from backend.app.core.schema_migrations import verify_schema

    report = verify_schema(tables=["users"])
    assert report["ok"] is False
    missing_cols = {m["column"] for m in report["missing"]}
    assert "email" in missing_cols


def test_apply_migrations_adds_email(temp_db):
    from backend.app.core.schema_migrations import apply_migrations, verify_schema

    result = apply_migrations(tables=["users", "documents"])
    assert "users.email" in result["applied"]
    report = verify_schema(tables=["users"])
    assert "email" in report["tables"]["users"]
    assert report["ok"] is True

    conn = sqlite3.connect(temp_db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    conn.close()
    assert "email" in cols
