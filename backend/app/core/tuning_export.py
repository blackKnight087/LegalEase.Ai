"""Stage 3 — export thumbs-up interactions as JSONL for LLM fine-tuning."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
EXPORT_DIR = ROOT / "Data" / "tuning_exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def export_positive_interactions(user_id: str = "", limit: int = 5000) -> Dict[str, Any]:
    """Build JSONL from adaptive_feedback + adaptive_interactions."""
    from .db import init_db, session_scope

    init_db()
    lines: List[str] = []
    with session_scope() as db:
        from sqlalchemy import text

        rows = db.execute(
            text(
                """
                SELECT i.query, i.answer_preview, i.mode, f.signal
                FROM adaptive_feedback f
                JOIN adaptive_interactions i ON i.id = f.interaction_id
                WHERE f.signal IN ('thumbs_up', 'helpful')
                AND (:uid = '' OR i.user_id = :uid)
                ORDER BY f.created_at DESC
                LIMIT :lim
                """
            ),
            {"uid": str(user_id), "lim": limit},
        ).fetchall()
        for q, a, mode, sig in rows:
            if not q or not a or len(a) < 40:
                continue
            record = {
                "messages": [
                    {"role": "system", "content": f"You are LegalEase assistant ({mode})."},
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": a},
                ],
                "metadata": {"signal": sig, "user_id": user_id},
            }
            lines.append(json.dumps(record, ensure_ascii=False))

    if not lines:
        return {"status": "empty", "record_count": 0, "path": ""}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = EXPORT_DIR / f"tuning_{user_id or 'all'}_{ts}.jsonl"
    out.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "record_count": len(lines), "path": str(out)}


def export_saas_training_pairs(user_id: str = "", limit: int = 2000) -> Dict[str, Any]:
    """Stage-3 JSONL from billing lexicon, CRM intents, and discovery rationales."""
    from backend.app.core.database import connect_data_db
    from backend.app.core.saas_schema import ensure_saas_schema

    ensure_saas_schema()
    lines: List[str] = []
    conn = connect_data_db()
    uid = str(user_id)

    lex_q = (
        "SELECT raw_sample, polished_narrative FROM financial_lexicon_cache "
        "WHERE LENGTH(polished_narrative) > 40 ORDER BY hit_count DESC LIMIT ?"
    )
    lex_params: tuple = (limit // 4,)
    if uid:
        lex_q = (
            "SELECT raw_sample, polished_narrative FROM financial_lexicon_cache "
            "WHERE user_id = ? AND LENGTH(polished_narrative) > 40 ORDER BY hit_count DESC LIMIT ?"
        )
        lex_params = (uid, limit // 4)
    for raw, polished in conn.execute(lex_q, lex_params).fetchall():
        rec = {
            "instruction": "Translate a raw activity log into a professional billing narrative for an Indian law invoice.",
            "input": raw,
            "output": polished,
            "metadata": {"module": "billing"},
        }
        lines.append(json.dumps(rec, ensure_ascii=False))

    crm_q = (
        "SELECT raw_intake_query, calculated_intent FROM crm_leads "
        "WHERE LENGTH(raw_intake_query) > 20 ORDER BY updated_at DESC LIMIT ?"
    )
    crm_params: tuple = (limit // 4,)
    if uid:
        crm_q = (
            "SELECT raw_intake_query, calculated_intent FROM crm_leads "
            "WHERE user_id = ? AND LENGTH(raw_intake_query) > 20 ORDER BY updated_at DESC LIMIT ?"
        )
        crm_params = (uid, limit // 4)
    for raw_q, intent in conn.execute(crm_q, crm_params).fetchall():
        rec = {
            "instruction": "Classify consumer legal intake and extract practice area intent.",
            "input": raw_q[:800],
            "output": json.dumps({"intent": intent}),
            "metadata": {"module": "crm"},
        }
        lines.append(json.dumps(rec, ensure_ascii=False))

    for content, tags, rationale in conn.execute(
        """
        SELECT content_payload, assigned_tags, rationale FROM discovery_items
        ORDER BY relevance_score DESC LIMIT ?
        """,
        (limit // 4,),
    ).fetchall():
        if len(content or "") < 30:
            continue
        rec = {
            "instruction": "Evaluate discovery text and assign relevance tier and tags.",
            "input": (content or "")[:1200],
            "output": json.dumps({"tags": (tags or "").split(","), "rationale": rationale}),
            "metadata": {"module": "ediscovery"},
        }
        lines.append(json.dumps(rec, ensure_ascii=False))

    conn.close()
    if not lines:
        return {"status": "empty", "record_count": 0, "path": ""}
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = EXPORT_DIR / f"saas_tuning_{user_id or 'all'}_{ts}.jsonl"
    out.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "record_count": len(lines), "path": str(out)}
