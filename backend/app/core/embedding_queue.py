"""
Document embedding queue — sequential processing, progress, retry.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("legalease.embedding.queue")

_lock = threading.Lock()
_queue: List[Dict[str, Any]] = {}
_worker_started = False


class DocQueueState(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    EMBEDDED = "EMBEDDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_document(
    user_id: str,
    doc_id: str,
    *,
    filename: str = "",
    matter_id: str = "",
    use_ocr: Optional[bool] = None,
    index_job_id: str = "",
) -> str:
    qid = str(uuid.uuid4())
    with _lock:
        _queue.append(
            {
                "queue_id": qid,
                "user_id": user_id,
                "doc_id": doc_id,
                "filename": filename,
                "matter_id": matter_id,
                "use_ocr": use_ocr,
                "index_job_id": index_job_id,
                "state": DocQueueState.PENDING.value,
                "message": "Queued for embedding",
                "progress_page": 0,
                "progress_pages": 0,
                "progress_chunk": 0,
                "progress_chunks": 0,
                "retries": 0,
                "created_at": _utc(),
                "updated_at": _utc(),
            }
        )
    logger.info("[EMBEDDING] Queued doc %s (%s)", doc_id, filename)
    return qid


def update_queue_item(qid: str, **fields: Any) -> None:
    with _lock:
        for row in _queue:
            if row.get("queue_id") == qid:
                row.update(fields)
                row["updated_at"] = _utc()
                break


def get_queue_snapshot(user_id: str = "") -> Dict[str, Any]:
    with _lock:
        rows = [dict(r) for r in _queue if not user_id or r.get("user_id") == user_id]
    pending = sum(1 for r in rows if r.get("state") == DocQueueState.PENDING.value)
    processing = sum(1 for r in rows if r.get("state") == DocQueueState.PROCESSING.value)
    failed = sum(1 for r in rows if r.get("state") == DocQueueState.FAILED.value)
    return {
        "queue_size": pending + processing,
        "pending": pending,
        "processing": processing,
        "failed": failed,
        "items": rows[-20:],
    }


def list_failed_doc_ids(user_id: str) -> List[str]:
    with _lock:
        return [
            str(r["doc_id"])
            for r in _queue
            if r.get("user_id") == user_id and r.get("state") == DocQueueState.FAILED.value
        ]
