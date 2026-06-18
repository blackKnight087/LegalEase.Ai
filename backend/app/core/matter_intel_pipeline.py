"""
Matter intelligence pipeline — runs real extraction from indexed matter documents.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import get_matter, list_matter_documents
from backend.app.core.practice_schema import ensure_practice_schema

logger = logging.getLogger(__name__)

_STAGES = (
    "idle",
    "starting",
    "entities",
    "evidence",
    "timeline",
    "hearings",
    "contradictions",
    "ready",
    "failed",
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _intel_log(event: str, **data: Any) -> None:
    logger.info("[MATTER_INTEL] %s %s", event, data)


def set_intel_status(
    matter_id: str,
    stage: str,
    message: str = "",
    *,
    progress: Optional[Dict[str, Any]] = None,
    last_error: str = "",
) -> None:
    ensure_practice_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO matter_intel_status (matter_id, stage, message, progress_json, last_error, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(matter_id) DO UPDATE SET
            stage = excluded.stage,
            message = excluded.message,
            progress_json = excluded.progress_json,
            last_error = excluded.last_error,
            updated_at = excluded.updated_at
        """,
        (
            matter_id,
            stage,
            message[:500],
            json.dumps(progress or {}),
            last_error[:800],
            _utc(),
        ),
    )
    conn.commit()
    conn.close()


def get_intel_status(matter_id: str) -> Dict[str, Any]:
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT stage, message, progress_json, last_error, updated_at
        FROM matter_intel_status WHERE matter_id = ?
        """,
        (matter_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {"matter_id": matter_id, "stage": "idle", "message": "", "progress": {}}
    return {
        "matter_id": matter_id,
        "stage": row[0],
        "message": row[1],
        "progress": json.loads(row[2] or "{}"),
        "last_error": row[3] or "",
        "updated_at": row[4],
    }


def _compute_matter_risk_score(progress: Dict[str, Any], contradiction_count: int) -> float:
    """Heuristic 0–1 risk score from pipeline outputs (stub-friendly)."""
    entities = int(progress.get("entities") or 0)
    evidence = int(progress.get("evidence") or 0)
    base = 0.15
    if contradiction_count >= 3:
        base += 0.45
    elif contradiction_count >= 1:
        base += 0.25
    if evidence < 2 and entities > 5:
        base += 0.15
    return round(min(1.0, base), 3)


def _contradiction_detection_stub(
    user_id: str, matter_id: str, pair_count: int
) -> Dict[str, Any]:
    """Structured contradiction summary for API consumers."""
    return {
        "stub": pair_count == 0,
        "matter_id": matter_id,
        "pairs_found": pair_count,
        "severity": "high" if pair_count >= 3 else ("medium" if pair_count else "low"),
        "message": (
            "No contradictions detected in indexed matter documents."
            if pair_count == 0
            else f"{pair_count} potential contradiction(s) flagged for lawyer review."
        ),
    }


def _matter_index_ready(user_id: str, matter_id: str) -> tuple[bool, str]:
    try:
        from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
        from backend.app.core.matter_index import get_matter_index_dir
        from backend.app.core.matter_autopilot import load_matter_doc_texts, _sample_matter_text

        chunks = load_matter_doc_texts(user_id, matter_id)
        text_len = sum(len(c.get("content", "")) for c in chunks)
        if text_len >= 80:
            return True, ""

        idx = get_matter_index_dir(str(user_id), matter_id)
        if index_exists(idx):
            vectors = count_index_vectors(idx)
            text = _sample_matter_text(str(user_id), matter_id, max_chars=500)
            if vectors >= 1 or len(text) >= 80:
                return True, ""

        if list_matter_documents(user_id, matter_id):
            return False, "Documents linked but text not ready. Wait for PDF extraction or re-index."
        return False, "No documents linked to this matter. Upload PDFs first."
    except Exception as exc:
        return False, str(exc)


def run_matter_intelligence_pipeline(
    user_id: str,
    matter_id: str,
    *,
    document_id: str = "",
    skip_if_running: bool = True,
) -> Dict[str, Any]:
    """Run full matter intelligence extraction. Returns summary counts."""
    if not get_matter(user_id, matter_id):
        return {"ok": False, "error": "Matter not found"}

    status = get_intel_status(matter_id)
    if skip_if_running and status.get("stage") in (
        "starting",
        "entities",
        "evidence",
        "timeline",
        "hearings",
        "contradictions",
    ):
        return {"ok": False, "error": "Intelligence pipeline already running", "status": status}

    ready, err = _matter_index_ready(user_id, matter_id)
    if not ready:
        set_intel_status(matter_id, "failed", err, last_error=err)
        _intel_log("matter_pipeline_failed", matter_id=matter_id, reason=err)
        return {"ok": False, "error": err}

    progress: Dict[str, Any] = {}
    set_intel_status(matter_id, "starting", "Analyzing matter documents…", progress=progress)
    _intel_log("matter_pipeline_started", matter_id=matter_id, document_id=document_id)

    results: Dict[str, Any] = {"ok": True, "stages": {}}

    try:
        set_intel_status(matter_id, "entities", "Extracting entities…", progress=progress)
        from backend.app.core.matter_entities import extract_entities_from_docs

        ent = extract_entities_from_docs(user_id, matter_id)
        progress["entities"] = len(ent)
        results["stages"]["entities"] = {"count": len(ent), "ok": True}
        _intel_log("entity_extracted", matter_id=matter_id, count=len(ent))

        set_intel_status(matter_id, "evidence", "Extracting evidence…", progress=progress)
        from backend.app.core.matter_evidence import extract_evidence_from_docs

        ev = extract_evidence_from_docs(user_id, matter_id)
        progress["evidence"] = len(ev)
        results["stages"]["evidence"] = {"count": len(ev), "ok": True}
        _intel_log("evidence_extracted", matter_id=matter_id, count=len(ev))

        set_intel_status(matter_id, "timeline", "Building timeline…", progress=progress)
        from backend.app.core.matter_intelligence import generate_timeline_from_docs

        tl = generate_timeline_from_docs(user_id, matter_id, auto_insert=True)
        progress["timeline"] = tl.get("inserted", 0)
        results["stages"]["timeline"] = tl
        _intel_log("timeline_generated", matter_id=matter_id, inserted=tl.get("inserted", 0))

        set_intel_status(matter_id, "hearings", "Extracting hearings…", progress=progress)
        from backend.app.core.matter_hearings_intel import extract_hearings_from_docs

        try:
            hr = extract_hearings_from_docs(user_id, matter_id)
            progress["hearings"] = hr.get("inserted", 0)
            results["stages"]["hearings"] = hr
            _intel_log("hearing_generated", matter_id=matter_id, inserted=hr.get("inserted", 0))
        except ValueError as exc:
            progress["hearings"] = 0
            results["stages"]["hearings"] = {"ok": False, "error": str(exc), "inserted": 0}
            _intel_log("hearing_extraction_skipped", matter_id=matter_id, reason=str(exc))

        set_intel_status(matter_id, "contradictions", "Finding contradictions…", progress=progress)
        from backend.app.core.matter_enhancements import extract_and_persist_contradictions

        cx = extract_and_persist_contradictions(user_id, matter_id)
        progress["contradictions"] = len(cx.get("pairs") or [])
        results["stages"]["contradictions"] = cx
        _intel_log("contradictions_found", matter_id=matter_id, count=len(cx.get("pairs") or []))

        cx_count = int(progress.get("contradictions") or 0)
        risk_score = _compute_matter_risk_score(progress, cx_count)
        contradiction_report = _contradiction_detection_stub(user_id, matter_id, cx_count)

        set_intel_status(
            matter_id,
            "ready",
            "Matter intelligence ready.",
            progress={**progress, "risk_score": risk_score},
        )
        _intel_log("matter_pipeline_success", matter_id=matter_id, progress=progress)
        results["progress"] = progress
        results["risk_score"] = risk_score
        results["contradiction_report"] = contradiction_report
        results["status"] = get_intel_status(matter_id)
        return results

    except Exception as exc:
        logger.exception("Matter intelligence pipeline failed: %s", exc)
        set_intel_status(
            matter_id,
            "failed",
            f"Pipeline failed: {exc}",
            progress=progress,
            last_error=str(exc),
        )
        _intel_log("matter_pipeline_failed", matter_id=matter_id, error=str(exc))
        return {"ok": False, "error": str(exc), "progress": progress}


def enqueue_matter_intelligence(
    user_id: str,
    matter_id: str,
    *,
    document_id: str = "",
) -> None:
    """Background matter intelligence after document index."""
    from backend.app.core.ml_job_queue import enqueue_ml_job, should_use_ml_queue

    if should_use_ml_queue():
        enqueue_ml_job(
            user_id,
            "matter_intelligence",
            {"matter_id": matter_id, "document_id": document_id, "skip_if_running": True},
        )
        return

    def _run() -> None:
        try:
            run_matter_intelligence_pipeline(
                user_id, matter_id, document_id=document_id, skip_if_running=True
            )
        except Exception:
            logger.exception("Background matter intelligence failed")

    threading.Thread(target=_run, daemon=True, name=f"matter-intel-{matter_id[:8]}").start()
