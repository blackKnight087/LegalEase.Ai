"""
Settings-only Gemini coach for local Ollama / LM Studio improvement.

Gemini is NEVER called during Knowledge Base or chat turns. It only runs when
the user explicitly triggers tuning from Settings (analyze feedback, heal intent,
enrich neural training datasets, update persona/facts that Ollama reads).

Improves Ollama indirectly via:
  - user_memory persona / facts / communication_notes
  - neural_finetuning query–passage pairs
  - adaptive_learning query expansions
  - tuning_export JSONL enrichment
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLED = os.getenv("GEMINI_OLLAMA_TUNING", "0").lower() in {"1", "true", "yes"}
COACH_MODEL = os.getenv("GEMINI_COACH_MODEL", os.getenv("GEMINI_FREE_MODEL", "gemini-2.5-flash")).strip()
MAX_FEEDBACK_ROWS = int(os.getenv("GEMINI_COACH_FEEDBACK_LIMIT", "25"))

# Re-export guards — single source of truth in coach_guards.py
from backend.app.core.coach_guards import (  # noqa: E402
    ALLOWED_COACH_FACT_KEYS as _ALLOWED_COACH_FACT_KEYS,
    LEGAL_SUBSTANCE_RE as _LEGAL_SUBSTANCE_RE,
    guard_rlaif_style_score,
    is_allowed_coach_fact_key,
    parse_coach_json as _parse_coach_json_guarded,
    sanitize_coach_style_text,
    validate_coach_insights,
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    from backend.app.core.database import connect_data_db

    return connect_data_db()


def ensure_coach_schema() -> None:
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ollama_coach_prefs (
            user_id TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            auto_schedule_enabled INTEGER DEFAULT 1,
            last_run_at TEXT,
            last_auto_coach_at TEXT,
            feedback_count_at_last_coach INTEGER DEFAULT 0,
            last_insights_json TEXT DEFAULT '{}',
            directives_text TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ollama_coach_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL,
            feedback_count INTEGER DEFAULT 0,
            insights_json TEXT DEFAULT '{}',
            applied_json TEXT DEFAULT '{}',
            error TEXT,
            created_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ollama_coach_memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            insights_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_coach_mem_uid
            ON ollama_coach_memories(user_id, created_at DESC)"""
        )
        _ensure_column(conn, "ollama_coach_prefs", "directives_text", "TEXT DEFAULT ''")
        _ensure_column(conn, "ollama_coach_prefs", "auto_schedule_enabled", "INTEGER DEFAULT 1")
        _ensure_column(conn, "ollama_coach_prefs", "last_auto_coach_at", "TEXT")
        _ensure_column(conn, "ollama_coach_prefs", "feedback_count_at_last_coach", "INTEGER DEFAULT 0")
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn, table: str, column: str, col_def: str) -> None:
    from backend.app.core.sql_compat import ensure_columns

    ensure_columns(conn, table, ((column, col_def, f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"),))


def _gemini_ready() -> bool:
    from backend.app.core.web_intelligence import gemini_configured

    return gemini_configured()


def coach_available() -> bool:
    return ENABLED and _gemini_ready()


def get_coach_prefs(user_id: str) -> Dict[str, Any]:
    ensure_coach_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT enabled, last_run_at, last_insights_json, directives_text FROM ollama_coach_prefs WHERE user_id=?",
            (str(user_id),),
        ).fetchone()
        if not row:
            return {
                "enabled": False,
                "last_run_at": None,
                "last_insights": {},
                "directives_text": "",
            }
        insights = {}
        try:
            insights = json.loads(row[2] or "{}")
        except Exception:
            pass
        return {
            "enabled": bool(row[0]),
            "last_run_at": row[1],
            "last_insights": insights,
            "directives_text": (row[3] or "") if len(row) > 3 else "",
        }
    finally:
        conn.close()


def set_coach_enabled(user_id: str, enabled: bool) -> Dict[str, Any]:
    ensure_coach_schema()
    uid = str(user_id)
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO ollama_coach_prefs (user_id, enabled, auto_schedule_enabled, updated_at)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at""",
            (uid, 1 if enabled else 0, _utc()),
        )
        conn.commit()
    finally:
        conn.close()
    return get_coach_prefs(uid)


def coach_status(user_id: str, membership: str = "Free") -> Dict[str, Any]:
    prefs = get_coach_prefs(user_id)
    usage: Dict[str, Any] = {}
    try:
        from backend.app.core.gemini_usage import usage_summary

        usage = usage_summary(str(user_id), membership)
    except Exception:
        pass
    schedule: Dict[str, Any] = {}
    export_info: Dict[str, Any] = {}
    try:
        from backend.app.core.coach_scheduler import get_schedule_prefs

        schedule = get_schedule_prefs(user_id)
    except Exception:
        pass
    try:
        from backend.app.core.ollama_modelfile_export import latest_export_info

        export_info = latest_export_info(user_id)
    except Exception:
        pass
    return {
        "global_enabled": ENABLED,
        "gemini_configured": _gemini_ready(),
        "available": coach_available(),
        "user_enabled": prefs.get("enabled", False),
        "last_run_at": prefs.get("last_run_at"),
        "last_insights": prefs.get("last_insights") or {},
        "directives_text": prefs.get("directives_text") or "",
        "memory_count": _coach_memory_count(user_id),
        "recent_memories": list_coach_memories(user_id, limit=5),
        "schedule": schedule,
        "ollama_export": export_info,
        "model": COACH_MODEL,
        "scope": "settings_only",
        "gemini_usage": usage,
    }


def _fetch_feedback_rows(user_id: str, limit: int = MAX_FEEDBACK_ROWS) -> List[Dict[str, Any]]:
    from backend.app.core.adaptive_learning import ensure_learning_schema

    ensure_learning_schema()
    conn = _connect()
    rows: List[Dict[str, Any]] = []
    try:
        cur = conn.execute(
            """SELECT i.mode, i.query, i.answer_preview, i.found_in_kb, f.signal, f.comment, f.created_at
            FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE i.user_id=?
            ORDER BY f.created_at DESC
            LIMIT ?""",
            (str(user_id), limit),
        )
        for mode, query, answer, found, signal, comment, created in cur.fetchall():
            rows.append(
                {
                    "mode": mode or "knowledge_base",
                    "query": (query or "")[:400],
                    "answer_preview": (answer or "")[:600],
                    "found_in_kb": bool(found),
                    "signal": signal,
                    "comment": (comment or "")[:200],
                    "created_at": created,
                }
            )
    finally:
        conn.close()
    return rows


def _fetch_correction_rows(user_id: str, limit: int = 10) -> List[Dict[str, str]]:
    """Recent implicit corrections — user re-phrased after a bad answer."""
    from backend.app.core.adaptive_learning import ensure_learning_schema

    ensure_learning_schema()
    conn = _connect()
    out: List[Dict[str, str]] = []
    try:
        cur = conn.execute(
            """SELECT mode, query_norm, successful_expansion
            FROM adaptive_query_patterns
            WHERE user_id=? AND fail_count > 0 AND LENGTH(successful_expansion) > 5
            ORDER BY last_used DESC
            LIMIT ?""",
            (str(user_id), limit),
        )
        for mode, qn, expansion in cur.fetchall():
            out.append({"mode": mode, "query_norm": qn, "better_phrasing": expansion[:300]})
    finally:
        conn.close()
    return out


def _coach_memory_count(user_id: str) -> int:
    ensure_coach_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM ollama_coach_memories WHERE user_id=?",
            (str(user_id),),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def list_coach_memories(user_id: str, *, limit: int = 10) -> List[Dict[str, Any]]:
    ensure_coach_schema()
    conn = _connect()
    try:
        cur = conn.execute(
            """SELECT id, source, content, created_at FROM ollama_coach_memories
            WHERE user_id=? ORDER BY created_at DESC LIMIT ?""",
            (str(user_id), limit),
        )
        return [
            {"id": r[0], "source": r[1], "content": r[2][:300], "created_at": r[3]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def store_coach_memory(
    user_id: str,
    source: str,
    content: str,
    *,
    insights: Optional[Dict[str, Any]] = None,
) -> str:
    ensure_coach_schema()
    mid = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO ollama_coach_memories (id, user_id, source, content, insights_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                mid,
                str(user_id),
                source[:40],
                content[:1200],
                json.dumps(insights or {}, ensure_ascii=False),
                _utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return mid


def get_coach_memory_block(user_id: str, *, limit: int = 6) -> str:
    """
    Style-only tuning hints for Ollama KB prompts.
    NEVER inject legal answers or Gemini-generated substance — format/behavior only.
    """
    memories = list_coach_memories(user_id, limit=limit * 2)
    if not memories:
        return ""
    lines = [
        "Response style preferences (from user feedback — NOT legal facts; "
        "always cite uploaded documents for substance):"
    ]
    added = 0
    for m in memories:
        if added >= limit:
            break
        src = m.get("source", "")
        raw = (m.get("content") or "").strip()
        if not raw:
            continue
        if src == "user_directive":
            snippet = sanitize_coach_style_text(raw, max_len=180)
        elif src == "negative_feedback" and "| Issue:" in raw:
            snippet = sanitize_coach_style_text(raw.split("| Issue:", 1)[1], max_len=160)
        else:
            continue
        if snippet:
            lines.append(f"- {snippet}")
            added += 1
    if added == 0:
        return ""
    return "\n".join(lines)[:1200]


def get_directives(user_id: str) -> str:
    return (get_coach_prefs(user_id).get("directives_text") or "").strip()


def save_directives(user_id: str, text: str) -> Dict[str, Any]:
    ensure_coach_schema()
    uid = str(user_id)
    cleaned = (text or "").strip()[:4000]
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO ollama_coach_prefs (user_id, enabled, directives_text, updated_at)
            VALUES (?, 0, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET directives_text=excluded.directives_text, updated_at=excluded.updated_at""",
            (uid, cleaned, _utc()),
        )
        conn.commit()
    finally:
        conn.close()
    if cleaned:
        store_coach_memory(uid, "user_directive", cleaned)
    return {"ok": True, "directives_text": cleaned}


def _fetch_interaction_detail(
    user_id: str,
    *,
    interaction_id: str = "",
    chat_id: str = "",
) -> Optional[Dict[str, Any]]:
    from backend.app.core.adaptive_learning import ensure_learning_schema

    ensure_learning_schema()
    conn = _connect()
    try:
        row = None
        if interaction_id:
            row = conn.execute(
                """SELECT id, mode, query, answer_preview, found_in_kb
                FROM adaptive_interactions WHERE id=? AND user_id=?""",
                (interaction_id, str(user_id)),
            ).fetchone()
        elif chat_id:
            row = conn.execute(
                """SELECT id, mode, query, answer_preview, found_in_kb
                FROM adaptive_interactions WHERE chat_id=? AND user_id=?
                ORDER BY created_at DESC LIMIT 1""",
                (chat_id, str(user_id)),
            ).fetchone()
        if not row:
            return None
        return {
            "interaction_id": row[0],
            "mode": row[1] or "knowledge_base",
            "query": (row[2] or "")[:400],
            "answer_preview": (row[3] or "")[:800],
            "found_in_kb": bool(row[4]),
        }
    finally:
        conn.close()


def _build_coach_prompt(
    user_id: str,
    feedback: List[Dict[str, Any]],
    corrections: List[Dict[str, str]],
    *,
    user_directives: str = "",
    negative_detail: Optional[Dict[str, Any]] = None,
) -> str:
    from backend.app.core.user_memory import get_or_create_profile

    prof = get_or_create_profile(user_id)
    stats: Dict[str, Any] = {}
    try:
        from backend.app.core.adaptive_learning import learning_stats

        stats = learning_stats(user_id)
    except Exception:
        pass

    payload = {
        "user_profile": {
            "persona": prof.get("persona", "warm"),
            "practice_area": prof.get("practice_area", ""),
            "communication_notes": prof.get("communication_notes", ""),
        },
        "user_improvement_instructions": user_directives or get_directives(user_id),
        "coach_memories": list_coach_memories(user_id, limit=8),
        "learning_summary": stats.get("summary") or {},
        "recent_feedback": feedback,
        "correction_patterns": corrections,
    }
    if negative_detail:
        payload["negative_feedback_detail"] = negative_detail
    return (
        "Analyze this LegalEase user's feedback from AI Chat and Litigation Desk (mode may be "
        "knowledge_base, court_day, evidence_desk, etc.) to help their LOCAL Ollama/LM Studio model answer better. "
        "Litigation Desk feedback may cover cause-list prep or contradiction quality — "
        "not KB retrieval. You are a tuning coach — do NOT answer legal questions.\n\n"
        f"DATA:\n{json.dumps(payload, ensure_ascii=False)[:12000]}\n\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "summary": "2-3 sentence overview of STYLE/FORMAT improvements only",\n'
        '  "intent_issues": [{"pattern": "...", "fix": "retrieval phrasing only"}],\n'
        '  "persona_suggestion": "warm|professional|concise|detailed|keep",\n'
        '  "communication_notes_addition": "STYLE only: length, bullets, tone — NO legal rules",\n'
        '  "suggested_facts": [{"key": "answer_style|response_length|tone|...", "value": "format pref"}],\n'
        '  "preference_updates": {"detail_level": 0.8, "prefer_bullets": 0.7, "structure_preference": "sections"},\n'
        '  "training_pairs": [],\n'
        '  "query_healings": [{"mode": "knowledge_base", "query_norm": "...", "expansion": "..."}],\n'
        '  "healing_actions": ["style bullet 1"]\n'
        "}\n"
        "STRICT: You are a META tuning coach only. NEVER output legal answers, statutes, "
        "case holdings, or what Ollama should say about the law. NEVER fill training_pairs — "
        "training data comes from user thumbs-up only. suggested_facts keys must be style/format "
        "(answer_style, response_length, tone, prefer_bullets). communication_notes_addition must "
        "be how to format answers, not legal content. query_healings = search phrasing only.\n"
        "Max 4 suggested_facts, max 3 query_healings. "
        "Honor user_improvement_instructions for style preferences only."
    )


def analyze_user_directives(
    user_id: str,
    directives: str,
    *,
    membership: str = "Free",
    apply: bool = True,
) -> Dict[str, Any]:
    """User types how Ollama should improve — Gemini analyzes and applies to memory/training."""
    text = (directives or "").strip()
    if not text:
        return {"ok": False, "error": "Please describe what to improve."}
    save_directives(user_id, text)
    if not coach_available():
        return {
            "ok": True,
            "saved": True,
            "coach_applied": False,
            "message": "Instructions saved. Enable GEMINI_OLLAMA_TUNING=1 to analyze with Gemini.",
        }
    prefs = get_coach_prefs(user_id)
    if not prefs.get("enabled"):
        return {
            "ok": True,
            "saved": True,
            "coach_applied": False,
            "message": "Instructions saved. Enable the tuning coach to analyze with Gemini.",
        }
    feedback = _fetch_feedback_rows(user_id, limit=10)
    corrections = _fetch_correction_rows(user_id, limit=5)
    prompt = _build_coach_prompt(
        user_id, feedback, corrections, user_directives=text
    )
    try:
        insights = _sanitize_insights(_call_gemini_coach(prompt, user_id, membership))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "saved": True}
    store_coach_memory(user_id, "user_directive", text, insights=insights)
    applied: Dict[str, Any] = {}
    if apply:
        applied = apply_coaching_insights(user_id, insights)
        try:
            from backend.app.core.neural_finetuning import collect_pairs_from_feedback, maybe_auto_train

            collect_pairs_from_feedback(str(user_id), limit=100)
            maybe_auto_train(str(user_id))
        except Exception:
            pass
    conn = _connect()
    try:
        conn.execute(
            """UPDATE ollama_coach_prefs SET last_run_at=?, last_insights_json=?, updated_at=? WHERE user_id=?""",
            (_utc(), json.dumps(insights, ensure_ascii=False), _utc(), str(user_id)),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "saved": True,
        "coach_applied": True,
        "insights": insights,
        "applied": applied,
        "message": "Your instructions were analyzed and applied to Ollama memory and training.",
    }


def process_negative_feedback(
    user_id: str,
    *,
    interaction_id: str = "",
    chat_id: str = "",
    user_comment: str = "",
    membership: str = "Free",
) -> Dict[str, Any]:
    """
    User submitted thumbs-down + what went wrong — Gemini analyzes and tunes Ollama rapidly.
    Triggered only when user submits the feedback form (not during answer generation).
    """
    comment = (user_comment or "").strip()
    if not comment:
        return {"ok": False, "skipped": True, "reason": "no_comment"}

    detail = _fetch_interaction_detail(
        user_id, interaction_id=interaction_id, chat_id=chat_id
    )
    if not detail:
        return {"ok": False, "error": "Could not find this chat turn."}

    store_coach_memory(
        user_id,
        "negative_feedback",
        f"Q: {detail.get('query', '')[:200]} | Issue: {comment[:400]}",
    )

    if not coach_available():
        return {
            "ok": True,
            "saved": True,
            "coach_applied": False,
            "message": "Feedback saved. Enable GEMINI_OLLAMA_TUNING for automatic tuning.",
        }

    prefs = get_coach_prefs(user_id)
    if not prefs.get("enabled"):
        return {
            "ok": True,
            "saved": True,
            "coach_applied": False,
            "message": "Feedback saved. Enable tuning coach in Settings for Gemini analysis.",
        }

    negative_detail = {
        **detail,
        "user_comment": comment,
        "signal": "thumbs_down",
    }

    def _coach_job() -> None:
        try:
            feedback = _fetch_feedback_rows(user_id, limit=8)
            corrections = _fetch_correction_rows(user_id, limit=5)
            prompt = _build_coach_prompt(
                user_id,
                feedback,
                corrections,
                user_directives=get_directives(user_id),
                negative_detail=negative_detail,
            )
            insights = _sanitize_insights(_call_gemini_coach(prompt, user_id, membership))
            store_coach_memory(
                user_id,
                "negative_feedback",
                comment,
                insights=insights,
            )
            apply_coaching_insights(user_id, insights)
            try:
                from backend.app.core.improvement_automation import schedule_improvement_pipeline

                schedule_improvement_pipeline(str(user_id), trigger="thumbs_down", membership=membership)
            except Exception:
                pass
        except Exception as exc:
            logger.warning("negative feedback coach failed: %s", exc)

    threading.Thread(
        target=_coach_job,
        daemon=True,
        name=f"coach-neg-{str(user_id)[:8]}",
    ).start()

    return {
        "ok": True,
        "saved": True,
        "coach_applied": False,
        "message": "Feedback saved — tuning runs in the background.",
    }


def _parse_coach_json(text: str) -> Dict[str, Any]:
    data, rejections = _parse_coach_json_guarded(text)
    if data is None:
        raw = (text or "").strip()
        return {"summary": raw[:500], "parse_error": True, "guard_rejections": rejections}
    if rejections:
        data["guard_rejections"] = rejections
    return data


def _sanitize_insights(raw: Dict[str, Any]) -> Dict[str, Any]:
    cleaned, rejections = validate_coach_insights(raw or {})
    if rejections:
        cleaned["guard_rejections"] = rejections
    return cleaned


def score_answer_style_rlaif(
    query: str,
    answer_preview: str,
    *,
    user_id: str = "",
    membership: str = "Free",
) -> Optional[Dict[str, Any]]:
    """RLAIF style-only scoring — never legal correctness."""
    if not coach_available() or not answer_preview:
        return None
    prompt = (
        "Score ONLY writing quality (NOT legal correctness). Return JSON with floats 0-1:\n"
        '{"clarity":0.8,"structure":0.7,"conciseness":0.6,"citation_format":0.5,'
        '"tone_match":0.7,"follow_up_quality":0.5}\n'
        "Do NOT score whether the legal answer is correct. Do NOT comment on law.\n"
        f"Query: {(query or '')[:200]}\n"
        f"Answer excerpt: {answer_preview[:500]}"
    )
    try:
        raw = _call_gemini_coach(prompt, user_id or "system", membership)
        return guard_rlaif_style_score(raw)
    except Exception as exc:
        logger.debug("RLAIF score failed: %s", exc)
        return None


def _call_gemini_coach(prompt: str, user_id: str, membership: str) -> Dict[str, Any]:
    from backend.app.core.gemini_usage import assert_gemini_allowed, record_gemini_call
    from backend.app.core.web_intelligence import GEMINI_API_KEY

    assert_gemini_allowed(str(user_id), membership)
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=COACH_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are LegalEase AI Tuning Coach — META-LEVEL ONLY. Output JSON only. "
                "Improve how a local Ollama assistant formats and retrieves answers. "
                "NEVER produce legal advice, legal facts, case law, statutes, or answer text. "
                "NEVER tell Ollama what to say about the law — only style, length, tone, "
                "and search-query phrasing. Do not use web search."
            ),
            temperature=0.15,
            max_output_tokens=1800,
            response_mime_type="application/json",
        ),
    )
    record_gemini_call(str(user_id))
    text = (getattr(response, "text", None) or "").strip()
    if not text:
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", None) or []:
                t = getattr(part, "text", None)
                if t:
                    text = t.strip()
                    break
    return _parse_coach_json(text)


def analyze_feedback(
    user_id: str,
    *,
    membership: str = "Free",
    apply: bool = False,
) -> Dict[str, Any]:
    """Settings-only: Gemini analyzes feedback and optionally applies safe improvements."""
    if not coach_available():
        return {
            "ok": False,
            "error": "AI tuning coach unavailable. Set GEMINI_OLLAMA_TUNING=1 and GEMINI_API_KEY.",
        }

    prefs = get_coach_prefs(user_id)
    if not prefs.get("enabled"):
        return {
            "ok": False,
            "error": "Enable AI tuning coach in Settings first.",
        }

    feedback = _fetch_feedback_rows(user_id)
    if len(feedback) < 2:
        return {
            "ok": False,
            "error": "Need at least 2 feedback entries (thumbs up/down). Chat more and rate answers.",
            "feedback_count": len(feedback),
        }

    corrections = _fetch_correction_rows(user_id)
    prompt = _build_coach_prompt(user_id, feedback, corrections)

    run_id = str(uuid.uuid4())
    ensure_coach_schema()
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO ollama_coach_runs (id, user_id, status, feedback_count, created_at)
            VALUES (?, ?, 'running', ?, ?)""",
            (run_id, str(user_id), len(feedback), _utc()),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        insights = _sanitize_insights(_call_gemini_coach(prompt, user_id, membership))
    except Exception as exc:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE ollama_coach_runs SET status='failed', error=? WHERE id=?",
                (str(exc)[:400], run_id),
            )
            conn.commit()
        finally:
            conn.close()
        try:
            from backend.app.core.gemini_errors import gemini_error_user_hint, is_gemini_quota_error

            err = gemini_error_user_hint(exc) if is_gemini_quota_error(exc) else str(exc)
        except Exception:
            err = str(exc)
        return {"ok": False, "error": err, "run_id": run_id}

    applied: Dict[str, Any] = {}
    if apply:
        applied = apply_coaching_insights(user_id, insights)

    conn = _connect()
    try:
        conn.execute(
            """UPDATE ollama_coach_runs SET status='completed', insights_json=?, applied_json=? WHERE id=?""",
            (json.dumps(insights, ensure_ascii=False), json.dumps(applied, ensure_ascii=False), run_id),
        )
        conn.execute(
            """INSERT INTO ollama_coach_prefs (user_id, enabled, last_run_at, last_insights_json, updated_at)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_run_at=excluded.last_run_at,
                last_insights_json=excluded.last_insights_json,
                updated_at=excluded.updated_at""",
            (str(user_id), _utc(), json.dumps(insights, ensure_ascii=False), _utc()),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "run_id": run_id,
        "feedback_count": len(feedback),
        "insights": insights,
        "applied": applied,
    }


def apply_coaching_insights(user_id: str, insights: Dict[str, Any]) -> Dict[str, Any]:
    """Apply coach suggestions to Ollama-facing memory and neural datasets."""
    from backend.app.core.user_memory import PERSONA_PRESETS, add_fact, update_profile

    applied: Dict[str, Any] = {
        "persona_updated": False,
        "facts_added": 0,
        "training_pairs_added": 0,
        "query_healings_added": 0,
        "communication_notes_updated": False,
    }

    persona = (insights.get("persona_suggestion") or "keep").strip().lower()
    if persona in PERSONA_PRESETS and persona != "keep":
        update_profile(user_id, persona=persona)
        applied["persona_updated"] = True
        applied["persona"] = persona

    notes_add = sanitize_coach_style_text(
        (insights.get("communication_notes_addition") or "").strip(), max_len=300
    )
    if notes_add:
        from backend.app.core.user_memory import get_or_create_profile

        prof = get_or_create_profile(user_id)
        existing = (prof.get("communication_notes") or "").strip()
        merged = f"{existing}\n{notes_add}".strip() if existing else notes_add
        merged = sanitize_coach_style_text(merged, max_len=1200)
        if merged and len(merged) <= 1200:
            update_profile(user_id, communication_notes=merged[:1200])
            applied["communication_notes_updated"] = True

    for fact in (insights.get("suggested_facts") or [])[:4]:
        if not isinstance(fact, dict):
            continue
        key = re.sub(r"[^\w]", "_", (fact.get("key") or "").strip().lower())[:40]
        val = sanitize_coach_style_text((fact.get("value") or "").strip(), max_len=200)
        if key and val and is_allowed_coach_fact_key(key):
            add_fact(user_id, key, val, source="coach", confidence=0.88)
            applied["facts_added"] += 1

    # Training pairs: NEVER from Gemini output — only from verified user thumbs-up in DB.
    try:
        from backend.app.core.neural_finetuning import collect_pairs_from_feedback

        added = collect_pairs_from_feedback(str(user_id), limit=50)
        applied["training_pairs_added"] = added
    except Exception as exc:
        applied["training_pairs_error"] = str(exc)[:120]

    try:
        from backend.app.core.adaptive_learning import teach_query_expansion

        for heal in (insights.get("query_healings") or [])[:3]:
            if not isinstance(heal, dict):
                continue
            mode = (heal.get("mode") or "knowledge_base").strip()
            qn = (heal.get("query_norm") or heal.get("query") or "").strip()
            exp = sanitize_coach_style_text((heal.get("expansion") or "").strip(), max_len=200)
            if qn and exp and not _LEGAL_SUBSTANCE_RE.search(exp):
                teach_query_expansion(str(user_id), mode, qn, exp, success_delta=2)
                applied["query_healings_added"] += 1
    except Exception as exc:
        applied["query_healings_error"] = str(exc)[:120]

    try:
        from backend.app.core.user_preferences import update_preferences_from_coach

        pref_n = update_preferences_from_coach(user_id, insights.get("preference_updates") or {})
        applied["preferences_updated"] = pref_n
    except Exception as exc:
        applied["preferences_error"] = str(exc)[:120]

    return applied


def run_coaching_cycle(
    user_id: str,
    *,
    membership: str = "Free",
    auto_train: bool = True,
) -> Dict[str, Any]:
    """
    Full Settings cycle: analyze feedback → apply insights → collect neural pairs → optional train.
    """
    analysis = analyze_feedback(user_id, membership=membership, apply=True)
    if not analysis.get("ok"):
        return analysis

    collect_result: Dict[str, Any] = {}
    train_result: Optional[Dict[str, Any]] = None
    export_result: Dict[str, Any] = {}
    try:
        from backend.app.core.neural_finetuning import (
            collect_pairs_from_feedback,
            maybe_auto_train,
        )

        added = collect_pairs_from_feedback(str(user_id), limit=500)
        collect_result = {"pairs_added": added}
        if auto_train:
            train_result = maybe_auto_train(str(user_id))
    except Exception as exc:
        collect_result = {"error": str(exc)[:120]}

    try:
        export_result = export_and_optionally_create_modelfile(str(user_id))
    except Exception as exc:
        export_result = {"ok": False, "error": str(exc)[:200]}

    return {
        **analysis,
        "collect": collect_result,
        "training": train_result,
        "ollama_export": export_result,
        "message": (
            "Coaching cycle complete. Ollama memory, neural training, and Modelfile export updated."
        ),
    }


def export_and_optionally_create_modelfile(user_id: str) -> Dict[str, Any]:
    """Export Modelfile + JSONL and auto-run ollama create when enabled."""
    from backend.app.core.improvement_automation import auto_export_and_create_ollama

    return auto_export_and_create_ollama(str(user_id), force=True)
