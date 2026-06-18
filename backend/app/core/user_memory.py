"""
Long-term user memory — preferences, facts, thread summaries.

Unlike GPT/Gemini (trained on billions of tokens + RLHF), we improve via:
  1) Adaptive learning (retrieval + query expansion from feedback)
  2) Persistent memory (this module) injected into every chat turn
  3) Thread summaries for multi-session continuity

Does NOT simulate human emotions — uses professional, warm legal-assistant tone.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.database import get_sqlite_path
from backend.app.core.legacy_db import connect_app_db, use_postgres_legacy

DB_PATH = get_sqlite_path()

_TRANSIENT_RE = re.compile(
    r"\b(today|tonight|this notice|this email|for now|just for|temporary|"
    r"quick question|one-off)\b",
    re.I,
)
_MIN_AUTO_CONFIDENCE = 0.65

PERSONA_PRESETS = {
    "professional": (
        "You are LegalEase, a precise Indian legal research assistant. "
        "Be clear, cite sources, and stay neutral. No fluff."
    ),
    "warm": (
        "You are LegalEase, a supportive Indian legal assistant. "
        "Be professional but approachable — acknowledge the user's situation, "
        "then give accurate, structured legal guidance. Never claim to be human."
    ),
    "concise": (
        "You are LegalEase. Answer in short, direct paragraphs. "
        "Lead with the rule, then application. Indian law context."
    ),
    "detailed": (
        "You are LegalEase. Provide thorough explanations with sections, "
        "exceptions, and practical next steps. Indian statutes (IPC/BNS/CrPC/IT Act)."
    ),
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    return connect_app_db()


def ensure_user_memory_schema() -> None:
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema

        ensure_pg_core_schema()
        return
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        persona TEXT DEFAULT 'warm',
        practice_area TEXT DEFAULT '',
        preferred_language TEXT DEFAULT 'English',
        communication_notes TEXT DEFAULT '',
        memory_enabled INTEGER DEFAULT 1,
        updated_at TEXT NOT NULL
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS user_facts (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        fact_key TEXT NOT NULL,
        fact_value TEXT NOT NULL,
        source TEXT DEFAULT 'auto',
        confidence REAL DEFAULT 1.0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )"""
    )
    c.execute(
        """CREATE INDEX IF NOT EXISTS idx_user_facts_uid ON user_facts(user_id)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS thread_summaries (
        thread_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        summary TEXT NOT NULL,
        topics TEXT DEFAULT '[]',
        last_query TEXT DEFAULT '',
        turn_count INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL
    )"""
    )
    conn.commit()
    conn.close()


def get_or_create_profile(user_id: str) -> Dict[str, Any]:
    ensure_user_memory_schema()
    uid = str(user_id)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT persona, practice_area, preferred_language, communication_notes, memory_enabled FROM user_profiles WHERE user_id=?",
            (uid,),
        ).fetchone()
        if row:
            return {
                "user_id": uid,
                "persona": row[0],
                "practice_area": row[1],
                "preferred_language": row[2],
                "communication_notes": row[3],
                "memory_enabled": bool(row[4]),
            }
        conn.execute(
            """INSERT INTO user_profiles (user_id, persona, updated_at)
            VALUES (?, 'warm', ?)""",
            (uid, _utc()),
        )
        conn.commit()
        return get_or_create_profile(uid)
    finally:
        conn.close()


def update_profile(user_id: str, **fields) -> Dict[str, Any]:
    ensure_user_memory_schema()
    prof = get_or_create_profile(user_id)
    allowed = {"persona", "practice_area", "preferred_language", "communication_notes", "memory_enabled"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return prof
    conn = _connect()
    try:
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [_utc(), str(user_id)]
        conn.execute(
            f"UPDATE user_profiles SET {sets}, updated_at=? WHERE user_id=?",
            vals,
        )
        conn.commit()
    finally:
        conn.close()
    return get_or_create_profile(user_id)


def add_fact(
    user_id: str,
    key: str,
    value: str,
    source: str = "user",
    confidence: float = 1.0,
) -> Dict[str, Any]:
    ensure_user_memory_schema()
    if source == "auto" and _is_transient_fact(value):
        return {"skipped": True, "reason": "transient"}
    if source == "auto" and confidence < _MIN_AUTO_CONFIDENCE:
        return {"skipped": True, "reason": "low_confidence"}

    uid, k = str(user_id), key[:80]
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT id, source FROM user_facts WHERE user_id=? AND fact_key=?",
            (uid, k),
        ).fetchone()
        if existing and existing[1] == "user" and source == "auto":
            return {"id": existing[0], "key": k, "value": value, "skipped": True}

        if existing:
            fid = existing[0]
            conn.execute(
                """UPDATE user_facts SET fact_value=?, source=?, confidence=?, updated_at=?
                WHERE id=?""",
                (value[:500], source, float(confidence), _utc(), fid),
            )
        else:
            fid = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO user_facts
                (id, user_id, fact_key, fact_value, source, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (fid, uid, k, value[:500], source, float(confidence), _utc(), _utc()),
            )
        conn.commit()
    finally:
        conn.close()
    return {"id": fid, "key": k, "value": value}


def delete_fact(user_id: str, fact_id: str) -> bool:
    ensure_user_memory_schema()
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM user_facts WHERE user_id=? AND id=?",
            (str(user_id), fact_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_fact(user_id: str, fact_id: str, key: str, value: str) -> bool:
    ensure_user_memory_schema()
    conn = _connect()
    try:
        cur = conn.execute(
            """UPDATE user_facts SET fact_key=?, fact_value=?, source='user',
            confidence=1.0, updated_at=? WHERE user_id=? AND id=?""",
            (key[:80], value[:500], _utc(), str(user_id), fact_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_facts(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_user_memory_schema()
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT id, fact_key, fact_value, source, confidence FROM user_facts
            WHERE user_id=? ORDER BY source DESC, updated_at DESC LIMIT ?""",
            (str(user_id), limit),
        ).fetchall()
        return [
            {"id": r[0], "key": r[1], "value": r[2], "source": r[3], "confidence": r[4]}
            for r in rows
        ]
    finally:
        conn.close()


def _is_transient_fact(value: str) -> bool:
    return bool(_TRANSIENT_RE.search(value or ""))


def update_thread_summary(
    user_id: str,
    thread_id: str,
    last_query: str,
    last_answer: str,
    history: Optional[List[Dict]] = None,
) -> None:
    """Rolling summary — only from user queries + topics, not hallucinated answers."""
    if not thread_id:
        return
    if not _answer_safe_for_summary(last_answer):
        last_answer = ""
    ensure_user_memory_schema()
    prev = get_thread_summary(thread_id)
    turn = (prev.get("turn_count") or 0) + 1
    summary = _build_summary(prev.get("summary", ""), last_query, last_answer, history)
    from backend.app.core.prompt_budget import budget_summary

    summary = budget_summary(summary)
    topics = _extract_topics(last_query, last_answer)
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO thread_summaries
            (thread_id, user_id, summary, topics, last_query, turn_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
            summary=excluded.summary, topics=excluded.topics, last_query=excluded.last_query,
            turn_count=excluded.turn_count, updated_at=excluded.updated_at""",
            (
                thread_id,
                str(user_id),
                summary[:4000],
                json.dumps(topics[:12]),
                last_query[:500],
                turn,
                _utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_thread_summary(thread_id: str) -> Dict[str, Any]:
    ensure_user_memory_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT summary, topics, last_query, turn_count FROM thread_summaries WHERE thread_id=?",
            (thread_id,),
        ).fetchone()
        if not row:
            return {}
        return {
            "summary": row[0],
            "topics": json.loads(row[1] or "[]"),
            "last_query": row[2],
            "turn_count": row[3],
        }
    finally:
        conn.close()


def extract_facts_from_message(user_id: str, message: str) -> List[Dict[str, str]]:
    """Lightweight fact extraction from user text (no LLM required)."""
    added = []
    m = message or ""
    patterns = [
        (r"\b(?:i am|i'm)\s+(?:a|an)\s+([a-z\s]{3,40}?)(?:lawyer|advocate|student|paralegal)", "role"),
        (r"\bmy client(?:'s)?\s+name\s+is\s+([A-Za-z][A-Za-z\s]{2,40})", "client_name"),
        (r"\b(?:focus on|specializ(?:e|ing) in)\s+([a-z\s]{3,50})", "practice_focus"),
        (r"\b(?:prefer|want)\s+(brief|short|detailed|simple)\s+answers?", "answer_style"),
    ]
    if _TRANSIENT_RE.search(m):
        return added

    for pat, key in patterns:
        match = re.search(pat, m, re.I)
        if match:
            val = match.group(1).strip()
            if len(val) < 4 or _is_transient_fact(val):
                continue
            out = add_fact(user_id, key, val, source="auto", confidence=0.75)
            if not out.get("skipped"):
                added.append({"key": key, "value": val})
    return added


def build_memory_context(
    user_id: str,
    thread_id: Optional[str] = None,
    mode: str = "knowledge_base",
    query: str = "",
) -> Dict[str, Any]:
    """
    Bundle injected into chat/RAG prompts.
    """
    prof = get_or_create_profile(user_id)
    if not prof.get("memory_enabled", True):
        return {"persona_prompt": PERSONA_PRESETS["professional"], "memory_block": "", "enabled": False}

    from backend.app.core.prompt_budget import budget_memory_block, budget_summary

    persona = PERSONA_PRESETS.get(prof.get("persona", "warm"), PERSONA_PRESETS["warm"])
    try:
        from backend.app.core.gemini_ollama_coach import is_allowed_coach_fact_key

        facts = [
            f
            for f in list_facts(user_id, limit=20)
            if f.get("source") == "user"
            or (
                f.get("source") == "coach"
                and is_allowed_coach_fact_key(f.get("key", ""))
            )
            or (
                f.get("source") not in ("coach",)
                and (f.get("confidence") or 0) >= 0.7
            )
        ]
    except Exception:
        facts = [
            f
            for f in list_facts(user_id, limit=20)
            if f.get("source") == "user" or (f.get("confidence") or 0) >= 0.7
        ]
    thread = get_thread_summary(thread_id) if thread_id else {}

    lines = []
    if prof.get("practice_area"):
        lines.append(f"User practice area: {prof['practice_area']}")
    if prof.get("communication_notes"):
        lines.append(f"User notes: {prof['communication_notes']}")
    try:
        from backend.app.core.gemini_ollama_coach import get_coach_memory_block

        coach_block = get_coach_memory_block(user_id, limit=6)
        if coach_block:
            lines.append(coach_block)
    except Exception:
        pass
    for f in facts[:8]:
        lines.append(f"Remember: {f['key']} = {f['value']}")
    if thread.get("topics"):
        lines.append(f"Active topics: {', '.join(thread['topics'][:6])}")
    if thread.get("summary"):
        lines.append(f"Thread context: {budget_summary(thread['summary'])}")

    past_block = ""
    try:
        from backend.app.core.chat_conversation_rag import (
            format_past_chat_context,
            search_past_chats,
            should_search_past_chats,
        )

        search_q = (query or thread.get("last_query") or "").strip()
        if thread_id and search_q and should_search_past_chats(search_q):
            hits = search_past_chats(user_id, search_q, k=2)
            past_block = format_past_chat_context(hits)
    except Exception:
        pass

    memory_block = budget_memory_block("\n".join(lines))
    return {
        "persona_prompt": persona,
        "memory_block": memory_block,
        "past_chat_block": past_block,
        "enabled": True,
        "persona": prof.get("persona"),
        "fact_count": len(facts),
        "thread_turns": thread.get("turn_count", 0),
    }


def _answer_safe_for_summary(answer: str) -> bool:
    if not answer or len(answer.strip()) < 50:
        return False
    tl = answer.lower()
    if any(
        x in tl
        for x in (
            "couldn't find",
            "could not find",
            "not found in",
            "i could not generate",
        )
    ):
        return False
    return True


def _build_summary(
    prev: str,
    query: str,
    answer: str,
    history: Optional[List[Dict]],
) -> str:
    """User queries + topics only — avoids baking hallucinations into summary."""
    parts = []
    if prev:
        parts.append(prev[:800])
    parts.append(f"User asked: {query[:200]}")
    topics = _extract_topics(query, answer or "")
    if topics:
        parts.append(f"Topics: {', '.join(topics)}")
    if history:
        for h in history[-3:]:
            if h.get("role") == "user":
                parts.append(f"Prior Q: {h.get('content', '')[:100]}")
    combined = " | ".join(parts)
    return combined[-2000:]


def _extract_topics(query: str, answer: str) -> List[str]:
    topics = []
    for text in (query, answer):
        for m in re.finditer(r"\b(?:IPC|BNS|CrPC|IT Act)\s*(?:Section\s*)?(\d{1,4}[a-z]?)\b", text, re.I):
            topics.append(f"{m.group(0)[:30]}")
        for m in re.finditer(r"\b(murder|bail|cheating|rape|theft|contract)\b", text, re.I):
            topics.append(m.group(1).lower())
    return list(dict.fromkeys(topics))[:12]


def remember_kb_success(
    user_id: str,
    query: str,
    answer: str,
    *,
    thread_id: str = "",
) -> None:
    """Promote successful KB answers into thread memory and durable facts."""
    if not query or not answer or len(answer) < 60:
        return
    prof = get_or_create_profile(user_id)
    if not prof.get("memory_enabled", True):
        return

    topics = _extract_topics(query, answer)
    if thread_id:
        update_thread_summary(thread_id, user_id, query, answer)

    for topic in topics[:3]:
        if re.match(r"^(ipc|bns|crpc|bnss|bsa|it act)", topic, re.I):
            add_fact(
                user_id,
                f"recent_topic_{topic[:20].lower().replace(' ', '_')}",
                topic,
                source="kb_learn",
                confidence=0.72,
            )

    if re.search(r"\b(ipc|bns|crpc|bnss)\b", query, re.I) and len(answer) > 120:
        q_short = query[:80].strip()
        add_fact(
            user_id,
            f"kb_answer_{hash(q_short) % 100000}",
            f"Q: {q_short} → {answer[:200]}",
            source="kb_learn",
            confidence=0.68,
        )
