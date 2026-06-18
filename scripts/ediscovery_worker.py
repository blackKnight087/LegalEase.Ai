#!/usr/bin/env python3
"""Process e-discovery jobs from Redis queue (or poll SQLite when Redis absent)."""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LEGACY = os.path.join(ROOT, "legacy_saas")
for p in (ROOT, LEGACY):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app.core.database import connect_data_db
from backend.app.core.job_queue import pop_job_id, process_job


def poll_sqlite_once() -> bool:
    from backend.app.core.core_db import ensure_app_schemas

    ensure_app_schemas()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT job_id FROM ediscovery_jobs WHERE status='QUEUED' ORDER BY created_at LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return False
    process_job(row[0])
    return True


def main() -> None:
    from backend.app.core.app_db_bridge import install_app_db_bridge
    from backend.app.core.auth_db_bridge import install_auth_db_bridge
    from backend.app.core.core_db import ensure_app_schemas

    print("LegalEase e-discovery worker — REDIS_URL=", os.getenv("REDIS_URL", "(none)"))
    ensure_app_schemas()
    install_auth_db_bridge()
    install_app_db_bridge()
    while True:
        jid = pop_job_id(block_seconds=3)
        if jid:
            print(f"Processing job {jid}")
            out = process_job(jid)
            print(out)
            continue
        if poll_sqlite_once():
            continue
        time.sleep(2)


if __name__ == "__main__":
    main()
