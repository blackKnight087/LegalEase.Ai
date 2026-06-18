"""Fresh SQLite DB must have documents table before upload."""
from __future__ import annotations

import uuid


def test_fresh_db_upload_after_ensure_app_schemas(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db_path))
    for key in ("DATABASE_URL", "SAAS_USE_POSTGRES_LEGACY", "SAAS_PRODUCTION"):
        monkeypatch.delenv(key, raising=False)

    from backend.app.core.app_db_bridge import uninstall_app_db_bridge

    uninstall_app_db_bridge()

    import app as app_module

    monkeypatch.setattr(app_module, "DB_PATH", db_path)

    from backend.app.core.core_db import ensure_app_schemas

    ensure_app_schemas()

    from legalease_auth import authenticate_user, create_user

    uname = f"u_{uuid.uuid4().hex[:8]}"
    create_user(uname, "pass12345", "Free", "user")
    user = authenticate_user(uname, "pass12345")
    uid = str(user["id"])

    class _F:
        name = "sample.pdf"

        def getbuffer(self):
            return memoryview(b"%PDF-1.4\n")

    fid, _path, pages, dup = app_module.save_uploaded_pdf(_F(), uid)
    rows = app_module.run_query(
        "SELECT id FROM documents WHERE id = ?", (fid,), fetch=True
    )
    assert rows
    assert int(pages or 0) >= 0
