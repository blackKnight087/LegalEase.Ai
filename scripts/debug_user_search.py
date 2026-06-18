"""Debug Firm Chat user search."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "legacy_saas"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from backend.app.core.user_search import iter_user_search_rows
from legalease_auth import get_db_path

db = ROOT / "legalease.db"
conn = sqlite3.connect(db)
users = conn.execute("SELECT id, username FROM users").fetchall()
conn.close()

print("DB path:", get_db_path())
print("Users:", len(users))
for uid, uname in users[:5]:
    print(f"  {uname} -> {uid[:12]}...")

if len(users) >= 2:
    a_id, a_name = users[0]
    b_id, b_name = users[1]
    q = b_name[:3] if len(b_name) >= 3 else b_name
    rows = iter_user_search_rows(a_id, q)
    print(f"\n{a_name} searches '{q}' -> {len(rows)} hits")
    for r in rows:
        print(" ", r)
