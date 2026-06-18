"""User search for Firm Chat."""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from backend.app.core.user_search import (
    iter_user_search_rows,
    lookup_username_exact,
    normalize_user_search_query,
)
from legalease_auth import create_user, ensure_db, get_db_path


@pytest.fixture
def search_db(tmp_path, monkeypatch):
    db = tmp_path / "search_test.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    ensure_db()
    uid_a = str(uuid.uuid4())
    uid_b = str(uuid.uuid4())
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO users (id, username, password_hash, membership, role, created_at) VALUES (?,?,?,?,?,?)",
        (uid_a, "alice_law", b"x", "Free", "user", "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, membership, role, created_at, email) VALUES (?,?,?,?,?,?,?)",
        (uid_b, "bob@firm.com", b"x", "Free", "user", "2026-01-01", "bob@firm.com"),
    )
    conn.commit()
    conn.close()
    return uid_a, uid_b


def test_normalize_strips_at():
    assert normalize_user_search_query("@alice") == "alice"


def test_search_by_username_prefix(search_db):
    uid_a, uid_b = search_db
    # Search excludes the current user — search as B for A's username
    rows = iter_user_search_rows(uid_b, "ali")
    assert len(rows) == 1
    assert rows[0][1] == "alice_law"


def test_search_by_email(search_db):
    uid_a, uid_b = search_db
    rows = iter_user_search_rows(uid_a, "bob@firm")
    assert len(rows) == 1
    assert "bob" in rows[0][1]


def test_search_minimal_users_schema(tmp_path, monkeypatch):
    """Postgres production schema often lacks email/display_name on users."""
    db = tmp_path / "minimal_users.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            membership TEXT NOT NULL DEFAULT 'Free',
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        )
        """
    )
    uid_a = str(uuid.uuid4())
    uid_b = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users VALUES (?,?,?,?,?,?)",
        (uid_a, "priya_advocate", b"x", "Free", "user", "2026-01-01"),
    )
    conn.execute(
        "INSERT INTO users VALUES (?,?,?,?,?,?)",
        (uid_b, "rahul_counsel", b"x", "Pro", "user", "2026-01-01"),
    )
    conn.commit()
    conn.close()

    rows = iter_user_search_rows(uid_b, "priya")
    assert len(rows) == 1
    assert rows[0][1] == "priya_advocate"

    hit = lookup_username_exact("rahul_counsel")
    assert hit and hit["username"] == "rahul_counsel"
