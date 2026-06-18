"""
Phase 4 — Research query logging, expansion, and feedback loop.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.saas_schema import ensure_saas_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


_ABSTRACT_TO_STATUTORY = [
    (
        re.compile(r"\b(vendor|money|run away|cheat|fraud)\b", re.I),
        [
            "Cheating Section 318 BNS",
            "Criminal Breach of Trust Section 316 BNS",
            "Breach of Contract Section 73 Indian Contract Act remedies",
        ],
    ),
    (
        re.compile(r"\b(contract|broken|breach)\b", re.I),
        [
            "Section 73 Indian Contract Act damages",
            "Section 74 liquidated damages",
            "Specific Relief Act Section 10",
        ],
    ),
    (
        re.compile(r"\b(bail|arrest|police)\b", re.I),
        [
            "Section 437 CrPC BNSS bail non-bailable",
            "Section 483 BNSS bail sessions",
            "Anticipatory bail Section 438",
        ],
    ),
    (
        re.compile(r"\b(murder|kill|death|homicide)\b", re.I),
        [
            "Section 103 BNS murder",
            "Section 105 culpable homicide",
            "Exception private defence Section 34 BNS",
        ],
    ),
]


def expand_research_query(
    raw: str,
    user_id: str = "",
) -> Dict[str, Any]:
    """Expand conversational queries into statutory search terms."""
    q = (raw or "").strip()
    expanded: List[str] = [q]
    try:
        from backend.app.core.adaptive_learning import apply_learned_query_expansion

        learned = apply_learned_query_expansion(user_id, "web_search", q)
        if learned and learned != q and learned not in expanded:
            expanded.insert(0, learned)
    except Exception:
        pass
    for pat, terms in _ABSTRACT_TO_STATUTORY:
        if pat.search(q):
            for t in terms:
                if t not in expanded:
                    expanded.append(t)
    if len(expanded) == 1 and len(q.split()) <= 12:
        expanded.append(f"{q} India statute section judgment")
    return {
        "raw_search_term": q,
        "expanded_queries": expanded[:8],
        "confidence": 0.7 if len(expanded) > 1 else 0.45,
    }


def log_research_query(
    user_id: str,
    raw_search_term: str,
    *,
    selected_mode: str = "KNOWLEDGE_BASE",
    matter_id: str = "",
    retrieval_confidence: float = 0.0,
) -> Dict[str, Any]:
    ensure_saas_schema()
    expansion = expand_research_query(raw_search_term, user_id)
    qid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO research_queries
        (query_id, user_id, matter_id, raw_search_term, expanded_search_terms,
         selected_mode, retrieval_confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            qid,
            str(user_id),
            matter_id,
            raw_search_term.strip(),
            json.dumps(expansion["expanded_queries"]),
            selected_mode.upper(),
            retrieval_confidence,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "query_id": qid,
        **expansion,
        "selected_mode": selected_mode,
    }


def record_research_feedback(
    user_id: str,
    query_id: str,
    signal: int,
    *,
    rephrased_query: str = "",
) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    conn.execute(
        "UPDATE research_queries SET feedback_signal = ? WHERE query_id = ? AND user_id = ?",
        (signal, query_id, str(user_id)),
    )
    if rephrased_query.strip() and signal != 0:
        row = conn.execute(
            "SELECT raw_search_term FROM research_queries WHERE query_id = ?",
            (query_id,),
        ).fetchone()
        if row:
            try:
                from backend.app.core.adaptive_learning import record_implicit_correction

                record_implicit_correction(
                    user_id,
                    "web_search",
                    row[0],
                    rephrased_query.strip(),
                )  # prev query -> correction
            except Exception:
                pass
    conn.commit()
    conn.close()
    return {"recorded": True, "query_id": query_id}


def list_research_history(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT query_id, raw_search_term, expanded_search_terms, selected_mode,
               retrieval_confidence, feedback_signal, created_at
        FROM research_queries WHERE user_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (str(user_id), limit),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            exp = json.loads(r[2] or "[]")
        except json.JSONDecodeError:
            exp = []
        out.append(
            {
                "query_id": r[0],
                "raw_search_term": r[1],
                "expanded_queries": exp,
                "selected_mode": r[3],
                "retrieval_confidence": r[4],
                "feedback_signal": r[5],
                "created_at": r[6],
            }
        )
    return out


def similar_case_clusters(user_id: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Group recent research queries by statute/section for Analytics cluster map."""
    ensure_saas_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT raw_search_term, selected_mode FROM research_queries
        WHERE user_id = ? ORDER BY created_at DESC LIMIT 120
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()

    clusters: Dict[str, Dict[str, Any]] = {}
    for raw, mode in rows:
        text = raw or ""
        keys: List[str] = []
        for m in re.finditer(r"\b(?:IPC|BNS|BNSS|Section)\s+(\d{1,4}[a-z]?)\b", text, re.I):
            keys.append(f"Section {m.group(1).upper()}")
        if not keys and len(text.split()) >= 3:
            keys.append(text[:48].strip())
        for key in keys[:2]:
            bucket = clusters.setdefault(
                key,
                {"label": key, "count": 0, "modes": set(), "sample_query": text[:80]},
            )
            bucket["count"] += 1
            bucket["modes"].add(mode or "UNKNOWN")

    ranked = sorted(clusters.values(), key=lambda x: x["count"], reverse=True)
    out: List[Dict[str, Any]] = []
    for item in ranked[:limit]:
        out.append({
            "label": item["label"],
            "count": item["count"],
            "modes": sorted(item["modes"]),
            "sample_query": item["sample_query"],
        })
    return out
