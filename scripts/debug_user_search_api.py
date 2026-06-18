"""Test collaboration user search API."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "legacy_saas"))

from fastapi.testclient import TestClient

from backend.app.core.auth import get_current_user
from backend.app.main import app

db = ROOT / "legalease.db"
conn = sqlite3.connect(db)
users = {r[1]: r[0] for r in conn.execute("SELECT id, username FROM users").fetchall()}
conn.close()

if "yus" not in users or "saimon" not in users:
    print("Need yus and saimon users in DB, have:", list(users.keys()))
    sys.exit(1)

yus_id = users["yus"]
app.dependency_overrides[get_current_user] = lambda: {
    "id": yus_id,
    "username": "yus",
    "membership": "Pro",
    "role": "user",
}
client = TestClient(app)

for q in ["saimon", "yus", "Sumana", "arp"]:
    r = client.get("/api/v1/collaboration/users/search", params={"q": q})
    data = r.json()
    print(f"q={q!r} -> {r.status_code} users={len(data.get('users', []))} hint={data.get('hint', '')!r}")

app.dependency_overrides.clear()
