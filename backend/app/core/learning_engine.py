"""
Unified learning engine — GPT/Gemini-style rapid adaptation for LegalEase.

Combines:
  1) Answer memory — instant replay of proven Q→A pairs (works when FAISS/embeddings fail)
  2) Adaptive learning — query expansion, chunk boosts, thresholds
  3) Neural fine-tuning — embedding weight updates from feedback
  4) User memory — persona, facts, thread context
  5) KB rescue chain — multi-layer recovery before NOT_FOUND

Unlike cloud LLM training, we improve retrieval + memory + rescue paths in real time
from every successful turn — no re-index required for answer memory hits.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENABLED = os.getenv("LEARNING_ENGINE_ENABLED", "1").lower() in {"1", "true", "yes"}
MEMORY_ENABLED = os.getenv("RAPID_LEARN_MEMORY", "1").lower() in {"1", "true", "yes"}
MEMORY_MIN_CONFIDENCE = float(os.getenv("RAPID_LEARN_MEMORY_MIN_CONF", "0.55"))
MEMORY_FUZZY_THRESHOLD = float(os.getenv("RAPID_LEARN_FUZZY_MATCH", "0.72"))
MEMORY_STRICT_THRESHOLD = float(os.getenv("RAPID_LEARN_STRICT_MATCH", "0.94"))
OPEN_LAW_MEMORY_REPLAY = os.getenv("OPEN_LAW_MEMORY_REPLAY", "exact").strip().lower()
MIN_ANSWER_LEN = 60


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    from backend.app.core.legacy_db import connect_app_db

    return connect_app_db()


def _normalize(q: str) -> str:
    from backend.app.core.adaptive_learning import normalize_query

    return normalize_query(q)


def _token_set(q: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (q or "").lower()) if len(t) >= 3}


def _section_numbers(q: str) -> set:
    try:
        from kb_query_types import primary_sections_from_query

        return set(primary_sections_from_query(q or ""))
    except Exception:
        return set()


def _sections_in_answer(answer: str) -> set:
    """Section numbers cited in a stored/generated answer."""
    al = (answer or "").lower()
    found: set = set()
    for pat in (
        r"#+\s*(?:ipc|bns)\s+section\s+(\d{1,4}[a-z]?)",
        r"\bsection\s+(\d{1,4}[a-z]?)\b",
        r"\bipc\s+(\d{1,4}[a-z]?)\b",
    ):
        found.update(m.group(1).lower() for m in re.finditer(pat, al, re.I))
    return found


def _answer_is_criminal_statute(answer: str) -> bool:
    al = (answer or "").lower()
    return bool(
        re.search(r"\b(?:ipc|bns)\s+section\s+\d{1,4}", al)
        or re.search(r"##\s*(?:ipc|bns)\s+section", al)
    )


def _query_is_contract_topic(query: str) -> bool:
    try:
        from document_classifier import is_contract_topic_query

        return is_contract_topic_query(query)
    except ImportError:
        return False


def _answer_matches_query_sections(query: str, answer: str) -> bool:
    """Reject memory replay when answer headlines a different IPC section."""
    qs = _section_numbers(query)
    if not qs:
        if _query_is_contract_topic(query) and _answer_is_criminal_statute(answer):
            return False
        return True
    al = (answer or "").lower()
    if re.search(r"\bhas been replaced by\b|\breplaced by the\b|\bnew criminal law framework\b", al):
        if not any(re.search(rf"\b(?:section\s+{re.escape(s)}|ipc\s+{re.escape(s)})\b", al) for s in qs):
            return False
    ans_secs = _sections_in_answer(answer)
    if not ans_secs:
        return False
    if qs & ans_secs:
        return True
    return False


def _answer_matches_case_needles(query: str, answer: str) -> bool:
    """Reject memory when a case-specific query does not match the stored answer caption."""
    try:
        from kb_query_types import is_case_query, is_document_fact_query
        from backend.app.core.case_entity_resolver import (
            extract_case_needles,
            is_case_style_query,
            segment_matches_case_needles,
        )

        if not (is_case_query(query) or is_case_style_query(query) or is_document_fact_query(query)):
            return True
        needles = extract_case_needles(query)
        if not needles:
            return True
        return segment_matches_case_needles((answer or "").lower(), needles)
    except Exception:
        return True


def _sections_compatible(query_a: str, query_b: str, answer: str = "") -> bool:
    """Prevent answer memory from replaying IPC 307 when user asked about 302."""
    sa = _section_numbers(query_a)
    sb = _section_numbers(query_b)
    if sa and sb:
        return bool(sa & sb)
    if sa and answer:
        return _answer_matches_query_sections(query_a, answer)
    return True


def _similarity(a: str, b: str, *, strict: bool = False) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if not _sections_compatible(a, b):
        return 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return seq
    jaccard = len(ta & tb) / max(len(ta | tb), 1)
    score = max(seq, jaccard * 0.95)
    if not strict:
        legal = {"ipc", "bns", "crpc", "bnss", "bsa", "murder", "section", "law", "replace", "replaced"}
        la, lb = ta & legal, tb & legal
        if la and lb and (la & lb):
            if not (_section_numbers(a) or _section_numbers(b)):
                score = max(score, 0.75 + 0.05 * len(la & lb))
        if a in b or b in a:
            score = max(score, 0.85)
    return score


def ensure_learning_engine_schema() -> None:
    from backend.app.core.legacy_db import use_postgres_legacy

    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema

        ensure_pg_core_schema()
        return
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS kb_answer_memory (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            query_norm TEXT NOT NULL,
            query TEXT NOT NULL,
            answer TEXT NOT NULL,
            source TEXT DEFAULT 'kb_success',
            confidence REAL DEFAULT 0.85,
            hit_count INTEGER DEFAULT 0,
            chunk_keys TEXT DEFAULT '[]',
            topics TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_kb_answer_mem_uid_qn
            ON kb_answer_memory(user_id, query_norm)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS kb_rescue_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            query TEXT NOT NULL,
            rescue_layer TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )"""
        )
        conn.commit()
    finally:
        conn.close()


def _log_rescue(user_id: str, query: str, layer: str, success: bool, detail: str = "") -> None:
    if not ENABLED:
        return
    ensure_learning_engine_schema()
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO kb_rescue_events (id, user_id, query, rescue_layer, success, detail, created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), str(user_id), query[:500], layer[:40], 1 if success else 0, detail[:300], _utc()),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("[LEARN] KB rescue layer=%s success=%s query=%r", layer, success, query[:80])


def store_answer_memory(
    user_id: str,
    query: str,
    answer: str,
    *,
    source: str = "kb_success",
    confidence: float = 0.85,
    chunk_keys: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
) -> Optional[str]:
    """Persist a proven answer for instant replay — survives broken embeddings."""
    if not ENABLED or not MEMORY_ENABLED:
        return None
    q = (query or "").strip()
    a = (answer or "").strip()
    if len(q) < 8 or len(a) < MIN_ANSWER_LEN:
        return None
    if any(x in a.lower() for x in ("couldn't find", "could not find", "not found in", "not_found")):
        return None
    try:
        from backend.app.services.legal_query_parser import answer_satisfies_section_query

        if not answer_satisfies_section_query(q, a):
            return None
    except ImportError:
        pass
    if not _answer_matches_case_needles(q, a):
        return None
    try:
        from kb_query_types import is_case_query

        if is_case_query(q) and len(a) < 200:
            return None
    except ImportError:
        pass

    qn = _normalize(q)
    ensure_learning_engine_schema()
    conn = _connect()
    try:
        row = conn.execute(
            """SELECT id, confidence, hit_count FROM kb_answer_memory
            WHERE user_id=? AND query_norm=? LIMIT 1""",
            (str(user_id), qn),
        ).fetchone()
        now = _utc()
        if row:
            new_conf = min(0.99, max(float(row[1]), confidence) + 0.02)
            conn.execute(
                """UPDATE kb_answer_memory SET answer=?, confidence=?, source=?, updated_at=?,
                chunk_keys=?, topics=?
                WHERE id=?""",
                (
                    a[:8000],
                    new_conf,
                    source[:40],
                    now,
                    json.dumps(chunk_keys or []),
                    json.dumps(topics or []),
                    row[0],
                ),
            )
            conn.commit()
            return row[0]

        pid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO kb_answer_memory
            (id, user_id, query_norm, query, answer, source, confidence, chunk_keys, topics, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid,
                str(user_id),
                qn,
                q[:2000],
                a[:8000],
                source[:40],
                float(confidence),
                json.dumps(chunk_keys or []),
                json.dumps(topics or []),
                now,
                now,
            ),
        )
        conn.commit()
        return pid
    finally:
        conn.close()


def lookup_answer_memory(
    user_id: str,
    query: str,
    *,
    strict: bool = False,
) -> Optional[Dict[str, Any]]:
    """Match stored successful answers — strict mode for Open Law (exact/near-exact only)."""
    if not ENABLED or not MEMORY_ENABLED:
        return None
    qn = _normalize(query)
    if not qn:
        return None

    ensure_learning_engine_schema()
    conn = _connect()
    try:
        exact = conn.execute(
            """SELECT id, query_norm, query, answer, confidence, source, hit_count
            FROM kb_answer_memory
            WHERE (user_id=? OR user_id='') AND query_norm=?
            ORDER BY confidence DESC, updated_at DESC LIMIT 1""",
            (str(user_id), qn),
        ).fetchone()
        if exact:
            rows = [exact]
        else:
            if strict:
                return None
            if OPEN_LAW_MEMORY_REPLAY in ("off", "0", "false"):
                return None
            rows = conn.execute(
                """SELECT id, query_norm, query, answer, confidence, source, hit_count
                FROM kb_answer_memory
                WHERE user_id=? OR user_id=''
                ORDER BY confidence DESC, hit_count DESC, updated_at DESC
                LIMIT 80""",
                (str(user_id),),
            ).fetchall()
    finally:
        conn.close()

    threshold = MEMORY_STRICT_THRESHOLD if strict else MEMORY_FUZZY_THRESHOLD
    min_conf = max(MEMORY_MIN_CONFIDENCE, 0.85 if strict else MEMORY_MIN_CONFIDENCE)

    best: Optional[Tuple[float, tuple]] = None
    for row in rows:
        stored_qn = row[1]
        answer = row[3]
        if _query_is_contract_topic(query) and _answer_is_criminal_statute(answer):
            continue
        if not _sections_compatible(qn, stored_qn, answer):
            continue
        if not _answer_matches_query_sections(query, answer):
            continue
        if not _answer_matches_case_needles(query, answer):
            continue
        sim = 1.0 if stored_qn == qn else _similarity(qn, stored_qn, strict=strict)
        if strict and stored_qn != qn and sim < MEMORY_STRICT_THRESHOLD:
            continue
        if not strict and stored_qn != qn and (qn in stored_qn or stored_qn in qn):
            if not _section_numbers(qn):
                sim = max(sim, 0.88)
        if sim >= threshold:
            score = sim * float(row[4])
            if best is None or score > best[0]:
                best = (score, row)

    if not best or best[0] < min_conf:
        return None

    _, row = best
    mem_id = row[0]
    conn = _connect()
    try:
        conn.execute(
            "UPDATE kb_answer_memory SET hit_count = hit_count + 1, updated_at=? WHERE id=?",
            (_utc(), mem_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "answer": row[3],
        "confidence": float(row[4]),
        "source": row[5],
        "memory_id": mem_id,
        "matched_query": row[2],
        "layer": "answer_memory",
    }


def prepare_kb_query(
    user_id: str,
    query: str,
    profile: Any,
) -> Tuple[str, Dict[str, Any]]:
    """
    Pre-retrieval enhancement — adaptive expansion + memory hints.
    Returns (effective_query, signals dict).
    """
    signals: Dict[str, Any] = {"original_query": query}
    if not ENABLED:
        return query, signals

    effective = query
    try:
        from backend.app.core.adaptive_learning import apply_learned_query_expansion

        expanded = apply_learned_query_expansion(
            user_id,
            "knowledge_base",
            query,
            profile.expanded_query if profile else "",
        )
        if expanded and len(expanded) > len(query) + 3:
            effective = expanded
            signals["adaptive_expansion"] = expanded
    except Exception:
        pass

    try:
        from kb_legal_query_rewrite import expand_law_replacement_queries, is_law_replacement_query

        if is_law_replacement_query(query):
            alts = expand_law_replacement_queries(query)
            if alts:
                signals["law_expansions"] = alts[:6]
                if len(alts[0]) > len(effective):
                    effective = alts[0]
    except Exception:
        pass

    mem = lookup_answer_memory(user_id, query)
    if mem and not _answer_matches_query_sections(query, mem.get("answer") or ""):
        mem = None
    if mem and not _sections_compatible(
        query, mem.get("matched_query") or mem.get("query") or "", mem.get("answer") or ""
    ):
        mem = None
    if mem:
        signals["memory_hint"] = mem.get("answer", "")[:400]
        signals["memory_confidence"] = mem.get("confidence", 0)

    return effective, signals


def _retry_retrieval(
    user_id: str,
    query: str,
    index_dir: Any,
    profile: Any,
    k: int = 12,
) -> List[Dict[str, Any]]:
    from rag import query_kb

    try:
        from backend.app.core.adaptive_learning import apply_chunk_boosts

        chunks = query_kb(query, k=k, index_dir=index_dir)
        return apply_chunk_boosts(user_id, "knowledge_base", chunks)
    except Exception:
        try:
            return query_kb(query, k=k, index_dir=index_dir)
        except Exception:
            return []


def _docstore_keyword_rescue(query: str, index_dir: Any) -> List[Dict[str, Any]]:
    try:
        from rag import _load_docstore_only
        from kb_legal_query_rewrite import keyword_fallback_from_vectorstore

        vs = _load_docstore_only(index_dir)
        if vs:
            return keyword_fallback_from_vectorstore(vs, query, top_k=10)
    except Exception:
        pass
    return []


def rescue_broken_kb(
    user_id: str,
    query: str,
    *,
    history: Optional[List[Dict]] = None,
    index_dir: Any = None,
    profile: Any = None,
    query_type: Any = None,
    entity_info: Optional[Dict[str, Any]] = None,
    prior_chunks: Optional[List[Dict[str, Any]]] = None,
    diag: Optional[Dict[str, Any]] = None,
) -> Optional[Tuple[str, List[Dict[str, Any]], Dict[str, Any]]]:
    """
    Multi-layer KB rescue before returning NOT_FOUND.
    Layers (in order): answer memory → baseline law → learned retry → keyword scan → chunk synthesis.
    """
    if not ENABLED:
        return None

    diag = dict(diag or {})
    entity_info = entity_info or {}

    # Layer 1: Answer memory (instant — no index needed)
    mem = lookup_answer_memory(user_id, query)
    if mem and mem.get("answer") and not _answer_matches_query_sections(query, mem["answer"]):
        mem = None
    if mem and mem.get("answer"):
        _log_rescue(user_id, query, "answer_memory", True, f"conf={mem.get('confidence')}")
        diag["rescue"] = "answer_memory"
        diag["rescue_confidence"] = mem.get("confidence")
        return mem["answer"], prior_chunks or [], {**diag, "found": True, "found_reason": "answer_memory"}

    # Layer 2: Deterministic law mapping (no chunks required) — never for section lookups
    try:
        from backend.app.services.legal_query_parser import is_section_lookup_query
        from kb_legal_query_rewrite import build_baseline_law_answer, extract_law_mapping_answer, is_law_replacement_query

        if not is_section_lookup_query(query) and is_law_replacement_query(query):
            baseline = build_baseline_law_answer(query)
            if baseline:
                _log_rescue(user_id, query, "baseline_law", True)
                store_answer_memory(user_id, query, baseline, source="baseline_law", confidence=0.78)
                diag["rescue"] = "baseline_law"
                return baseline, prior_chunks or [], {**diag, "found": True, "found_reason": "baseline_law"}

            if prior_chunks:
                mapped = extract_law_mapping_answer(query, prior_chunks)
                if mapped:
                    _log_rescue(user_id, query, "law_mapping_chunks", True)
                    store_answer_memory(user_id, query, mapped, source="law_mapping", confidence=0.82)
                    diag["rescue"] = "law_mapping_chunks"
                    return mapped, prior_chunks, {**diag, "found": True, "found_reason": "law_mapping_chunks"}
    except Exception as exc:
        logger.debug("Law mapping rescue skipped: %s", exc)

    if index_dir is None:
        try:
            from app import resolve_rag_index_dir

            index_dir = resolve_rag_index_dir(user_id, None)
        except Exception:
            index_dir = None

    # Layer 3: Learned query expansion + re-retrieve
    retry_queries: List[str] = []
    section_lookup = False
    try:
        from backend.app.services.legal_query_parser import (
            answer_satisfies_section_query,
            filter_chunks_for_section_query,
            is_section_lookup_query,
        )

        section_lookup = is_section_lookup_query(query)
    except ImportError:
        answer_satisfies_section_query = None  # type: ignore
        filter_chunks_for_section_query = None  # type: ignore
        is_section_lookup_query = None  # type: ignore

    try:
        from backend.app.services.legal_query_parser import is_section_lookup_query as _is_sec
        from kb_legal_query_rewrite import expand_law_replacement_queries, normalize_legal_query

        retry_queries.append(normalize_legal_query(query))
        if not _is_sec(query):
            retry_queries.extend(expand_law_replacement_queries(query)[:4])
        from backend.app.core.adaptive_learning import apply_learned_query_expansion

        learned = apply_learned_query_expansion(user_id, "knowledge_base", query, "")
        if learned and learned != query and not _is_sec(query):
            retry_queries.append(learned)
        elif learned and learned != query and _is_sec(query):
            # Section queries: only allow expansions that still mention the section.
            secs = _section_numbers(query)
            if secs and any(s in learned.lower() for s in secs):
                retry_queries.append(learned)
    except Exception:
        pass

    seen_q = set()
    for rq in retry_queries:
        rq = (rq or "").strip()
        if not rq or rq.lower() in seen_q:
            continue
        seen_q.add(rq.lower())
        if not index_dir:
            continue
        chunks = _retry_retrieval(user_id, rq, index_dir, profile, k=14)
        if not chunks:
            continue
        if section_lookup and filter_chunks_for_section_query:
            chunks = filter_chunks_for_section_query(query, chunks)
            if not chunks:
                continue
        try:
            from kb_rag_decision import evaluate_retrieval, section_match_in_chunks

            qt_val = None
            if query_type is not None:
                qt_val = getattr(query_type, "value", query_type)
            found, score, _, _ = evaluate_retrieval(
                query,
                chunks,
                threshold=0.32,
                query_type=qt_val,
                entities=list(_section_numbers(query)) or None,
            )
            if section_lookup and not section_match_in_chunks(chunks, list(_section_numbers(query))):
                continue
            if found or score >= 0.30:
                from kb_response_state import build_found_answer

                answer = build_found_answer(query, chunks[:6], profile, messages=history, use_llm=False)
                if answer and len(answer) >= MIN_ANSWER_LEN:
                    if answer_satisfies_section_query and not answer_satisfies_section_query(query, answer):
                        continue
                    _log_rescue(user_id, query, "learned_retry", True, rq[:80])
                    learn_from_kb_success(user_id, query, answer, chunks, source="rescue_retry", confidence=0.75)
                    diag["rescue"] = "learned_retry"
                    diag["retry_query"] = rq
                    return answer, chunks, {**diag, "found": True, "found_reason": "learned_retry"}
        except Exception:
            continue

    # Layer 4: Docstore keyword scan (embedding-free)
    if index_dir:
        kw_chunks = _docstore_keyword_rescue(query, index_dir)
        if kw_chunks:
            try:
                from kb_legal_query_rewrite import extract_law_mapping_answer, is_law_replacement_query
                from kb_response_state import build_found_answer

                if is_law_replacement_query(query):
                    mapped = extract_law_mapping_answer(query, kw_chunks)
                    if mapped:
                        _log_rescue(user_id, query, "keyword_law_mapping", True)
                        learn_from_kb_success(user_id, query, mapped, kw_chunks, source="keyword_rescue", confidence=0.80)
                        diag["rescue"] = "keyword_law_mapping"
                        return mapped, kw_chunks, {**diag, "found": True, "found_reason": "keyword_law_mapping"}

                answer = build_found_answer(query, kw_chunks[:6], profile, messages=history, use_llm=False)
                if answer and len(answer) >= MIN_ANSWER_LEN and "couldn't find" not in answer.lower():
                    try:
                        from backend.app.services.legal_query_parser import answer_satisfies_section_query

                        if not answer_satisfies_section_query(query, answer):
                            answer = ""
                    except ImportError:
                        pass
                if answer and len(answer) >= MIN_ANSWER_LEN and "couldn't find" not in answer.lower():
                    _log_rescue(user_id, query, "keyword_docstore", True)
                    learn_from_kb_success(user_id, query, answer, kw_chunks, source="keyword_rescue", confidence=0.70)
                    diag["rescue"] = "keyword_docstore"
                    return answer, kw_chunks, {**diag, "found": True, "found_reason": "keyword_docstore"}
            except Exception:
                pass

    # Layer 5: Document-wide scan for list/summary queries
    if index_dir and query_type is not None:
        try:
            from kb_document_scan import search_entire_document
            from kb_query_types import QueryType
            from kb_response_state import build_found_answer

            if query_type in {QueryType.SUMMARY, QueryType.LIST_EXTRACTION, QueryType.TOPIC_QUERY}:
                scan_chunks, scan_entities = search_entire_document(index_dir, query, query_type)
                if scan_entities or scan_chunks:
                    if profile and scan_entities:
                        profile.signals["extracted_entities"] = scan_entities
                    answer = build_found_answer(
                        query, scan_chunks, profile, messages=history, use_llm=False
                    )
                    if answer and len(answer) >= MIN_ANSWER_LEN:
                        _log_rescue(user_id, query, "document_scan", True)
                        learn_from_kb_success(user_id, query, answer, scan_chunks, source="doc_scan", confidence=0.72)
                        diag["rescue"] = "document_scan"
                        return answer, scan_chunks, {**diag, "found": True, "found_reason": "document_scan"}
        except Exception:
            pass

    _log_rescue(user_id, query, "exhausted", False)
    learn_from_kb_failure(user_id, query, prior_chunks or [])
    return None


def learn_from_web_success(
    user_id: str,
    query: str,
    answer: str,
    *,
    source: str = "web_success",
    confidence: float = 0.82,
) -> Optional[str]:
    """Store proven Open Law answers for instant replay and neural pair collection."""
    mem_id = store_answer_memory(
        user_id, query, answer, source=source, confidence=confidence,
    )
    try:
        from backend.app.core.neural_finetuning import add_training_pair

        if len((answer or "").strip()) >= 40:
            add_training_pair(query, answer[:2000], user_id=str(user_id), source=source)
    except Exception:
        pass

    def _bg_train() -> None:
        try:
            from backend.app.core.neural_finetuning import maybe_auto_train

            maybe_auto_train(str(user_id))
        except Exception:
            pass

    try:
        import threading

        threading.Thread(target=_bg_train, daemon=True).start()
    except Exception:
        pass
    return mem_id


def learn_from_kb_success(
    user_id: str,
    query: str,
    answer: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
    *,
    source: str = "kb_success",
    confidence: float = 0.85,
    thread_id: str = "",
) -> None:
    """Unified post-success learning — memory + adaptive + neural + user facts."""
    if not ENABLED:
        return

    chunk_keys: List[str] = []
    try:
        from backend.app.core.adaptive_learning import chunk_key_from_result

        chunk_keys = [chunk_key_from_result(c) for c in (chunks or [])[:8]]
    except Exception:
        pass

    store_answer_memory(
        user_id,
        query,
        answer,
        source=source,
        confidence=confidence,
        chunk_keys=chunk_keys,
    )

    try:
        from backend.app.core.adaptive_learning import _implicit_positive_chunks, normalize_query

        if chunk_keys:
            _implicit_positive_chunks(str(user_id), "knowledge_base", chunk_keys, weight=0.08)
        qn = normalize_query(query)
        conn = _connect()
        try:
            from backend.app.core.adaptive_learning import ensure_learning_schema, _upsert_query_pattern

            ensure_learning_schema()
            _upsert_query_pattern(
                conn, str(user_id), "knowledge_base", qn, query, success_delta=1
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

    try:
        from backend.app.core.neural_finetuning import add_pairs_from_interaction, maybe_auto_train

        if chunks:
            add_pairs_from_interaction(str(user_id), query, chunks, source=source)

        def _bg_train() -> None:
            try:
                maybe_auto_train(str(user_id))
            except Exception:
                pass

        import threading

        threading.Thread(target=_bg_train, daemon=True, name="neural-auto-train").start()
    except Exception:
        pass

    try:
        from backend.app.core.user_memory import remember_kb_success

        remember_kb_success(user_id, query, answer, thread_id=thread_id)
    except Exception:
        pass


def learn_from_kb_failure(
    user_id: str,
    query: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Record failure signals for faster adaptation on next similar query."""
    if not ENABLED:
        return
    try:
        from backend.app.core.adaptive_learning import normalize_query, ensure_learning_schema

        qn = normalize_query(query)
        ensure_learning_schema()
        conn = _connect()
        try:
            conn.execute(
                """UPDATE adaptive_query_patterns SET fail_count = fail_count + 1
                WHERE query_norm=? AND user_id=?""",
                (qn, str(user_id)),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def get_learning_engine_status(user_id: str = "") -> Dict[str, Any]:
    ensure_learning_engine_schema()
    conn = _connect()
    try:
        mem_count = conn.execute(
            "SELECT COUNT(*) FROM kb_answer_memory WHERE user_id=? OR user_id=''",
            (str(user_id),),
        ).fetchone()
        rescue_rows = conn.execute(
            """SELECT rescue_layer, SUM(success), COUNT(*)
            FROM kb_rescue_events WHERE user_id=? GROUP BY rescue_layer""",
            (str(user_id),),
        ).fetchall()
        top_mem = conn.execute(
            """SELECT query, hit_count, confidence FROM kb_answer_memory
            WHERE user_id=? ORDER BY hit_count DESC LIMIT 5""",
            (str(user_id),),
        ).fetchall()
    finally:
        conn.close()

    neural: Dict[str, Any] = {}
    adaptive: Dict[str, Any] = {}
    try:
        from backend.app.core.neural_finetuning import tuning_status

        neural = tuning_status(user_id)
    except Exception:
        pass
    try:
        from backend.app.core.adaptive_learning import learning_stats

        adaptive = learning_stats(user_id)
    except Exception:
        pass

    return {
        "enabled": ENABLED,
        "memory_enabled": MEMORY_ENABLED,
        "answer_memory_count": int(mem_count[0] if mem_count else 0),
        "top_memories": [
            {"query": r[0], "hits": r[1], "confidence": r[2]} for r in (top_mem or [])
        ],
        "rescue_stats": {r[0]: {"successes": r[1], "attempts": r[2]} for r in (rescue_rows or [])},
        "neural_finetuning": neural,
        "adaptive_learning": adaptive,
        "performance": (adaptive or {}).get("summary") or {},
        "ollama_coach": _coach_status_safe(user_id),
        "improvement_automation": _automation_status_safe(user_id),
        "llm_finetuning": _llm_status_safe(user_id),
        "inference_rewards": _reward_status_safe(user_id),
    }


def _llm_status_safe(user_id: str) -> Dict[str, Any]:
    try:
        from backend.app.core.llm_finetuning import tuning_status

        return tuning_status(user_id)
    except Exception:
        return {}


def _reward_status_safe(user_id: str) -> Dict[str, Any]:
    try:
        from backend.app.core.reward_inference import get_reward_summary

        return get_reward_summary(user_id)
    except Exception:
        return {}


def _automation_status_safe(user_id: str) -> Dict[str, Any]:
    try:
        from backend.app.core.improvement_automation import automation_status

        return automation_status(user_id)
    except Exception:
        return {"enabled": False}


def _coach_status_safe(user_id: str) -> Dict[str, Any]:
    try:
        from backend.app.core.gemini_ollama_coach import coach_status

        return coach_status(user_id)
    except Exception:
        return {"available": False, "global_enabled": False}
