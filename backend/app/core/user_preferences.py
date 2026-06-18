"""
Persistent user preference profile — depth, structure, citation, follow-up style.

Updated from:
  - explicit user facts (user_memory)
  - thumbs-up/down signals (human_training)
  - Gemini coach preference_updates (style-only, guarded)
  - in-chat context learning (session hints merged at end of turn)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_PROFILE: Dict[str, Any] = {
    "learner_mode": False,
    "depth": "standard",  # quick | standard | detailed | comparison
    "structure": "sections",  # sections | bullets | narrative | mixed
    "citation_style": "inline",  # inline | footnote | minimal
    "tone": "professional",
    "prefer_bullets": 0.5,
    "prefer_concise": 0.5,
    "prefer_headings": 0.7,
    "detail_level": 0.5,
    "follow_up_style": "specific",  # specific | broad | minimal
    "answer_style": "balanced",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    from backend.app.core.database import connect_data_db

    return connect_data_db()


def ensure_preferences_schema() -> None:
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL DEFAULT '{}',
            session_hints_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_user_prefs_updated
            ON user_preferences(updated_at DESC)"""
        )
        conn.commit()
    finally:
        conn.close()


def _merge_profile(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (updates or {}).items():
        if v is None:
            continue
        if k in DEFAULT_PROFILE:
            if isinstance(DEFAULT_PROFILE[k], bool):
                out[k] = bool(v)
            elif isinstance(DEFAULT_PROFILE[k], float) and isinstance(v, (int, float)):
                out[k] = max(0.0, min(1.0, float(v)))
            else:
                out[k] = v
    return out


def get_preference_profile(user_id: str) -> Dict[str, Any]:
    ensure_preferences_schema()
    uid = str(user_id)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT profile_json, session_hints_json FROM user_preferences WHERE user_id=?",
            (uid,),
        ).fetchone()
        profile = dict(DEFAULT_PROFILE)
        hints: Dict[str, Any] = {}
        if row:
            try:
                profile = _merge_profile(profile, json.loads(row[0] or "{}"))
            except Exception:
                pass
            try:
                hints = json.loads(row[1] or "{}")
            except Exception:
                hints = {}
        return {"profile": profile, "session_hints": hints}
    finally:
        conn.close()


def save_preference_profile(user_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    ensure_preferences_schema()
    uid = str(user_id)
    merged = _merge_profile(DEFAULT_PROFILE, profile)
    import sqlite3
    import time

    last_exc: Exception | None = None
    for attempt in range(5):
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO user_preferences (user_id, profile_json, session_hints_json, updated_at)
                VALUES (?, ?, COALESCE((SELECT session_hints_json FROM user_preferences WHERE user_id=?), '{}'), ?)
                ON CONFLICT(user_id) DO UPDATE SET profile_json=excluded.profile_json, updated_at=excluded.updated_at""",
                (uid, json.dumps(merged, ensure_ascii=False), uid, _utc()),
            )
            conn.commit()
            return merged
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if "locked" not in str(exc).lower() or attempt >= 4:
                raise
            time.sleep(0.05 * (attempt + 1))
        finally:
            conn.close()
    if last_exc:
        raise last_exc
    return merged


def update_preferences_from_coach(user_id: str, updates: Dict[str, Any]) -> int:
    """Apply guarded coach preference_updates (style only)."""
    from backend.app.core.coach_guards import is_allowed_coach_fact_key, sanitize_coach_style_text

    if not updates:
        return 0
    current = get_preference_profile(user_id)["profile"]
    applied = 0
    patch: Dict[str, Any] = {}
    for k, v in updates.items():
        if not is_allowed_coach_fact_key(str(k)):
            continue
        if isinstance(v, str):
            sv = sanitize_coach_style_text(v, max_len=80)
            if sv:
                patch[str(k)] = sv
                applied += 1
        elif isinstance(v, (int, float)):
            patch[str(k)] = max(0.0, min(1.0, float(v)))
            applied += 1
    if patch:
        save_preference_profile(user_id, _merge_profile(current, patch))
    return applied


def record_session_hint(user_id: str, hint_key: str, hint_value: Any) -> None:
    """In-chat learning — ephemeral hints merged into next turns (cleared weekly)."""
    ensure_preferences_schema()
    uid = str(user_id)
    data = get_preference_profile(uid)
    hints = dict(data.get("session_hints") or {})
    hints[str(hint_key)[:40]] = hint_value
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO user_preferences (user_id, profile_json, session_hints_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET session_hints_json=excluded.session_hints_json, updated_at=excluded.updated_at""",
            (
                uid,
                json.dumps(data["profile"], ensure_ascii=False),
                json.dumps(hints, ensure_ascii=False),
                _utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def learn_from_feedback_signal(
    user_id: str,
    signal: str,
    *,
    mode: str = "",
    query: str = "",
    answer_preview: str = "",
) -> Dict[str, Any]:
    """
    Context learning from human labels — adjust preference weights without legal substance.
    """
    data = get_preference_profile(user_id)
    profile = dict(data["profile"])
    q = (query or "").lower()
    a = (answer_preview or "").lower()

    if signal in ("thumbs_up", "helpful", "verbal_positive", "copy", "export_docx", "export_pdf", "save_to_matter"):
        if any(w in q for w in ("detail", "elaborate", "comprehensive", "in depth")):
            profile["detail_level"] = min(1.0, float(profile.get("detail_level", 0.5)) + 0.08)
            profile["depth"] = "detailed"
        if any(w in q for w in ("brief", "short", "concise", "quick")):
            profile["prefer_concise"] = min(1.0, float(profile.get("prefer_concise", 0.5)) + 0.1)
            profile["depth"] = "quick"
        if "compare" in q or "difference" in q:
            profile["depth"] = "comparison"
        if a.count("\n- ") >= 3 or a.count("•") >= 3:
            profile["prefer_bullets"] = min(1.0, float(profile.get("prefer_bullets", 0.5)) + 0.06)
        if a.count("##") >= 2 or a.count("**") >= 4:
            profile["prefer_headings"] = min(1.0, float(profile.get("prefer_headings", 0.5)) + 0.06)
    elif signal in ("thumbs_down", "verbal_negative"):
        if any(w in q for w in ("too long", "verbose", "lengthy")):
            profile["prefer_concise"] = min(1.0, float(profile.get("prefer_concise", 0.5)) + 0.12)
        if any(w in q for w in ("more detail", "expand", "deeper")):
            profile["detail_level"] = min(1.0, float(profile.get("detail_level", 0.5)) + 0.1)

    save_preference_profile(user_id, profile)
    return profile


def build_preference_prompt_block(user_id: str, *, kb_depth: str = "") -> str:
    """Prompt block for Ollama synthesis — style only."""
    data = get_preference_profile(user_id)
    p = data["profile"]
    hints = data.get("session_hints") or {}
    depth = kb_depth or p.get("depth") or "standard"
    lines = [
        "USER RESPONSE PREFERENCES (format only — never override document facts):",
        f"- Depth: {depth}",
        f"- Structure: {p.get('structure', 'sections')}",
        f"- Citation style: {p.get('citation_style', 'inline')}",
        f"- Tone: {p.get('tone', 'professional')}",
    ]
    if float(p.get("prefer_bullets", 0.5)) >= 0.65:
        lines.append("- Prefer bullet points where appropriate.")
    if float(p.get("prefer_concise", 0.5)) >= 0.65:
        lines.append("- Prefer concise answers unless user asks for detail.")
    if float(p.get("prefer_headings", 0.5)) >= 0.65:
        lines.append("- Use clear section headings.")
    if float(p.get("detail_level", 0.5)) >= 0.7:
        lines.append("- User prefers detailed explanations when documents support it.")
    if hints.get("last_follow_up_intent"):
        lines.append(f"- Recent follow-up intent: {hints['last_follow_up_intent']}.")
    return "\n".join(lines)[:900]


def get_learner_mode(user_id: str) -> bool:
    return bool(get_preference_profile(user_id).get("profile", {}).get("learner_mode"))


def set_learner_mode(user_id: str, enabled: bool) -> Dict[str, Any]:
    prof = get_preference_profile(user_id)["profile"]
    prof["learner_mode"] = bool(enabled)
    save_preference_profile(user_id, prof)
    return prof
