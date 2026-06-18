"""
Optional reference queries for LegalEase_Dense_KB_Test_Document.pdf only.

NOT used for live chat — only by scripts/run_dense_kb_validation.py when you explicitly
validate that benchmark PDF. Production smoke tests use kb_smoke_query_builder.py (universal).
"""
from __future__ import annotations

from typing import Any, Dict, List

DENSE_KB_FILENAME_HINTS = (
    "dense_kb_test",
    "dense legal testing",
    "legalease_dense",
)

# Ground-truth queries — each should return FOUND after full re-index of the dense PDF
DENSE_KB_SMOKE_QUERIES: List[Dict[str, str]] = [
    {"id": "ipc_307", "query": "Explain IPC 307"},
    {"id": "ipc_302_punish", "query": "Punishment under IPC 302"},
    {"id": "ipc_299_300", "query": "Difference between IPC 299 and IPC 300"},
    {"id": "ipc_406", "query": "IPC Section 406"},
    {"id": "section_300", "query": "section 300"},
    {"id": "constitutional_rights", "query": "What are the fundamental constitutional rights in the document?"},
    {"id": "equality", "query": "Right to Equality"},
    {"id": "article_14", "query": "Article 14"},
    {"id": "nda_confidential", "query": "What do the sample NDA clauses say about confidential information?"},
    {"id": "nirbhaya", "query": "Explain the Nirbhaya case mentioned in the document"},
]

# Note: this test doc lists Article 14 (equality), not Article 21 — use Article 14 for validation
DENSE_KB_OPTIONAL_QUERIES: List[Dict[str, str]] = [
    {"id": "compare_302_307", "query": "Compare IPC 302 and IPC 307"},
    {"id": "ipc_420", "query": "What is IPC Section 420 about?"},
    {"id": "kesavananda", "query": "Kesavananda Bharati case basic structure"},
]


def is_dense_kb_test_filename(filename: str) -> bool:
    name = (filename or "").lower().replace(" ", "_")
    return any(h in name for h in DENSE_KB_FILENAME_HINTS)


def index_contains_dense_test_doc(index_dir: Any) -> bool:
    try:
        from backend.app.core.kb_doc_scope import list_index_documents

        for doc in list_index_documents(index_dir):
            if is_dense_kb_test_filename(doc.get("filename", "")):
                return True
    except Exception:
        pass
    return False


def smoke_queries_for_index(index_dir: Any) -> List[Dict[str, str]]:
    """Deprecated — use kb_smoke_query_builder.build_smoke_queries_from_index instead."""
    if index_contains_dense_test_doc(index_dir):
        return list(DENSE_KB_SMOKE_QUERIES)
    return []
