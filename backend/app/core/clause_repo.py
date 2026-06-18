"""Document templates & clause library — Phase 1 automation studio."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.practice_schema import ensure_practice_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_templates(user_id: str, *, practice_area: str = "") -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    q = """
        SELECT template_id, user_id, template_name, practice_area,
               variable_json_map, created_at, updated_at
        FROM document_templates
        WHERE user_id = ? OR user_id = ''
    """
    params: List[Any] = [str(user_id)]
    if practice_area:
        q += " AND practice_area = ?"
        params.append(practice_area)
    q += " ORDER BY template_name"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [_template_summary(r) for r in rows]


def get_template(user_id: str, template_id: str) -> Optional[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT template_id, user_id, template_name, practice_area,
               raw_markdown_structure, variable_json_map, created_at, updated_at
        FROM document_templates
        WHERE template_id = ? AND (user_id = ? OR user_id = '')
        """,
        (template_id, str(user_id)),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _template_full(row)


def create_template(
    user_id: str,
    *,
    template_name: str,
    practice_area: str,
    raw_markdown_structure: str,
    variable_json_map: Optional[List[str]] = None,
) -> Dict[str, Any]:
    ensure_practice_schema()
    import re

    tid = str(uuid.uuid4())
    now = _utc()
    vars_ = variable_json_map or sorted(
        set(re.findall(r"\{(\w+)\}", raw_markdown_structure))
    )
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO document_templates
        (template_id, user_id, template_name, practice_area,
         raw_markdown_structure, variable_json_map, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tid,
            str(user_id),
            template_name.strip(),
            practice_area.strip() or "General",
            raw_markdown_structure,
            json.dumps(vars_),
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return get_template(user_id, tid) or {}


def render_template(
    user_id: str,
    template_id: str,
    variables: Dict[str, str],
) -> Dict[str, Any]:
    tpl = get_template(user_id, template_id)
    if not tpl:
        return {"error": "Template not found"}
    body = tpl["raw_markdown_structure"]
    missing = []
    for key in tpl.get("variables") or []:
        val = variables.get(key) or variables.get(key.lower())
        if val is None or str(val).strip() == "":
            missing.append(key)
            continue
        body = body.replace("{" + key + "}", str(val))
    return {
        "template_id": template_id,
        "rendered": body,
        "missing_variables": missing,
    }


def list_clauses(
    user_id: str,
    *,
    practice_area: str = "",
    tag: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    q = """
        SELECT clause_id, clause_tag, practice_area, clause_text_content,
               confidence_weight, user_id
        FROM clause_library
        WHERE user_id = ? OR user_id = ''
    """
    params: List[Any] = [str(user_id)]
    if practice_area:
        q += " AND practice_area = ?"
        params.append(practice_area)
    if tag:
        q += " AND clause_tag LIKE ?"
        params.append(f"%{tag}%")
    q += " ORDER BY confidence_weight DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        {
            "clause_id": r[0],
            "clause_tag": r[1],
            "practice_area": r[2],
            "clause_text_content": r[3],
            "confidence_weight": r[4],
            "user_id": r[5],
        }
        for r in rows
    ]


def upsert_clause(
    user_id: str,
    *,
    clause_tag: str,
    clause_text_content: str,
    practice_area: str = "General",
    confidence_weight: float = 1.0,
) -> Dict[str, Any]:
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT clause_id FROM clause_library
        WHERE (user_id = ? OR user_id = '') AND clause_tag = ?
        ORDER BY confidence_weight DESC LIMIT 1
        """,
        (str(user_id), clause_tag),
    ).fetchone()
    now = _utc()
    if row:
        cid = row[0]
        conn.execute(
            """
            UPDATE clause_library
            SET clause_text_content = ?, confidence_weight = ?, updated_at = ?
            WHERE clause_id = ?
            """,
            (clause_text_content, confidence_weight, now, cid),
        )
    else:
        cid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO clause_library
            (clause_id, user_id, clause_tag, practice_area, clause_text_content,
             confidence_weight, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                str(user_id),
                clause_tag,
                practice_area,
                clause_text_content,
                confidence_weight,
                now,
                now,
            ),
        )
    conn.commit()
    conn.close()
    return {"clause_id": cid, "clause_tag": clause_tag, "confidence_weight": confidence_weight}


def adjust_clause_confidence(
    user_id: str,
    clause_tag: str,
    *,
    delta: float,
    practice_area: str = "",
) -> None:
    """Self-upgrade loop: boost or penalize clause ranking after lawyer edits."""
    ensure_practice_schema()
    conn = connect_data_db()
    q = """
        UPDATE clause_library
        SET confidence_weight = MIN(3.0, MAX(0.1, confidence_weight + ?)),
            updated_at = ?
        WHERE clause_tag = ? AND (user_id = ? OR user_id = '')
    """
    params: List[Any] = [delta, _utc(), clause_tag, str(user_id)]
    if practice_area:
        q += " AND practice_area = ?"
        params.append(practice_area)
    conn.execute(q, params)
    conn.commit()
    conn.close()


def record_clause_edit_delta(
    user_id: str,
    *,
    baseline: str,
    accepted: str,
    practice_area: str = "Corporate",
    clause_tag: str = "CUSTOM_EDIT",
) -> Dict[str, Any]:
    """Capture lawyer's finalized clause vs AI baseline for Stage-3 tuning."""
    import difflib

    ratio = difflib.SequenceMatcher(None, baseline[:2000], accepted[:2000]).ratio()
    if ratio < 0.85:
        upsert_clause(
            user_id,
            clause_tag=clause_tag,
            clause_text_content=accepted[:4000],
            practice_area=practice_area,
            confidence_weight=1.2,
        )
        adjust_clause_confidence(user_id, clause_tag, delta=0.15, practice_area=practice_area)
    return {"recorded": True, "similarity": round(ratio, 3)}


def _template_summary(row) -> Dict[str, Any]:
    return {
        "template_id": row[0],
        "user_id": row[1],
        "template_name": row[2],
        "practice_area": row[3],
        "variables": json.loads(row[4] or "[]") if len(row) <= 7 else json.loads(row[5] or "[]"),
        "created_at": row[5] if len(row) <= 7 else row[6],
        "updated_at": row[6] if len(row) <= 7 else row[7],
    }


def _template_full(row) -> Dict[str, Any]:
    return {
        "template_id": row[0],
        "user_id": row[1],
        "template_name": row[2],
        "practice_area": row[3],
        "raw_markdown_structure": row[4],
        "variables": json.loads(row[5] or "[]"),
        "created_at": row[6],
        "updated_at": row[7],
    }
