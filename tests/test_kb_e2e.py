"""
E2E test: upload PDF → index → query → assert answer.

Uses isolated DB + FAISS dirs; mocks PDF extraction with law chart text.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.legacy_kb

LAW_CHART = """
INDIAN OLD VS NEW CRIMINAL LAWS
Indian Penal Code (IPC), 1860 → Bharatiya Nyaya Sanhita (BNS), 2023
Code of Criminal Procedure (CrPC), 1973 → Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023
IPC 302 → BNS 103
Key reforms: Digital evidence admissibility, online FIR registration.
"""


@pytest.fixture
def e2e_env(tmp_path, monkeypatch):
    """Isolated SaaS test environment."""
    db = tmp_path / "e2e.db"
    data = tmp_path / "data"
    faiss = tmp_path / "faiss"
    data.mkdir()
    faiss.mkdir()

    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(faiss))

    import app as legacy_app

    monkeypatch.setattr(legacy_app, "DB_PATH", db)
    monkeypatch.setattr(legacy_app, "DATA_DIR", data)

    from backend.app.core.core_db import ensure_app_schemas

    ensure_app_schemas()

    # Seed test user for FK constraints
    legacy_app.run_query(
        "INSERT OR IGNORE INTO users (id, username, password_hash, membership, role, created_at) VALUES (?,?,?,?,?,?)",
        ("e2e-user-1", "e2e", b"x", "Pro", "user", "2026-01-01T00:00:00+00:00"),
    )

    yield {
        "db": db,
        "data": data,
        "faiss": faiss,
        "user_id": "e2e-user-1",
    }


def _minimal_pdf_bytes() -> bytes:
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
trailer<</Size 4/Root 1 0 R>>
startxref
200
%%EOF"""


@pytest.mark.integration
def test_upload_index_query_e2e(e2e_env, monkeypatch):
    """Full pipeline: save doc → build index → query KB → get BNS answer."""
    uid = e2e_env["user_id"]
    pdf_bytes = _minimal_pdf_bytes()

    class FakeUpload:
        name = "criminal_laws_chart.pdf"

        def getbuffer(self):
            return pdf_bytes

    with patch("app.extract_text_from_file", return_value=LAW_CHART):
        from app import save_uploaded_pdf, build_faiss_index, resolve_rag_index_dir

        file_id, path, pages, was_dup = save_uploaded_pdf(FakeUpload(), uid)
        assert not was_dup
        assert file_id

        ok, msg = build_faiss_index(uid, only_doc_ids=[file_id], incremental=True)
        assert ok, msg

        from rag import count_index_vectors, index_exists

        index_dir = resolve_rag_index_dir(uid)
        assert index_exists(index_dir)
        vectors = count_index_vectors(index_dir)
        assert vectors > 0, f"Expected FAISS vectors, got 0. msg={msg}"

    query = "What is the new law replacing IPC?"
    with patch("kb_pipeline.generate_answer") as mock_gen:
        from kb_response_state import enforce_single_state

        def _answer(q, chunks, profile, history, **kw):
            from kb_legal_query_rewrite import extract_law_mapping_answer

            ans = extract_law_mapping_answer(q, chunks)
            return enforce_single_state(ans or "NOT_FOUND", found=bool(ans))

        mock_gen.side_effect = _answer

        from kb_pipeline import kb_pipeline

        answer, chunks, diag = kb_pipeline(uid, query, index_dir=index_dir)

    assert answer != "NOT_FOUND_IN_KB", diag
    assert "BNS" in answer or "Bharatiya Nyaya" in answer
    assert len(chunks) > 0 or diag.get("found")


@pytest.mark.integration
def test_kb_observability_detects_zero_chunks(e2e_env, monkeypatch):
    from backend.app.core.kb_observability import get_kb_observability

    obs = get_kb_observability(e2e_env["user_id"])
    assert "embeddings_ok" in obs
    assert "faiss_chunks" in obs
    assert "index_scope" in obs
    assert obs["documents"] == 0


@pytest.mark.integration
def test_health_ready_endpoint():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    data = r.json()
    assert "embeddings_ok" in data
    assert "faiss_ok" in data
    assert "ready" in data
