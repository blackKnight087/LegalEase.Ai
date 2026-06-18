"""
Phase 4 — E-discovery batch ingest, relevance triage, tag learning.
Evidence Intelligence Center — file upload, OCR pipeline, repository.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import get_matter
from backend.app.core.saas_schema import ensure_saas_schema

_EVIDENCE_ITEM_COLUMNS = (
    ("file_type", "TEXT DEFAULT ''"),
    ("file_hash", "TEXT DEFAULT ''"),
    ("metadata_json", "TEXT DEFAULT '{}'"),
    ("entities_json", "TEXT DEFAULT '{}'"),
    ("timeline_json", "TEXT DEFAULT '[]'"),
    ("statutes_json", "TEXT DEFAULT '[]'"),
    ("privilege_json", "TEXT DEFAULT '{}'"),
    ("risks_json", "TEXT DEFAULT '[]'"),
    ("category_json", "TEXT DEFAULT '{}'"),
    ("extraction_method", "TEXT DEFAULT ''"),
)

_TAG_RULES: List[Tuple[str, re.Pattern, float, str]] = [
    (
        "FINANCIAL_FRAUD",
        re.compile(
            r"\b(ledger|adjustment|regulator|audit|conceal|"
            r"misreport|inflate|off[\s-]?book)\b",
            re.I,
        ),
        0.85,
        "References financial manipulation or regulatory evasion.",
    ),
    (
        "INTENT_EVIDENCE",
        re.compile(
            r"\b(make sure|before they|do not tell|delete|"
            r"cover up|hide|destroy)\b",
            re.I,
        ),
        0.9,
        "Suggests consciousness of guilt or deliberate concealment.",
    ),
    (
        "EXCULPATORY",
        re.compile(
            r"\b(not aware|no knowledge|approved by legal|"
            r"compliance signed off|within policy)\b",
            re.I,
        ),
        0.75,
        "May support defendant or corporate compliance position.",
    ),
    (
        "HEARSAY_INADMISSIBLE",
        re.compile(
            r"\b(i heard|rumour|rumor|someone said|"
            r"allegedly|apparently)\b",
            re.I,
        ),
        0.6,
        "Likely hearsay — verify admissibility and foundation.",
    ),
    (
        "PRIVILEGE_RISK",
        re.compile(
            r"\b(attorney[\s-]?client|privileged|"
            r"without prejudice|legal advice)\b",
            re.I,
        ),
        0.8,
        "Potential privilege — review before production.",
    ),
    (
        "CONTRACT_BREACH",
        re.compile(
            r"\b(breach|default|terminate|penalty|"
            r"indemnity|non[\s-]?compete)\b",
            re.I,
        ),
        0.7,
        "Contractual dispute or obligation language.",
    ),
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_evidence_columns(conn) -> None:
    """Add Evidence Intelligence columns to discovery_items (SQLite + Postgres)."""
    from backend.app.core.sql_compat import ensure_columns

    ensure_columns(
        conn,
        "discovery_items",
        tuple(
            (col, typedef, f"ALTER TABLE discovery_items ADD COLUMN {col} {typedef}")
            for col, typedef in _EVIDENCE_ITEM_COLUMNS
        ),
    )


def _apply_tag_weights(user_id: str, matter_id: str, tags: List[str]) -> float:
    if not tags:
        return 0.5
    conn = connect_data_db()
    boost = 0.0
    for tag in tags:
        row = conn.execute(
            """
            SELECT weight_delta FROM discovery_tag_weights
            WHERE user_id = ? AND matter_id = ? AND tag = ?
            """,
            (str(user_id), matter_id, tag),
        ).fetchone()
        if row:
            boost += float(row[0])
    conn.close()
    return min(0.98, max(0.1, 0.5 + boost))


def triage_document(
    text: str,
    *,
    user_id: str = "",
    matter_id: str = "",
) -> Dict[str, Any]:
    """Classify discovery item with tags, score, and rationale."""
    content = (text or "").strip()
    if len(content) < 20:
        return {
            "classification": "LOW_VALUE",
            "tags": [],
            "relevance_score": 0.2,
            "rationale": "Insufficient substantive content.",
        }
    tags: List[str] = []
    rationales: List[str] = []
    base_score = 0.35
    for tag, pat, weight, rationale in _TAG_RULES:
        if pat.search(content):
            tags.append(tag)
            rationales.append(rationale)
            base_score = max(base_score, weight)
    if user_id and matter_id:
        base_score = _apply_tag_weights(user_id, matter_id, tags) or base_score
    if not tags:
        if len(content) > 200:
            tags = ["GENERAL_CORRESPONDENCE"]
            base_score = 0.45
            rationales.append("Routine communication — manual review recommended.")
        else:
            return {
                "classification": "UNREVIEWED",
                "tags": [],
                "relevance_score": 0.3,
                "rationale": "No high-signal evidentiary markers detected.",
            }
    classification = (
        "RELEVANT_HIGH"
        if base_score >= 0.75
        else "RELEVANT_MEDIUM"
        if base_score >= 0.55
        else "RELEVANT_LOW"
    )
    return {
        "classification": classification,
        "tags": tags,
        "relevance_score": round(base_score, 3),
        "rationale": " ".join(rationales[:2]),
    }


def create_batch(
    user_id: str,
    matter_id: str,
    batch_title: str,
    documents: List[Dict[str, str]],
) -> Dict[str, Any]:
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    ensure_saas_schema()
    bid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ediscovery_batches
        (batch_id, matter_id, user_id, batch_title, total_documents_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (bid, matter_id, str(user_id), batch_title, len(documents), now),
    )
    items_out = []
    for doc in documents:
        payload = (doc.get("text") or doc.get("content_payload") or "").strip()
        source = doc.get("source_identifier") or doc.get("filename") or "unknown"
        triage = triage_document(payload, user_id=user_id, matter_id=matter_id)
        iid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO discovery_items
            (item_id, batch_id, source_identifier, content_payload, assigned_tags,
             relevance_score, classification, rationale, reviewed_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                iid,
                bid,
                source[:200],
                payload[:50000],
                ",".join(triage.get("tags") or []),
                triage.get("relevance_score", 0.5),
                triage.get("classification", "UNREVIEWED"),
                triage.get("rationale", ""),
                now,
            ),
        )
        items_out.append(
            {
                "item_id": iid,
                "source_identifier": source,
                **triage,
            }
        )
    conn.commit()
    conn.close()
    high = sum(1 for i in items_out if i.get("classification") == "RELEVANT_HIGH")
    return {
        "batch_id": bid,
        "matter_id": matter_id,
        "batch_title": batch_title,
        "total_documents_count": len(documents),
        "high_relevance_count": high,
        "items": items_out,
    }


def get_batch(user_id: str, batch_id: str) -> Optional[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT batch_id, matter_id, batch_title, total_documents_count, created_at
        FROM ediscovery_batches WHERE batch_id = ? AND user_id = ?
        """,
        (batch_id, str(user_id)),
    ).fetchone()
    if not row:
        conn.close()
        return None
    items = conn.execute(
        """
        SELECT item_id, source_identifier, assigned_tags, relevance_score,
               classification, rationale, reviewed_status, content_payload
        FROM discovery_items WHERE batch_id = ?
        ORDER BY relevance_score DESC
        """,
        (batch_id,),
    ).fetchall()
    conn.close()
    return {
        "batch_id": row[0],
        "matter_id": row[1],
        "batch_title": row[2],
        "total_documents_count": row[3],
        "created_at": row[4],
        "items": [
            {
                "item_id": i[0],
                "source_identifier": i[1],
                "tags": (i[2] or "").split(",") if i[2] else [],
                "relevance_score": i[3],
                "classification": i[4],
                "rationale": i[5],
                "reviewed_status": bool(i[6]),
                "excerpt": (i[7] or "")[:400],
            }
            for i in items
        ],
    }


def list_batches(user_id: str, matter_id: str = "") -> List[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    q = """
        SELECT batch_id, matter_id, batch_title, total_documents_count, created_at
        FROM ediscovery_batches WHERE user_id = ?
    """
    params: List[Any] = [str(user_id)]
    if matter_id:
        q += " AND matter_id = ?"
        params.append(matter_id)
    q += " ORDER BY created_at DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        {
            "batch_id": r[0],
            "matter_id": r[1],
            "batch_title": r[2],
            "total_documents_count": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def review_item(
    user_id: str,
    item_id: str,
    *,
    tags: Optional[List[str]] = None,
    classification: str = "",
    verified: bool = True,
) -> Dict[str, Any]:
    """Lawyer verification — trains tag weights for matter."""
    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT d.item_id, d.batch_id, d.assigned_tags, b.matter_id
        FROM discovery_items d
        JOIN ediscovery_batches b ON b.batch_id = d.batch_id
        WHERE d.item_id = ? AND b.user_id = ?
        """,
        (item_id, str(user_id)),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Item not found"}
    matter_id = row[3]
    tag_str = ",".join(tags) if tags else row[2]
    conn.execute(
        """
        UPDATE discovery_items
        SET assigned_tags = ?, classification = COALESCE(NULLIF(?, ''), classification),
            reviewed_status = ?, relevance_score = MIN(0.99, relevance_score + 0.05)
        WHERE item_id = ?
        """,
        (tag_str, classification, 1 if verified else 0, item_id),
    )
    if tags:
        for tag in tags:
            conn.execute(
                """
                INSERT INTO discovery_tag_weights (user_id, matter_id, tag, weight_delta, updated_at)
                VALUES (?, ?, ?, 0.08, ?)
                ON CONFLICT(user_id, matter_id, tag) DO UPDATE SET
                    weight_delta = MIN(0.5, discovery_tag_weights.weight_delta + 0.05),
                    hit_count = discovery_tag_weights.hit_count + 1,
                    updated_at = excluded.updated_at
                """,
                (str(user_id), matter_id, tag, _utc()),
            )
    conn.commit()
    conn.close()
    return {"recorded": True, "item_id": item_id, "tags": tags or []}


def search_batch(
    user_id: str,
    batch_id: str,
    query: str,
    *,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    batch = get_batch(user_id, batch_id)
    if not batch:
        return []
    ql = query.lower()
    out = []
    for item in batch.get("items") or []:
        blob = f"{item.get('excerpt', '')} {' '.join(item.get('tags') or [])}".lower()
        if ql in blob or not query.strip():
            if float(item.get("relevance_score") or 0) >= min_score:
                out.append(item)
    return sorted(out, key=lambda x: float(x.get("relevance_score") or 0), reverse=True)


def _item_row_to_dict(row: tuple, *, extended: bool = True) -> Dict[str, Any]:
    base = {
        "item_id": row[0],
        "source_identifier": row[1],
        "tags": (row[2] or "").split(",") if row[2] else [],
        "relevance_score": row[3],
        "classification": row[4],
        "rationale": row[5],
        "reviewed_status": bool(row[6]),
        "excerpt": (row[7] or "")[:400],
        "created_at": row[8] if len(row) > 8 else "",
    }
    if extended and len(row) > 9:
        base.update(
            {
                "file_type": row[9] or "",
                "file_hash": row[10] or "",
                "metadata": json.loads(row[11] or "{}"),
                "entities": json.loads(row[12] or "{}"),
                "timeline": json.loads(row[13] or "[]"),
                "statutes": json.loads(row[14] or "[]"),
                "privilege": json.loads(row[15] or "{}"),
                "risks": json.loads(row[16] or "[]"),
                "category": row[17] or "",
                "extraction_method": row[18] or "",
            }
        )
    return base


def process_evidence_upload(
    user_id: str,
    matter_id: str,
    filename: str,
    data: bytes,
    *,
    batch_title: str = "",
) -> Dict[str, Any]:
    """Upload + OCR/extract + full evidence intelligence analysis."""
    from backend.app.core.evidence_extraction import extract_evidence_file
    from backend.app.core.evidence_intelligence import analyze_evidence, match_court_orders

    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    ensure_saas_schema()

    extracted = extract_evidence_file(filename, data)
    text = extracted.get("text") or ""
    if len(text.strip()) < 10:
        return {
            "error": "Could not extract readable text from file. Try OCR-enabled PDF or paste text.",
            "metadata": extracted.get("metadata"),
            "extraction_method": extracted.get("extraction_method"),
        }

    analysis = analyze_evidence(
        text,
        user_id=user_id,
        matter_id=matter_id,
        source=filename,
        metadata=extracted.get("metadata") or {},
    )
    court_orders = match_court_orders(user_id, text, matter_id=matter_id)
    strength = analysis.get("evidence_strength") or {}
    triage_tags = strength.get("tags") or []

    title = batch_title or f"Evidence — {filename}"
    docs = [{"source_identifier": filename, "text": text, "analysis": analysis, "extracted": extracted}]
    batch = create_evidence_batch(user_id, matter_id, title, docs)
    if batch.get("error"):
        return batch
    batch["analysis"] = analysis
    batch["court_orders"] = court_orders
    batch["extraction_method"] = extracted.get("extraction_method")
    return batch


def create_evidence_batch(
    user_id: str,
    matter_id: str,
    batch_title: str,
    documents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create batch with extended evidence intelligence fields."""
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    ensure_saas_schema()
    bid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ediscovery_batches
        (batch_id, matter_id, user_id, batch_title, total_documents_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (bid, matter_id, str(user_id), batch_title, len(documents), now),
    )
    items_out = []
    for doc in documents:
        payload = (doc.get("text") or doc.get("content_payload") or "").strip()
        source = doc.get("source_identifier") or doc.get("filename") or "unknown"
        analysis = doc.get("analysis") or {}
        extracted = doc.get("extracted") or {}
        if not analysis and payload:
            from backend.app.core.evidence_intelligence import analyze_evidence

            analysis = analyze_evidence(
                payload, user_id=user_id, matter_id=matter_id, source=source
            )
        strength = analysis.get("evidence_strength") or triage_document(
            payload, user_id=user_id, matter_id=matter_id
        )
        if isinstance(strength, dict) and "percent" in strength:
            score = strength.get("score", 0.5)
            classification = strength.get("classification", "UNREVIEWED")
            tags = strength.get("tags") or []
            rationale = strength.get("rationale", "")
        else:
            score = strength.get("relevance_score", 0.5)
            classification = strength.get("classification", "UNREVIEWED")
            tags = strength.get("tags") or []
            rationale = strength.get("rationale", "")

        meta = extracted.get("metadata") or analysis.get("metadata") or {}
        iid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO discovery_items
            (item_id, batch_id, source_identifier, content_payload, assigned_tags,
             relevance_score, classification, rationale, reviewed_status, created_at,
             file_type, file_hash, metadata_json, entities_json, timeline_json,
             statutes_json, privilege_json, risks_json, category, extraction_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                iid,
                bid,
                source[:200],
                payload[:50000],
                ",".join(tags),
                score,
                classification,
                rationale,
                now,
                meta.get("file_type", "") or extracted.get("extraction_method", ""),
                meta.get("sha256", ""),
                json.dumps(meta, ensure_ascii=False),
                json.dumps(analysis.get("entities") or {}, ensure_ascii=False),
                json.dumps(analysis.get("timeline") or [], ensure_ascii=False),
                json.dumps(analysis.get("statutes") or [], ensure_ascii=False),
                json.dumps(analysis.get("privilege") or {}, ensure_ascii=False),
                json.dumps(analysis.get("risks") or [], ensure_ascii=False),
                (analysis.get("classification") or {}).get("primary_category", ""),
                extracted.get("extraction_method") or meta.get("extraction_method", ""),
            ),
        )
        items_out.append(
            {
                "item_id": iid,
                "source_identifier": source,
                "relevance_score": score,
                "classification": classification,
                "tags": tags,
                "category": (analysis.get("classification") or {}).get("primary_category"),
                "evidence_strength": strength,
                "entities": analysis.get("entities"),
                "timeline": analysis.get("timeline"),
                "statutes": analysis.get("statutes"),
                "privilege": analysis.get("privilege"),
                "risks": analysis.get("risks"),
                "metadata": meta,
            }
        )
    conn.commit()
    conn.close()
    high = sum(1 for i in items_out if (i.get("evidence_strength") or {}).get("percent", 0) >= 80)
    return {
        "batch_id": bid,
        "matter_id": matter_id,
        "batch_title": batch_title,
        "total_documents_count": len(documents),
        "high_relevance_count": high,
        "items": items_out,
    }


def list_evidence_repository(
    user_id: str,
    *,
    matter_id: str = "",
    limit: int = 100,
) -> Dict[str, Any]:
    """Evidence repository — all analyzed items for user/matter."""
    ensure_saas_schema()
    conn = connect_data_db()
    q = """
        SELECT d.item_id, d.source_identifier, d.assigned_tags, d.relevance_score,
               d.classification, d.rationale, d.reviewed_status, d.content_payload,
               d.created_at, d.file_type, d.file_hash, d.metadata_json, d.entities_json,
               d.timeline_json, d.statutes_json, d.privilege_json, d.risks_json,
               d.category, d.extraction_method, b.matter_id, b.batch_title
        FROM discovery_items d
        JOIN ediscovery_batches b ON b.batch_id = d.batch_id
        WHERE b.user_id = ?
    """
    params: List[Any] = [str(user_id)]
    if matter_id:
        q += " AND b.matter_id = ?"
        params.append(matter_id)
    q += " ORDER BY d.created_at DESC LIMIT ?"
    params.append(limit)
    try:
        rows = conn.execute(q, params).fetchall()
    except Exception:
        q = """
            SELECT d.item_id, d.source_identifier, d.assigned_tags, d.relevance_score,
                   d.classification, d.rationale, d.reviewed_status, d.content_payload,
                   d.created_at, '', '', '{}', '{}', '[]', '[]', '{}', '[]', '', '',
                   b.matter_id, b.batch_title
            FROM discovery_items d
            JOIN ediscovery_batches b ON b.batch_id = d.batch_id
            WHERE b.user_id = ?
        """
        params = [str(user_id)]
        if matter_id:
            q += " AND b.matter_id = ?"
            params.append(matter_id)
        q += " ORDER BY d.created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
    conn.close()
    items = []
    for row in rows:
        item = _item_row_to_dict(row[:19])
        item["matter_id"] = row[19]
        item["batch_title"] = row[20]
        items.append(item)
    from backend.app.core.evidence_intelligence import merge_timelines

    timeline = merge_timelines(
        [{"source_identifier": i["source_identifier"], "timeline": i.get("timeline") or []} for i in items]
    )
    return {"items": items, "count": len(items), "timeline": timeline}


def get_matter_evidence_timeline(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    repo = list_evidence_repository(user_id, matter_id=matter_id, limit=200)
    return repo.get("timeline") or []
