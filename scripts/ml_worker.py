#!/usr/bin/env python3
"""Process ML jobs from Redis queue (improvement pipeline, reindex, neural train)."""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LEGACY = os.path.join(ROOT, "legacy_saas")
for p in (ROOT, LEGACY):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app.core.ml_job_queue import (
    poll_ml_job_sqlite,
    pop_ml_job_id,
    process_ml_job,
)
from backend.app.core.saas_ops_schema import ensure_saas_ops_schema


def main() -> None:
    from backend.app.core.app_db_bridge import install_app_db_bridge
    from backend.app.core.auth_db_bridge import install_auth_db_bridge
    from backend.app.core.core_db import ensure_app_schemas

    print("LegalEase ML worker — REDIS_URL=", os.getenv("REDIS_URL", "(none)"))
    ensure_app_schemas()
    install_auth_db_bridge()
    install_app_db_bridge()
    while True:
        jid = pop_ml_job_id(block_seconds=3)
        if not jid:
            jid = poll_ml_job_sqlite()
        if not jid:
            time.sleep(2)
            continue
        print(f"Processing ML job {jid}")
        out = process_ml_job(jid)
        print(out)


if __name__ == "__main__":
    main()
