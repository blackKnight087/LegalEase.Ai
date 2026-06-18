"""One-off Firm Chat / user search diagnostics (run inside API container)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/app")

from backend.app.core.core_db import ensure_app_schemas

ensure_app_schemas()

from backend.app.core.collab_service import list_collab_members, search_users_by_username
from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import use_postgres_legacy
from backend.app.core.user_search import iter_user_search_rows, lookup_username_exact


def main() -> None:
    print("postgres_legacy:", use_postgres_legacy())
    conn = connect_data_db()
    try:
        n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        print("user_count:", n)
        rows = conn.execute(
            "SELECT id, username FROM users ORDER BY username LIMIT 20"
        ).fetchall()
        for r in rows:
            print(" user:", r[1], r[0][:8])
        cols = conn.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users'
            ORDER BY ordinal_position
            """
        ).fetchall()
        print("columns:", [c[0] for c in cols])
    finally:
        conn.close()

    if not rows:
        print("NO USERS — register at least 2 accounts to test Firm Chat.")
        return

    uid = str(rows[0][0])
    uname = str(rows[0][1])
    print("--- search as", uname, "---")
    for q in [uname[:3], uname, rows[1][1] if len(rows) > 1 else "zzz"]:
        hits = iter_user_search_rows(uid, q, limit=10)
        print(f"query={q!r} hits={len(hits)}", [h[1] for h in hits])
    if len(rows) > 1:
        other = str(rows[1][1])
        exact = lookup_username_exact(other)
        print("lookup_exact", other, "->", exact)
        sr = search_users_by_username(uid, other, your_username=uname)
        print("search_users_by_username:", sr)

    members = list_collab_members(uid)
    print("collab_members:", len(members), [m.get("username") for m in members[:10]])


if __name__ == "__main__":
    main()
