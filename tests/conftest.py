"""Shared pytest fixtures for LegalEase SaaS test suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy_saas"
for p in (str(ROOT), str(LEGACY)):
    if p not in sys.path:
        sys.path.insert(0, p)


SAMPLE_IPC_DOCUMENT = """
IPC Section 299 — Culpable Homicide
Whoever causes death with intention or knowledge shall be guilty of culpable homicide.

IPC Section 300 — Murder
Murder is aggravated culpable homicide with defined circumstances.

IPC Section 302 — Punishment for Murder
Whoever commits murder shall be punished with death or imprisonment for life.

IPC Section 304A — Causing Death by Negligence
Death caused by negligent act without intention.

IPC Section 307 — Attempt to Murder
Whoever does any act with intent to cause death shall be guilty of attempt to murder.

IT Act Section 66C — Identity Theft
Dishonest use of electronic signature or password.

IT Act Section 66D — Cheating by Personation
Cheating by personation using computer resource.
"""


@pytest.fixture
def sample_legal_chunks():
    """Chunks mirroring a typical IPC + IT Act study document."""
    parts = [
        ("299", "IPC", "Culpable Homicide"),
        ("300", "IPC", "Murder"),
        ("302", "IPC", "Punishment for Murder"),
        ("304a", "IPC", "Causing Death by Negligence"),
        ("307", "IPC", "Attempt to Murder"),
        ("66C", "IT Act", "Identity Theft"),
        ("66D", "IT Act", "Cheating by Personation"),
    ]
    chunks = []
    for i, (sec, law, title) in enumerate(parts):
        if law == "IT Act":
            body = f"IT Act Section {sec} — {title}. Offence under cyber law."
        else:
            body = f"IPC Section {sec} — {title}. Punishment may include imprisonment."
        chunks.append(
            {
                "content": body,
                "metadata": {"filename": "legal_notes.pdf", "chunk_index": str(i)},
                "final_score": 0.7,
                "hybrid_score": 0.7,
                "source": "document_scan",
            }
        )
    return chunks


@pytest.fixture
def comparison_chunks_300_307():
    return [
        {
            "content": "IPC Section 300 — Murder. Death actually caused with intent.",
            "metadata": {"filename": "doc.pdf", "chunk_index": "0"},
            "final_score": 0.8,
            "entity": "300",
        },
        {
            "content": "IPC Section 307 — Attempt to Murder. Attempt without successful death.",
            "metadata": {"filename": "doc.pdf", "chunk_index": "1"},
            "final_score": 0.75,
            "entity": "307",
        },
    ]


@pytest.fixture
def follow_up_messages():
    return [
        {"role": "user", "content": "What is IPC 307?"},
        {
            "role": "assistant",
            "content": "IPC Section 307 deals with attempt to murder under your document.",
        },
    ]


@pytest.fixture
def tmp_chat_db(monkeypatch, tmp_path):
    """Isolate chat persistence to a temp SQLite file."""
    db_file = tmp_path / "test_legalease.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db_file))
    import backend.app.core.chat_persistence as cp

    monkeypatch.setattr(cp, "DB_PATH", db_file)
    cp.ensure_chat_schema()
    return db_file


@pytest.fixture(autouse=True)
def _reset_app_db_bridge_after_test():
    """Postgres legacy tests patch app.run_query; reset after each test."""
    yield
    from backend.app.core.app_db_bridge import uninstall_app_db_bridge

    uninstall_app_db_bridge()


@pytest.fixture(autouse=True)
def _learning_scope_promotion_enabled_in_tests(monkeypatch):
    """`.env` may disable promotion; API tests expect the endpoint when role=admin."""
    try:
        from backend.app.api.v1.endpoints import learning as learning_mod

        monkeypatch.setattr(learning_mod, "SCOPE_PROMOTION_ENABLED", True)
    except ImportError:
        pass
