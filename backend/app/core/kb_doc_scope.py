"""
Document-scoped KB retrieval — prevent cross-document contamination.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_CRIMINAL_MARKERS = re.compile(
    r"\b(ipc|bns|bnss|bsa|crpc|indian penal code|bharatiya nyaya|criminal conspiracy|"
    r"unlawful assembly|rioting|murder|anticipatory bail)\b",
    re.I,
)
_CONTRACT_MARKERS = re.compile(
    r"\b(non[- ]?disclosure|nda|disclosing party|receiving party|confidential information|"
    r"breach of contract|indemnity|whereas|hereby agrees)\b",
    re.I,
)
_DEICTIC_DOC_RE = re.compile(
    r"\b(this|the|my|our)\s+(?:uploaded\s+)?(?:pdf|document|file|contract|agreement|nda|case)\b|"
    r"\b(?:just\s+)?uploaded\b|"
    r"\b(?:new|latest)\s+(?:pdf|document|file|upload)\b|"
    r"\bin\s+(?:this|the|my)\s+(?:pdf|document|file)\b",
    re.I,
)


def _most_recent_uploaded_doc(user_id: str) -> Optional[Dict[str, str]]:
    """Latest document row for this user (upload order)."""
    try:
        from legalease_auth import run_query

        row = run_query(
            "SELECT id, filename FROM documents WHERE uploader_id = ? ORDER BY uploaded_at DESC LIMIT 1",
            (str(user_id),),
            fetch=True,
        )
        if row and row[0]:
            return {"doc_id": str(row[0][0] or ""), "filename": str(row[0][1] or "")}
    except Exception:
        pass
    return None


def list_index_documents(index_dir: Any) -> List[Dict[str, str]]:
    """Unique documents in a FAISS index from chunk metadata."""
    try:
        from rag import index_exists, _load_docstore_only

        if not index_exists(index_dir):
            return []
        view = _load_docstore_only(Path(index_dir))
        if view is None:
            return []
        seen: Set[str] = set()
        docs: List[Dict[str, str]] = []
        for doc_id in view.index_to_docstore_id.values():
            try:
                doc = view.docstore.search(doc_id)
            except Exception:
                continue
            meta = getattr(doc, "metadata", None) or {}
            key = str(meta.get("doc_id") or meta.get("filename") or doc_id)
            if key in seen:
                continue
            seen.add(key)
            docs.append(
                {
                    "doc_id": str(meta.get("doc_id") or ""),
                    "filename": str(meta.get("filename") or meta.get("source_file") or ""),
                    "document_type": str(meta.get("document_type") or "unknown"),
                    "file_type": str(meta.get("file_type") or ""),
                }
            )
        return docs
    except Exception as exc:
        logger.debug("list_index_documents failed: %s", exc)
        return []


def resolve_document_scope(
    user_id: str,
    query: str,
    index_dir: Any,
    *,
    doc_id: Optional[str] = None,
    filename: Optional[str] = None,
    thread_id: Optional[str] = None,
    history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Determine active document for retrieval.
    Priority: explicit doc_id/filename → thread attachment → query-inferred type → single doc in index.
    """
    from document_classifier import document_type_for_query, is_contract_family

    scope: Dict[str, Any] = {
        "doc_id": (doc_id or "").strip(),
        "filename": (filename or "").strip(),
        "document_type": "",
        "strict": False,
        "reason": "",
    }

    if scope["doc_id"] or scope["filename"]:
        scope["strict"] = True
        scope["reason"] = "explicit"
        return scope

    if thread_id:
        try:
            from backend.app.core.thread_attachments import load_thread_attachment

            att = load_thread_attachment(str(user_id), str(thread_id))
            if att and att.get("filename"):
                scope["filename"] = str(att["filename"])
                scope["strict"] = True
                scope["reason"] = "thread_attachment"
                from document_classifier import classify_document

                scope["document_type"] = classify_document(
                    att.get("content") or "", scope["filename"]
                )
                return scope
        except Exception:
            pass

    docs = list_index_documents(index_dir)
    try:
        from backend.app.core.kb_doc_scope import (
            is_unlinked_index_dir,
            list_unlinked_only_index_documents,
        )

        if is_unlinked_index_dir(index_dir):
            docs = list_unlinked_only_index_documents(user_id, index_dir)
    except Exception:
        pass
    if not docs:
        return scope

    try:
        from conversation_context import is_meta_follow_up

        if is_meta_follow_up(query):
            scope["reason"] = "meta_follow_up_open_index"
            return scope
    except ImportError:
        pass

    # Multiple uploads: search all unless user pins one file — avoids wrong-doc answers
    if len(docs) >= 2:
        ql = (query or "").lower()
        try:
            from backend.app.core.universal_kb import is_statute_focused_query

            statute_q = is_statute_focused_query(query)
        except Exception:
            statute_q = bool(re.search(r"\b(?:ipc|bns|section)\s*\d", ql))

        if not statute_q and _DEICTIC_DOC_RE.search(query or ""):
            recent = _most_recent_uploaded_doc(user_id)
            if recent and recent.get("doc_id"):
                for d in docs:
                    if str(d.get("doc_id") or "") == recent["doc_id"]:
                        scope.update(
                            {
                                "doc_id": recent["doc_id"],
                                "filename": d.get("filename") or recent.get("filename") or "",
                                "document_type": d.get("document_type") or "",
                                "strict": True,
                                "reason": "recent_upload_deictic",
                            }
                        )
                        # region agent log
                        try:
                            from backend.app.core.debug_session_log import debug_log

                            debug_log(
                                "C",
                                "kb_doc_scope.py:resolve_document_scope",
                                "scoped_recent_upload",
                                {
                                    "doc_id": recent["doc_id"][:12],
                                    "filename": (scope.get("filename") or "")[:60],
                                },
                            )
                        except Exception:
                            pass
                        # endregion
                        return scope

        wanted = document_type_for_query(query)
        if wanted:
            from document_classifier import is_contract_family

            matching = [
                d
                for d in docs
                if (d.get("document_type") or "") == wanted
                or (is_contract_family(wanted) and is_contract_family(d.get("document_type")))
            ]
            if len(matching) > 1:
                scope.update(
                    {
                        "document_type": wanted,
                        "content_family": wanted,
                        "strict": False,
                        "reason": "query_document_type_multi",
                    }
                )
                return scope
            if len(matching) == 1:
                d = matching[0]
                scope.update(
                    {
                        "doc_id": d.get("doc_id") or "",
                        "filename": d.get("filename") or "",
                        "document_type": d.get("document_type") or wanted,
                        "content_family": wanted or "",
                        "strict": True,
                        "reason": "query_document_type_single",
                    }
                )
                return scope
        scope["strict"] = False
        scope["reason"] = "multi_document_open_index"
        if wanted:
            scope["document_type"] = wanted
            scope["content_family"] = wanted
        return scope

    if len(docs) == 1:
        wanted = document_type_for_query(query)
        scope["doc_id"] = docs[0].get("doc_id") or ""
        scope["filename"] = docs[0].get("filename") or ""
        scope["document_type"] = wanted or docs[0].get("document_type") or ""
        scope["content_family"] = wanted or ""
        scope["strict"] = True
        scope["reason"] = "single_document_index"
        try:
            from backend.app.services.legal_orchestrator_v2 import _is_constitutional_text

            if _is_constitutional_text(query):
                doc_type = (docs[0].get("document_type") or "").lower()
                if doc_type in ("ipc", "criminal", "bns", "crpc") or "penal" in doc_type:
                    scope["strict"] = False
                    scope["reason"] = "constitutional_query_open_index"
        except Exception:
            pass
        return scope

    ql = (query or "").lower()
    if re.search(r"\b(this|the)\s+(agreement|document|nda|contract|upload)\b", ql):
        for d in reversed(docs):
            if is_contract_family(d.get("document_type")):
                scope.update(
                    {
                        "doc_id": d.get("doc_id") or "",
                        "filename": d.get("filename") or "",
                        "document_type": d.get("document_type") or "",
                        "strict": True,
                        "reason": "deictic_contract_reference",
                    }
                )
                return scope

    wanted = document_type_for_query(query)
    if wanted:
        from document_classifier import is_contract_family

        matching = [
            d
            for d in docs
            if (d.get("document_type") or "") == wanted
            or (is_contract_family(wanted) and is_contract_family(d.get("document_type")))
        ]
        if len(matching) == 1:
            d = matching[0]
            scope.update(
                {
                    "doc_id": d.get("doc_id") or "",
                    "filename": d.get("filename") or "",
                    "document_type": d.get("document_type") or wanted,
                    "content_family": wanted or "",
                    "strict": True,
                    "reason": "query_document_type_single",
                }
            )
            return scope
        if len(matching) > 1:
            # Multiple uploads of the same family — search all of them, do not pin to the first file.
            scope.update(
                {
                    "document_type": wanted,
                    "content_family": wanted,
                    "strict": False,
                    "reason": "query_document_type_multi",
                }
            )
            return scope

    return scope


def chunk_matches_scope(meta: Dict[str, Any], scope: Dict[str, Any]) -> bool:
    allowed_names = scope.get("allowed_filenames") or []
    allowed_ids = scope.get("allowed_doc_ids") or []
    if allowed_names or allowed_ids:
        fn = str(meta.get("filename") or meta.get("source_file") or "").lower()
        did = str(meta.get("doc_id") or "")
        if allowed_ids and did and did in allowed_ids:
            return True
        if allowed_names and fn:
            allowed_lower = {str(n).lower() for n in allowed_names}
            if fn in allowed_lower or any(a in fn for a in allowed_lower):
                return True
        if allowed_names or allowed_ids:
            return False
    if not scope.get("strict"):
        return True
    target_doc = (scope.get("doc_id") or "").strip()
    target_file = (scope.get("filename") or "").strip().lower()
    if target_doc and str(meta.get("doc_id") or "") == target_doc:
        return True
    if target_file:
        fn = str(meta.get("filename") or meta.get("source_file") or "").lower()
        if fn == target_file or target_file in fn:
            return True
    return not target_doc and not target_file


def filter_chunks_by_scope(
    chunks: List[Dict[str, Any]],
    scope: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not scope.get("strict") or not chunks:
        return chunks
    scoped = [c for c in chunks if chunk_matches_scope(c.get("metadata") or {}, scope)]
    return filter_chunks_by_content_family(scoped or chunks, scope)


def _chunk_matches_content_family(meta: Dict[str, Any], content: str, family: str) -> bool:
    """Match chunk to query-inferred content family (handles mixed PDFs)."""
    if not family:
        return True
    chunk_type = str(meta.get("document_type") or "").lower()
    body = content or ""
    from document_classifier import is_contract_family, is_criminal_law_doc

    if is_contract_family(family):
        if is_contract_family(chunk_type):
            return True
        return bool(_CONTRACT_MARKERS.search(body) and not _CRIMINAL_MARKERS.search(body[:400]))
    if family == "criminal_law" or is_criminal_law_doc(family):
        if chunk_type == "criminal_law":
            return True
        return bool(_CRIMINAL_MARKERS.search(body))
    if family == "court_judgment":
        if chunk_type == "court_judgment":
            return True
        return bool(re.search(r"\b(judgment|judgement|supreme court|petitioner|nirbhaya|kesavananda)\b", body, re.I))
    if family == "constitutional":
        return bool(
            re.search(
                r"\b(Article\s+\d+|Constitutional Rights|Right to Equality|Right to Freedom|"
                r"Right against Exploitation|Right to Freedom of Religion|Right to Constitutional Remedies)\b",
                body,
                re.I,
            )
        )
    return chunk_type == family or not chunk_type or chunk_type == "unknown"


def filter_chunks_by_content_family(
    chunks: List[Dict[str, Any]],
    scope: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Keep chunks aligned with query topic inside a single mixed document."""
    family = (scope.get("content_family") or scope.get("document_type") or "").strip()
    if not family or not scope.get("strict") or not chunks:
        return chunks
    matched = [
        c
        for c in chunks
        if _chunk_matches_content_family(
            c.get("metadata") or {},
            c.get("content") or "",
            family,
        )
    ]
    return matched if matched else chunks


def retrieve_scoped_docstore_chunks(
    query: str,
    index_dir: Any,
    scope: Dict[str, Any],
    *,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Keyword retrieval limited to strict document scope (dense miss fallback)."""
    if not scope.get("strict"):
        return []
    try:
        from rag import _load_docstore_only, _scan_docstore_generic

        view = _load_docstore_only(Path(index_dir))
        if view is None:
            return []
        hits = _scan_docstore_generic(view, query, top_k=max(top_k, 8) * 3)
        return filter_chunks_by_scope(hits, scope)[:top_k]
    except Exception as exc:
        logger.debug("retrieve_scoped_docstore_chunks failed: %s", exc)
        return []


def load_contract_index_text(
    index_dir: Any,
    scope: Optional[Dict[str, Any]] = None,
) -> str:
    """Concatenate contract/NDA chunks from the index (excludes test meta pages)."""
    try:
        from rag import _load_docstore_only
        from document_classifier import is_contract_family
        from kb_content_cleaner import is_index_meta_boilerplate

        view = _load_docstore_only(Path(index_dir))
        if view is None:
            return ""
        parts: List[str] = []
        seen: Set[str] = set()
        scope = scope or {}
        for doc_id in view.index_to_docstore_id.values():
            try:
                doc = view.docstore.search(doc_id)
            except Exception:
                continue
            content = (getattr(doc, "page_content", None) or "").strip()
            if not content or is_index_meta_boilerplate(content):
                continue
            meta = getattr(doc, "metadata", None) or {}
            if scope.get("strict") and not chunk_matches_scope(meta, scope):
                continue
            dt = str(meta.get("document_type") or "").lower()
            if not scope.get("strict"):
                if not is_contract_family(dt) and not re.search(
                    r"\b(?:non[- ]?disclosure|disclosing party|receiving party|"
                    r"confidential information|sample nda)\b",
                    content,
                    re.I,
                ):
                    continue
            elif scope.get("strict") and is_contract_family(scope.get("document_type")):
                if not re.search(
                    r"\b(?:non[- ]?disclosure|disclosing party|receiving party|"
                    r"confidential information|sample nda)\b",
                    content,
                    re.I,
                ):
                    continue
            key = content[:120]
            if key in seen:
                continue
            seen.add(key)
            parts.append(content)
        return "\n\n".join(parts)
    except Exception as exc:
        logger.debug("load_contract_index_text failed: %s", exc)
        return ""


def load_scoped_document_text(index_dir: Any, scope: Dict[str, Any]) -> str:
    """Concatenate all indexed chunk text for the active document."""
    if not scope.get("strict"):
        return ""
    try:
        from rag import _load_docstore_only

        view = _load_docstore_only(Path(index_dir))
        if view is None:
            return ""
        parts: List[str] = []
        seen: Set[str] = set()
        for doc_id in view.index_to_docstore_id.values():
            try:
                doc = view.docstore.search(doc_id)
            except Exception:
                continue
            meta = getattr(doc, "metadata", None) or {}
            if not chunk_matches_scope(meta, scope):
                continue
            content = (getattr(doc, "page_content", None) or "").strip()
            if not content or content in seen:
                continue
            seen.add(content)
            parts.append(content)
        return "\n\n".join(parts)
    except Exception as exc:
        logger.debug("load_scoped_document_text failed: %s", exc)
        return ""


def contamination_penalty(content: str, scope: Dict[str, Any]) -> float:
    """Penalize chunks from wrong document family when scope is active."""
    if not scope.get("strict"):
        return 0.0
    body = content or ""
    doc_type = (scope.get("content_family") or scope.get("document_type") or "").lower()
    if doc_type in {"nda", "contract", "agreement"}:
        if _CRIMINAL_MARKERS.search(body):
            return -1.25
    if doc_type == "criminal_law":
        if _CONTRACT_MARKERS.search(body) and not _CRIMINAL_MARKERS.search(body):
            return -0.85
    if doc_type == "court_judgment":
        if _CRIMINAL_MARKERS.search(body) and not re.search(
            r"\b(judgment|judgement|nirbhaya|kesavananda|supreme court|petitioner)\b",
            body,
            re.I,
        ):
            return -0.65
    return 0.0


def reject_cross_document_contamination(
    query: str,
    chunks: List[Dict[str, Any]],
    scope: Dict[str, Any],
) -> Tuple[bool, str]:
    """Return False if top chunks are from wrong document family."""
    if not chunks or not scope.get("strict"):
        return True, "ok"

    try:
        from backend.app.services.legal_query_parser import is_section_lookup_query
        from kb_query_types import is_section_focus_query
        from document_classifier import is_contract_topic_query

        if is_contract_topic_query(query):
            pass
        elif is_section_lookup_query(query) or is_section_focus_query(query):
            return True, "section_query_overrides_scope"
    except ImportError:
        pass

    from document_classifier import document_type_for_query, is_contract_family

    top = chunks[0]
    body = (top.get("content") or "")[:800]
    meta = top.get("metadata") or {}
    chunk_type = str(meta.get("document_type") or "")

    if is_contract_family(scope.get("document_type")) or is_contract_family(
        document_type_for_query(query)
    ):
        try:
            from document_classifier import is_contract_topic_query

            if is_contract_topic_query(query) and _CONTRACT_MARKERS.search(body):
                return True, "nda_section_in_mixed_doc"
        except ImportError:
            pass
        if _CONTRACT_MARKERS.search(body):
            return True, "ok"
        if _CRIMINAL_MARKERS.search(body) and not _CONTRACT_MARKERS.search(body):
            return False, "criminal_contamination_in_contract_scope"
        if chunk_type == "criminal_law" and not _CONTRACT_MARKERS.search(body):
            return False, "wrong_document_type"

    if scope.get("document_type") == "criminal_law":
        if _CONTRACT_MARKERS.search(body) and not _CRIMINAL_MARKERS.search(body):
            return False, "contract_contamination_in_criminal_scope"

    return True, "ok"


def _global_kb_document_keys(user_id: str) -> Tuple[Set[str], Set[str]]:
    """Return (doc_ids, filenames) for documents in Global KB (not linked to any matter)."""
    doc_ids: Set[str] = set()
    filenames: Set[str] = set()
    try:
        from backend.app.core.database import connect_data_db

        conn = connect_data_db()
        rows = conn.execute(
            """
            SELECT id, filename FROM documents
            WHERE uploader_id = ? AND COALESCE(matter_id, '') = ''
            """,
            (str(user_id),),
        ).fetchall()
        conn.close()
        for row in rows:
            if row[0]:
                doc_ids.add(str(row[0]))
            if row[1]:
                filenames.add(str(row[1]).lower())
    except Exception as exc:
        logger.debug("_global_kb_document_keys failed: %s", exc)
    return doc_ids, filenames


def _linked_document_keys(user_id: str) -> Tuple[Set[str], Set[str]]:
    """Return (doc_ids, filenames) for documents linked to a matter."""
    doc_ids: Set[str] = set()
    filenames: Set[str] = set()
    try:
        from backend.app.core.database import connect_data_db

        conn = connect_data_db()
        rows = conn.execute(
            """
            SELECT id, filename FROM documents
            WHERE uploader_id = ? AND COALESCE(matter_id, '') != ''
            """,
            (str(user_id),),
        ).fetchall()
        conn.close()
        for row in rows:
            if row[0]:
                doc_ids.add(str(row[0]))
            if row[1]:
                filenames.add(str(row[1]).lower())
    except Exception as exc:
        logger.debug("_linked_document_keys failed: %s", exc)
    return doc_ids, filenames


def is_global_kb_index_dir(index_dir: Any) -> bool:
    """True for the dedicated Global KB FAISS index (search all docs in index)."""
    path = str(index_dir or "").replace("\\", "/").lower()
    return "/global_kb" in path or path.endswith("/global_kb")


def is_unlinked_index_dir(index_dir: Any) -> bool:
    """Legacy unlinked-only index — not global_kb (which searches all indexed docs)."""
    if is_global_kb_index_dir(index_dir):
        return False
    path = str(index_dir or "").replace("\\", "/").lower()
    return "_unlinked" in path or path.endswith("/_un")


def list_unlinked_only_index_documents(
    user_id: str,
    index_dir: Any,
) -> List[Dict[str, str]]:
    """Documents in the FAISS index that are not linked to any matter."""
    linked_ids, linked_names = _linked_document_keys(user_id)
    docs = list_index_documents(index_dir)
    if not linked_ids and not linked_names:
        return docs
    out: List[Dict[str, str]] = []
    for d in docs:
        did = str(d.get("doc_id") or "")
        fn = str(d.get("filename") or "").lower()
        if did and did in linked_ids:
            continue
        if fn and fn in linked_names:
            continue
        out.append(d)
    return out


def apply_unlinked_only_scope(
    user_id: str,
    scope: Dict[str, Any],
    index_dir: Any,
) -> Dict[str, Any]:
    """
    Legacy _unlinked index only: restrict retrieval to documents not linked to a matter.
    global_kb index searches all documents indexed in that directory.
    """
    if is_global_kb_index_dir(index_dir):
        return scope
    if not is_unlinked_index_dir(index_dir):
        return scope
    out = dict(scope or {})
    allowed = list_unlinked_only_index_documents(user_id, index_dir)
    allowed_names = [
        str(d.get("filename") or "").strip()
        for d in allowed
        if d.get("filename")
    ]
    allowed_ids = [
        str(d.get("doc_id") or "").strip()
        for d in allowed
        if d.get("doc_id")
    ]
    out["unlinked_only"] = True
    out["allowed_filenames"] = allowed_names
    out["allowed_doc_ids"] = allowed_ids
    if allowed_names:
        pinned = str(out.get("filename") or "").lower()
        if pinned and pinned not in {n.lower() for n in allowed_names}:
            out.pop("filename", None)
            out.pop("doc_id", None)
            out["strict"] = False
            out["pinned_reason"] = "linked_doc_removed_from_kb"
    if len(allowed) == 1:
        d = allowed[0]
        out.setdefault("doc_id", d.get("doc_id") or "")
        out.setdefault("filename", d.get("filename") or "")
        out["strict"] = True
        out["reason"] = out.get("reason") or "unlinked_single_document"
    elif not allowed:
        out["strict"] = True
        out["reason"] = "no_unlinked_documents"
    return out


def filter_chunks_unlinked_only(
    user_id: str,
    chunks: List[Dict[str, Any]],
    *,
    index_dir: Any = None,
) -> List[Dict[str, Any]]:
    if not chunks:
        return chunks
    if index_dir is not None and is_global_kb_index_dir(index_dir):
        return _filter_chunks_global_kb(user_id, chunks)
    if index_dir is not None and not is_unlinked_index_dir(index_dir):
        return chunks
    linked_ids, linked_names = _linked_document_keys(user_id)
    if not linked_ids and not linked_names:
        return chunks
    kept: List[Dict[str, Any]] = []
    for ch in chunks:
        meta = ch.get("metadata") or {}
        did = str(meta.get("doc_id") or "")
        fn = str(meta.get("filename") or meta.get("source_file") or "").lower()
        if did and did in linked_ids:
            continue
        if fn and fn in linked_names:
            continue
        kept.append(ch)
    return kept


def _filter_chunks_global_kb(
    user_id: str,
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Global KB retrieval must never return matter-linked, deleted, or orphaned vectors.
    """
    linked_ids, linked_names = _linked_document_keys(user_id)
    allowed_ids, allowed_names = _global_kb_document_keys(user_id)
    kept: List[Dict[str, Any]] = []
    for ch in chunks:
        meta = ch.get("metadata") or {}
        did = str(meta.get("doc_id") or "")
        fn = str(meta.get("filename") or meta.get("source_file") or "").lower()
        stale_matter = str(meta.get("matter_id") or "").strip()
        if stale_matter:
            continue
        if fn and re.search(
            r"dense_kb_test|dense_legal_testing|kb_test_document|legalease_.*test|"
            r"\d+_page_kb_test|page_kb_test|testing\s+document",
            fn,
            re.I,
        ):
            continue
        try:
            from kb_content_cleaner import is_kb_test_boilerplate

            body_preview = (ch.get("content") or "")[:600]
            if body_preview and is_kb_test_boilerplate(body_preview):
                continue
        except Exception:
            pass
        if did and did in linked_ids:
            continue
        if fn and fn in linked_names:
            continue
        if allowed_ids or allowed_names:
            if did and did not in allowed_ids:
                continue
            if not did and fn and fn not in allowed_names:
                continue
        kept.append(ch)
    return kept

