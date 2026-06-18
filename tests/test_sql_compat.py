"""PostgreSQL / SQLite compatibility helpers."""
from __future__ import annotations

from backend.app.core import sql_compat


def test_table_columns_uses_information_schema_on_postgres(monkeypatch):
    executed: list[tuple[str, tuple]] = []

    class FakeCursor:
        def fetchall(self):
            return [("id",), ("username",)]

    class FakeConn:
        def execute(self, sql, params=()):
            executed.append((str(sql).strip(), tuple(params)))
            return FakeCursor()

    monkeypatch.setattr(sql_compat, "use_postgres_legacy", lambda: True)

    cols = sql_compat.table_columns(FakeConn(), "users")
    assert cols == ["id", "username"]
    assert "information_schema.columns" in executed[0][0]
    assert "PRAGMA" not in executed[0][0]


def test_insert_or_ignore_routes_to_on_conflict(monkeypatch):
    executed: list[str] = []

    class FakeConn:
        def execute(self, sql, params=()):
            executed.append(str(sql).strip())

    monkeypatch.setattr(sql_compat, "use_postgres_legacy", lambda: True)
    sql_compat.insert_or_ignore(
        FakeConn(),
        "INSERT OR IGNORE INTO t (a) VALUES (?)",
        "INSERT INTO t (a) VALUES (?) ON CONFLICT (a) DO NOTHING",
        ("x",),
    )
    assert "ON CONFLICT" in executed[0]
    assert "INSERT OR IGNORE" not in executed[0]


def test_execute_script_splits_statements_on_postgres(monkeypatch):
    executed: list[str] = []

    class FakeConn:
        def execute(self, sql, params=()):
            executed.append(str(sql).strip())

    monkeypatch.setattr(sql_compat, "use_postgres_legacy", lambda: True)
    sql_compat.execute_script(
        FakeConn(),
        "CREATE TABLE IF NOT EXISTS a (id TEXT); CREATE INDEX IF NOT EXISTS idx_a ON a(id);",
    )
    assert len(executed) == 2
    assert executed[0].startswith("CREATE TABLE")
    assert executed[1].startswith("CREATE INDEX")
