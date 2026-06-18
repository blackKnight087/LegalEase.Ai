"""Lightweight document DB helpers — no Streamlit / app.py imports."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from legalease_auth import run_query

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

_ALLOWED_UPLOAD_EXT = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value or "unknown")


def get_kb_status_id(user_id: Optional[str]) -> str:
    return f"kb_status_{_safe_id(user_id)}" if user_id else "kb_status_1"


def sanitize_filename(filename: str, *, default_ext: str = ".pdf") -> str:
    name = Path(filename or "").name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    ext = Path(name).suffix.lower()
    if ext not in _ALLOWED_UPLOAD_EXT:
        ext = default_ext if default_ext in _ALLOWED_UPLOAD_EXT else ".pdf"
        stem = Path(name).stem[:100].strip(" .") if name else "document"
        name = f"{stem or 'document'}{ext}"
    else:
        stem = Path(name).stem[:100].strip(" .") or "document"
        name = f"{stem}{ext}"
    return name


def get_user_document_count(user_id: str) -> int:
    result = run_query(
        "SELECT COUNT(*) FROM documents WHERE uploader_id = ?",
        (user_id,),
        fetch=True,
    )
    return int(result[0][0]) if result else 0


def _org_matter_ids_subquery() -> str:
    """SQL fragment: matter IDs visible via org membership."""
    return """
        SELECT m.matter_id FROM matters m
        WHERE m.org_id IN (
            SELECT org_id FROM org_members WHERE user_id = ?
        )
    """


def list_visible_documents(user_id: str) -> list:
    """Documents owned by user or linked to org-shared matters."""
    uid = str(user_id)
    rows = run_query(
        f"""
        SELECT id, filename, pages, uploaded_at, COALESCE(matter_id, '')
        FROM documents
        WHERE uploader_id = ?
           OR matter_id IN ({_org_matter_ids_subquery()})
        ORDER BY uploaded_at DESC
        """,
        (uid, uid),
        fetch=True,
    ) or []
    return rows


def get_org_visible_document_count(user_id: str) -> int:
    uid = str(user_id)
    row = run_query(
        f"""
        SELECT COUNT(*) FROM documents
        WHERE uploader_id = ?
           OR matter_id IN ({_org_matter_ids_subquery()})
        """,
        (uid, uid),
        fetch=True,
    )
    return int(row[0][0]) if row else 0


def get_scoped_document_count(user_id: str, matter_id: Optional[str] = None) -> int:
    mid = (matter_id or "").strip()
    if mid:
        row = run_query(
            "SELECT COUNT(*) FROM documents WHERE uploader_id = ? AND matter_id = ?",
            (user_id, mid),
            fetch=True,
        )
    else:
        row = run_query(
            "SELECT COUNT(*) FROM documents WHERE uploader_id = ? AND COALESCE(matter_id, '') = ''",
            (user_id,),
            fetch=True,
        )
    return int(row[0][0]) if row else 0


def get_knowledge_base_status(user_id: Optional[str] = None) -> Dict[str, Any]:
    result = run_query(
        "SELECT status, total_documents, total_chunks, last_updated FROM knowledge_base_status WHERE id = ?",
        (get_kb_status_id(user_id),),
        fetch=True,
    )
    if result:
        return {
            "status": result[0][0],
            "total_documents": result[0][1],
            "total_chunks": result[0][2],
            "last_updated": result[0][3],
        }
    return {
        "status": "empty",
        "total_documents": 0,
        "total_chunks": 0,
        "last_updated": None,
    }
