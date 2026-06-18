"""Matter intelligence — timeline generation, search, smoke tests."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.matter_repo import get_matter, list_matter_documents
from backend.app.core.matter_workflow import add_timeline_event, list_timeline

logger = logging.getLogger(__name__)


def _intel_log(event: str, **data: Any) -> None:
    logger.info("[MATTER_INTEL] %s %s", event, data)
    try:
        log_path = Path(__file__).resolve().parents[3] / "debug-cf6ca9.log"
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "runId": "matter-intel",
                        "location": "matter_intelligence",
                        "message": event,
                        "data": data,
                        "timestamp": int(__import__("time").time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass


def search_matter(
    user_id: str,
    matter_id: str,
    query: str,
    *,
    k: int = 8,
) -> Dict[str, Any]:
    """Semantic search within matter FAISS + keyword hits on filenames."""
    if not get_matter(user_id, matter_id):
        return {"results": [], "query": query}
    q = (query or "").strip()
    if not q:
        return {"results": [], "query": q}

    _intel_log("matter_ai_query", matter_id=matter_id, query=q[:120])

    semantic: List[Dict[str, Any]] = []
    try:
        from rag import index_exists, query_kb
        from backend.app.core.matter_index import resolve_rag_index_dir

        idx = resolve_rag_index_dir(str(user_id), matter_id, require_matter_scope=True)
        if index_exists(idx):
            for hit in query_kb(q, k=k, index_dir=idx):
                semantic.append(
                    {
                        "type": "semantic",
                        "content": (hit.get("content") or "")[:600],
                        "filename": hit.get("metadata", {}).get("filename", ""),
                        "score": hit.get("score"),
                    }
                )
    except Exception as exc:
        _intel_log("matter_search_error", matter_id=matter_id, error=str(exc))

    keyword: List[Dict[str, Any]] = []
    ql = q.lower()
    for doc in list_matter_documents(user_id, matter_id):
        fn = (doc.get("filename") or "").lower()
        if ql in fn:
            keyword.append(
                {
                    "type": "keyword",
                    "content": f"Document: {doc.get('filename')}",
                    "filename": doc.get("filename"),
                    "document_id": doc.get("document_id"),
                }
            )

    for ev in list_timeline(user_id, matter_id):
        blob = f"{ev.get('title', '')} {ev.get('description', '')}".lower()
        if ql in blob:
            keyword.append(
                {
                    "type": "timeline",
                    "content": f"{ev.get('event_date')}: {ev.get('title')}",
                    "event_id": ev.get("event_id"),
                }
            )

    results = semantic + keyword[: k // 2]
    _intel_log("matter_ai_response", matter_id=matter_id, hits=len(results))
    return {"query": q, "results": results}


def generate_timeline_from_docs(
    user_id: str,
    matter_id: str,
    *,
    auto_insert: bool = False,
) -> Dict[str, Any]:
    """Use matter KB to propose chronology events."""
    if not get_matter(user_id, matter_id):
        return {"events": [], "inserted": 0}
    from backend.app.core.matter_autopilot import load_matter_doc_texts

    chunks = load_matter_doc_texts(user_id, matter_id)
    combined = "\n\n".join(ch.get("content", "") for ch in chunks)
    events: List[Dict[str, str]] = []

    if combined:
        tl_block = re.search(
            r"TIMELINE\s+OF\s+EVENTS?\s*\n(.*?)(?=\n(?:HEARING|WITNESS|EVIDENCE|CASE)|\Z)",
            combined,
            re.I | re.S,
        )
        scan = tl_block.group(1) if tl_block else combined
        for m in re.finditer(
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4}-\d{2}-\d{2})\s*[|\-–]\s*(.+?)(?:\s*[|\-–]\s*(.+))?$",
            scan,
            re.I | re.M,
        ):
            events.append(
                {
                    "event_date": m.group(1)[:20],
                    "title": m.group(2).strip()[:200],
                    "description": (m.group(3) or "").strip()[:500],
                    "event_type": "auto",
                }
            )

    if len(events) < 2:
        prompt = (
            "List the key dated events in chronological order from the matter documents. "
            "Format each line as: YYYY-MM-DD | Event title | brief description"
        )
        try:
            from app import rag_query

            answer, _ = rag_query(str(user_id), prompt, k=8, matter_id=matter_id)
            for line in (answer or "").splitlines():
                m = re.match(
                    r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+\w+\s+\d{4})\s*[|\-–]\s*(.+?)(?:\s*[|\-–]\s*(.+))?$",
                    line.strip(),
                )
                if m:
                    events.append(
                        {
                            "event_date": m.group(1)[:10],
                            "title": m.group(2).strip()[:200],
                            "description": (m.group(3) or "").strip()[:500],
                            "event_type": "auto",
                        }
                    )
        except Exception:
            pass

    inserted = 0
    if auto_insert:
        for ev in events:
            add_timeline_event(
                user_id,
                matter_id,
                title=ev["title"],
                description=ev.get("description", ""),
                event_date=ev.get("event_date", ""),
                event_type="auto",
            )
            inserted += 1

    return {"events": events, "inserted": inserted, "proposed_count": len(events)}


def extract_hearings_from_docs(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Extract court hearings from matter documents and persist to matter_hearings."""
    from backend.app.core.matter_hearings_intel import extract_hearings_from_docs as _extract

    return _extract(user_id, matter_id)


def matter_dashboard_health_snapshot(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Fast dashboard stats only — no LLM/RAG queries (use run_matter_smoke_tests for full checks)."""
    m = get_matter(user_id, matter_id)
    if not m:
        return {"ok": False, "tests": [], "ai_confidence": 0}
    docs = list_matter_documents(user_id, matter_id)
    tests: List[Dict[str, Any]] = [
        {
            "name": "documents_indexed",
            "pass": len(docs) > 0,
            "detail": f"{len(docs)} document(s) linked",
        }
    ]
    vectors = 0
    chunk_count = 0
    try:
        from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
        from backend.app.core.matter_index import get_matter_index_dir
        from backend.app.core.matter_autopilot import sample_matter_chunks

        idx = get_matter_index_dir(str(user_id), matter_id)
        vectors = count_index_vectors(idx) if index_exists(idx) else 0
        chunk_count = len(sample_matter_chunks(str(user_id), matter_id, max_chunks=200))
    except Exception:
        pass
    tests.append(
        {
            "name": "vector_index",
            "pass": vectors > 0 or len(docs) == 0,
            "detail": f"{vectors} vectors",
        }
    )
    tests.append(
        {
            "name": "chunk_count",
            "pass": chunk_count > 0 or len(docs) == 0,
            "detail": f"{chunk_count} chunks sampled",
        }
    )
    confidence = round(100 * sum(1 for t in tests if t["pass"]) / max(len(tests), 1))
    return {
        "ok": tests[0]["pass"] if tests else False,
        "tests": tests,
        "ai_confidence": confidence,
        "vector_count": vectors,
        "chunk_count": chunk_count,
        "snapshot": True,
    }


def run_matter_smoke_tests(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Full KB smoke checks including 5 RAG retrieval queries."""
    _intel_log("matter_smoke_test_run", matter_id=matter_id)
    snap = matter_dashboard_health_snapshot(user_id, matter_id)
    if not get_matter(user_id, matter_id):
        return {"ok": False, "tests": [], "pass": False}

    tests: List[Dict[str, Any]] = list(snap.get("tests") or [])
    vectors = int(snap.get("vector_count") or 0)
    chunks = int(snap.get("chunk_count") or 0)

    queries = (
        ("accused_query", "Who is accused in this case?"),
        ("witness_query", "Who is the witness and what did they say?"),
        ("facts_query", "What happened in this case? Summarize the incident."),
        ("evidence_query", "What evidence exists against the accused?"),
        ("ipc_query", "What IPC sections are involved in this case?"),
    )

    passed_rag = 0
    for test_name, query in queries:
        ok = False
        detail = ""
        sources: List[str] = []
        try:
            from app import rag_query

            ans, chunk_list = rag_query(str(user_id), query, k=5, matter_id=matter_id)
            ok = bool(ans) and len((ans or "").strip()) > 40
            if chunk_list:
                ok = ok and "NOT_FOUND" not in (ans or "").upper()[:80]
                for ch in chunk_list[:3]:
                    fn = ""
                    if isinstance(ch, dict):
                        fn = str(ch.get("metadata", {}).get("filename") or ch.get("filename") or "")
                    sources.append(fn or "chunk")
            detail = (ans or "")[:160]
            if ok:
                passed_rag += 1
        except Exception as exc:
            detail = str(exc)[:160]
        tests.append(
            {
                "name": test_name,
                "pass": ok,
                "detail": detail,
                "sources": sources,
                "query": query,
            }
        )

    from backend.app.core.matter_autopilot import load_matter_doc_texts

    text_chunks = load_matter_doc_texts(user_id, matter_id)
    text_len = sum(len(c.get("content", "")) for c in text_chunks)
    overall_pass = passed_rag >= 3 and (vectors > 0 or text_len >= 80)
    result = {
        "ok": overall_pass,
        "pass": overall_pass,
        "tests": tests,
        "vector_count": vectors,
        "chunk_count": chunks,
        "retrieval_pass_count": passed_rag,
        "ai_confidence": round(100 * sum(1 for t in tests if t.get("pass")) / max(len(tests), 1)),
    }
    _intel_log(
        "matter_smoke_test_complete",
        matter_id=matter_id,
        passed=overall_pass,
        rag_passed=passed_rag,
    )
    return result
