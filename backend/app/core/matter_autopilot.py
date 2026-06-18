"""Matter autopilot — extract entities and suggest research queries from uploaded docs."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import list_matter_documents


def sample_matter_chunks(
    user_id: str, matter_id: str, *, max_chunks: int = 40, max_chars: int = 24000
) -> List[Dict[str, str]]:
    """Return indexed chunks with filename for matter-scoped extraction."""
    chunks: List[Dict[str, str]] = []
    try:
        from app import resolve_rag_index_dir
        from rag import load_faiss_index

        index_dir = resolve_rag_index_dir(user_id, matter_id)
        store = load_faiss_index(index_dir)
        if not store:
            return []
        docs = getattr(store, "docstore", None)
        if not docs:
            return []
        total = 0
        for _id, doc in list(getattr(docs, "_dict", {}).items())[:max_chunks]:
            meta = getattr(doc, "metadata", {}) or {}
            content = (getattr(doc, "page_content", "") or "").strip()
            if not content:
                continue
            chunks.append(
                {
                    "content": content[:4000],
                    "filename": str(meta.get("filename") or meta.get("source") or "document"),
                    "document_id": str(meta.get("document_id") or meta.get("doc_id") or ""),
                    "page": str(meta.get("page") or meta.get("page_number") or ""),
                }
            )
            total += len(content)
            if total >= max_chars:
                break
    except Exception:
        return []
    return chunks


def _sample_matter_text(user_id: str, matter_id: str, max_chars: int = 12000) -> str:
    try:
        from app import resolve_rag_index_dir
        from rag import load_faiss_index

        index_dir = resolve_rag_index_dir(user_id, matter_id)
        store = load_faiss_index(index_dir)
        if not store:
            return ""
        docs = getattr(store, "docstore", None)
        if not docs:
            return ""
        parts: List[str] = []
        for _id, doc in list(getattr(docs, "_dict", {}).items())[:40]:
            parts.append(getattr(doc, "page_content", "") or "")
            if sum(len(p) for p in parts) > max_chars:
                break
        return "\n".join(parts)[:max_chars]
    except Exception:
        return ""


def load_matter_doc_texts(
    user_id: str, matter_id: str, *, max_chunks: int = 60, max_chars: int = 80000
) -> List[Dict[str, str]]:
    """FAISS chunks when indexed; otherwise PDF extraction cache / file text."""
    chunks = sample_matter_chunks(str(user_id), matter_id, max_chunks=max_chunks, max_chars=max_chars)
    if chunks:
        return chunks

    docs = list_matter_documents(user_id, matter_id)
    if not docs:
        return []

    conn = connect_data_db()
    out: List[Dict[str, str]] = []
    data_dir = Path(__file__).resolve().parents[3] / "Data"
    for doc in docs:
        doc_id = str(doc.get("document_id") or "")
        row = conn.execute(
            "SELECT saved_path, filename FROM documents WHERE id = ? AND uploader_id = ?",
            (doc_id, str(user_id)),
        ).fetchone()
        if not row:
            continue
        path = Path(row[0] or "")
        filename = str(row[1] or path.name)
        text = ""
        if path.exists():
            for tag in ("auto", "native", "ocr"):
                cache = path.parent / f"{path.stem}.{tag}.extracted.txt"
                if cache.exists():
                    try:
                        text = cache.read_text(encoding="utf-8", errors="replace")
                        if len(text.strip()) > 80:
                            break
                    except OSError:
                        pass
            if len(text.strip()) < 80:
                try:
                    from app import extract_text_from_file

                    text = extract_text_from_file(path)
                except Exception:
                    text = ""
        if len(text.strip()) < 80 and path.name:
            for cache in data_dir.glob(f"*{path.stem}*.extracted.txt"):
                try:
                    text = cache.read_text(encoding="utf-8", errors="replace")
                    break
                except OSError:
                    pass
        if text.strip():
            out.append(
                {
                    "content": text[:max_chars],
                    "filename": filename,
                    "document_id": doc_id,
                    "page": "",
                }
            )
    conn.close()
    return out


def analyze_matter(user_id: str, matter_id: str) -> Dict[str, Any]:
    text = _sample_matter_text(user_id, matter_id)
    if not text or len(text) < 100:
        return {
            "ok": False,
            "message": "Not enough indexed text in this matter.",
            "parties": [],
            "sections": [],
            "suggested_queries": [],
        }

    parties: List[str] = []
    for pat in (
        r"(?:petitioner|plaintiff|appellant|respondent|accused|defendant)\s*[:\-]?\s*([A-Z][A-Za-z\s\.]{2,50})",
        r"(?:State of|Union of India|v\.|vs\.)\s*([A-Z][A-Za-z\s\.]{2,40})",
    ):
        for m in re.finditer(pat, text, re.I):
            val = m.group(1).strip()
            if 3 < len(val) < 60 and val not in parties:
                parties.append(val)

    sections = sorted(set(re.findall(r"\b(?:Section|IPC|BNS|BNSS|CrPC)\s*(\d{1,4}[a-z]?)\b", text, re.I)))[:12]

    queries: List[str] = []
    if sections:
        queries.append(f"Full jurisprudence analysis of Section {sections[0]} applicable to this matter")
        if len(sections) > 1:
            queries.append(f"Compare Section {sections[0]} and Section {sections[1]} in context of this case")
    if parties:
        queries.append(f"Legal strategy and precedents for {parties[0][:40]}")
    queries.append("Identify contradictions across uploaded documents in this matter")
    queries.append("Prepare oral argument questions bench may ask for this matter")

    return {
        "ok": True,
        "parties": parties[:8],
        "sections": sections,
        "suggested_queries": queries[:6],
        "text_sample_chars": len(text),
    }
