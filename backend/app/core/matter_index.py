"""Per-matter FAISS index paths — isolate RAG retrieval by case file."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import os

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def faiss_base_dir() -> Path:
    path = Path(os.getenv("FAISS_BASE_DIR", str(_PROJECT_ROOT / "faiss_indexes")))
    path.mkdir(parents=True, exist_ok=True)
    return path

UNLINKED_SUBDIR = "_unlinked"
GLOBAL_KB_SUBDIR = "global_kb"
LEGACY_INDEX_NAME = "index"


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value or "unknown")


def get_user_index_dir(user_id: str) -> Path:
    path = faiss_base_dir() / f"user_{safe_id(user_id)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_matter_index_dir(user_id: str, matter_id: str) -> Path:
    path = get_user_index_dir(user_id) / f"matter_{safe_id(matter_id)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_unlinked_index_dir(user_id: str) -> Path:
    """Legacy alias — prefer get_global_kb_index_dir for new code."""
    return get_global_kb_index_dir(user_id)


def get_global_kb_index_dir(user_id: str) -> Path:
    """
    Global legal knowledge index (statutes, constitution, case law, templates).
    Reads legacy ``_unlinked`` when ``global_kb`` is not yet populated.
    """
    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists

    user_base = get_user_index_dir(user_id)
    global_dir = user_base / GLOBAL_KB_SUBDIR
    legacy_dir = user_base / UNLINKED_SUBDIR

    for candidate in (global_dir, legacy_dir):
        if index_exists(candidate) and count_index_vectors(candidate) > 0:
            return candidate
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir


def get_global_kb_write_dir(user_id: str) -> Path:
    """Target directory for new global KB index builds (always ``global_kb``)."""
    path = get_user_index_dir(user_id) / GLOBAL_KB_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_exists_at(path: Path) -> bool:
    from backend.app.core.faiss_index_stats import index_exists

    return index_exists(path)


def resolve_rag_index_dir(
    user_id: str,
    matter_id: Optional[str] = None,
    *,
    require_matter_scope: bool = False,
    retrieval_scope: str = "auto",
) -> Path:
    """
    Pick the FAISS directory for retrieval.

    retrieval_scope:
      - ``global`` → global_kb only (Knowledge Base mode)
      - ``matter`` → matter:{id} only (Matter AI)
      - ``auto`` → matter if require_matter_scope/matter_id+strict, else global_kb
    """
    from backend.app.core.faiss_index_stats import count_index_vectors

    scope = (retrieval_scope or "auto").strip().lower()
    mid = (matter_id or "").strip()

    if scope == "global":
        return get_global_kb_index_dir(user_id)

    if scope == "matter":
        if require_matter_scope and not mid:
            raise ValueError("matter_id required for matter retrieval scope")
        if mid:
            from backend.app.core.matter_repo import get_matter

            if get_matter(user_id, mid):
                return get_matter_index_dir(user_id, mid)
            if require_matter_scope:
                raise ValueError("Matter not found or access denied")
        if require_matter_scope:
            raise ValueError("matter_id required for scoped retrieval")
        return get_global_kb_index_dir(user_id)

    # auto (legacy callers)
    if require_matter_scope and not mid:
        raise ValueError("matter_id required for scoped retrieval")

    if mid:
        from backend.app.core.matter_repo import get_matter

        if not get_matter(user_id, mid):
            if require_matter_scope:
                raise ValueError("Matter not found or access denied")
        else:
            return get_matter_index_dir(user_id, mid)

    if require_matter_scope:
        raise ValueError("matter_id required for scoped retrieval")

    return get_global_kb_index_dir(user_id)


def list_matters_with_documents(user_id: str) -> List[str]:
    from backend.app.core.database import connect_data_db

    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT DISTINCT matter_id FROM documents
        WHERE uploader_id = ? AND COALESCE(matter_id, '') != ''
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]
