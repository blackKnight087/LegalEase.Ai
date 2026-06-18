"""
Multi-stage Knowledge Base pipeline:
Intent → Retrieve → Rerank → Filter → Aggregate → Generate → Validate
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from conversation_context import merge_retrieval_query
from intent_engine import IntentProfile, QueryIntent, classify_intent
from kb_query_types import (
    QueryType,
    detect_query_type,
    extract_entities,
    needs_document_wide_scan,
    query_type_signals,
    retrieval_k_for_type,
)
from kb_validate import validate_answer


def _law_from_query(query: str) -> str:
    ql = (query or "").lower()
    if re.search(r"\bbns\b", ql):
        return "bns"
    if re.search(r"\bipc\b", ql):
        return "ipc"
    return ""


def _primary_section_for_answer(profile: IntentProfile) -> str:
    """Section number for this turn — current query only, never stale chat context."""
    from kb_query_types import primary_sections_from_query

    orig = str((profile.signals or {}).get("original_query") or "")
    secs = primary_sections_from_query(orig)
    if len(secs) == 1:
        return secs[0]
    ent = (profile.signals or {}).get("entities") or []
    if len(ent) == 1:
        return str(ent[0])
    if secs:
        return secs[0]
    return ""


def _try_entity_lookup_answer(
    user_id: str,
    query: str,
    scope: Dict[str, Any],
    index_dir: Any,
    chunks: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """Answer contract/NDA entity questions from stored or indexed document text."""
    from contract_entity_extractor import answer_entity_lookup, extract_contract_entities
    from document_classifier import is_contract_family

    doc_type = scope.get("document_type") or ""
    if not is_contract_family(doc_type):
        from document_classifier import document_type_for_query

        if not is_contract_family(document_type_for_query(query)):
            return None
        doc_type = document_type_for_query(query) or "nda"

    try:
        from backend.app.core.document_entities import load_document_entities

        stored = None
        if scope.get("doc_id"):
            stored = load_document_entities(user_id, document_id=str(scope.get("doc_id", "")))
        if not stored and scope.get("filename"):
            stored = load_document_entities(user_id, filename=str(scope.get("filename", "")))
        if stored:
            answer = answer_entity_lookup(query, stored, stored.get("_document_type", doc_type))
            if answer:
                return answer
    except Exception:
        pass

    from kb_content_cleaner import is_index_meta_boilerplate

    body_parts: List[str] = []
    if chunks:
        for c in chunks[:8]:
            text = (c.get("content") or "").strip()
            if text and not is_index_meta_boilerplate(text):
                body_parts.append(text)
    try:
        from backend.app.core.kb_doc_scope import (
            load_contract_index_text,
            load_scoped_document_text,
        )

        scoped_text = load_scoped_document_text(index_dir, scope)
        if scoped_text:
            body_parts.append(scoped_text)
        if not body_parts:
            contract_text = load_contract_index_text(index_dir, scope)
            if contract_text:
                body_parts.append(contract_text)
    except Exception:
        pass

    body = "\n\n".join(p for p in body_parts if p).strip()
    if not body:
        return None

    structured = extract_contract_entities(body, doc_type)
    return answer_entity_lookup(query, structured, doc_type)


def metadata_filter(
    query_type: QueryType,
    query: str,
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    from kb_document_scan import filter_chunks_by_law
    from kb_query_types import _requested_laws

    if not chunks:
        return []
    if query_type in {QueryType.LIST_EXTRACTION, QueryType.SUMMARY, QueryType.TOPIC_QUERY}:
        return chunks
    if query_type == QueryType.LAW_REPLACEMENT:
        return chunks
    laws = _requested_laws(query)
    if laws:
        chunks = filter_chunks_by_law(chunks, laws)
    if query_type == QueryType.LIST_EXTRACTION:
        filtered = []
        for ch in chunks:
            text = ch.get("content") or ""
            if re.search(
                r"\b(?:IPC|Indian Penal Code|IT Act|Section\s+\d|66[CDEF])\b",
                text,
                re.I,
            ):
                filtered.append(ch)
        if filtered:
            return filtered
    return chunks


def aggregate_chunks(
    chunks: List[Dict[str, Any]],
    query_type: QueryType,
    profile: IntentProfile,
    entities: Optional[List[Dict[str, str]]] = None,
    *,
    section_entities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    from kb_retrieval import ensure_per_section_chunks, extract_comparison_sections, is_comparison_query

    if not chunks:
        return []

    max_total = profile.max_context_chunks or 8
    if query_type in {QueryType.LIST_EXTRACTION, QueryType.SUMMARY, QueryType.TOPIC_QUERY}:
        max_total = max(max_total, 12)
    if query_type == QueryType.COMPARISON:
        max_total = max(max_total, 10)

    seen = set()
    unique: List[Dict[str, Any]] = []
    for ch in chunks:
        meta = ch.get("metadata") or {}
        key = (
            str(meta.get("filename", "")),
            str(meta.get("chunk_index", "")),
            str(ch.get("entity", "")),
            (ch.get("content") or "")[:96],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(ch)

    unique.sort(
        key=lambda c: float(c.get("final_score", c.get("hybrid_score", 0))),
        reverse=True,
    )

    cmp_q = profile.signals.get("original_query") or profile.expanded_query or ""
    secs = section_entities or profile.signals.get("entities") or []
    if query_type == QueryType.COMPARISON or is_comparison_query(cmp_q):
        if len(secs) < 2:
            secs = extract_comparison_sections(cmp_q)
        if len(secs) >= 2:
            return ensure_per_section_chunks(unique, secs, max_total=max_total)

    if entities:
        profile.signals["extracted_entities"] = entities

    return unique[:max_total]


def generate_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
    profile: IntentProfile,
    history: Optional[List[Dict]] = None,
    *,
    query_type: QueryType = QueryType.UNKNOWN,
    entities: Optional[List[Dict[str, str]]] = None,
    user_id: str = "",
) -> str:
    from kb_response_state import build_found_answer, enforce_single_state

    try:
        from backend.app.core.kb_dense_document import try_dense_document_answer

        dense_early = try_dense_document_answer(
            query,
            context_chunks,
            scope=(profile.signals or {}).get("document_scope"),
        )
        if dense_early:
            return enforce_single_state(dense_early, found=True)
    except ImportError:
        pass

    if query_type == QueryType.ENTITY_LOOKUP and context_chunks:
        from contract_entity_extractor import answer_entity_lookup, extract_contract_entities
        from document_classifier import is_contract_family

        scope = (profile.signals or {}).get("document_scope") or {}
        doc_type = scope.get("document_type") or ""
        body = " ".join((c.get("content") or "") for c in context_chunks[:4])
        if is_contract_family(doc_type) or is_contract_family(
            str((context_chunks[0].get("metadata") or {}).get("document_type", ""))
        ):
            structured = extract_contract_entities(body, doc_type)
            answer = answer_entity_lookup(query, structured, doc_type)
            if answer:
                return enforce_single_state(answer, found=True)
        if user_id and scope.get("doc_id"):
            try:
                from backend.app.core.document_entities import load_document_entities

                stored = load_document_entities(user_id, document_id=scope.get("doc_id", ""))
                if stored:
                    answer = answer_entity_lookup(query, stored, stored.get("_document_type", ""))
                    if answer:
                        return enforce_single_state(answer, found=True)
            except Exception:
                pass

    try:
        from backend.app.services.legal_query_parser import is_section_lookup_query
        from kb_legal_query_rewrite import (
            build_baseline_law_answer,
            extract_law_mapping_answer,
            is_law_replacement_query,
        )

        if not is_section_lookup_query(query) and (
            is_law_replacement_query(query) or query_type == QueryType.LAW_REPLACEMENT
        ):
            mapped = extract_law_mapping_answer(query, context_chunks)
            if not mapped:
                mapped = build_baseline_law_answer(query)
            if mapped:
                from citation_formatter import polish_kb_response

                return enforce_single_state(
                    polish_kb_response(mapped, context_chunks),
                    found=True,
                )
    except Exception:
        pass

    try:
        from kb_query_types import is_case_query

        if is_case_query(query):
            from answer_orchestrator import format_case_topic_answer

            answer = format_case_topic_answer(query, context_chunks)
            if answer:
                return enforce_single_state(answer, found=True)
    except ImportError:
        pass

    plan_dict = (profile.signals or {}).get("legal_query_plan") or {}
    try:
        from backend.app.services.legal_query_engine import (
            LegalQueryKind,
            generate_multi_section_answer,
        )

        if (
            plan_dict.get("kind") == LegalQueryKind.MULTI_SECTION_EXPLANATION.value
            or (profile.signals.get("multi_entity") and len(plan_dict.get("sections") or []) >= 2)
        ):
            secs = plan_dict.get("sections") or profile.signals.get("sections") or []
            law = str(plan_dict.get("primary_law") or profile.signals.get("primary_law") or "IPC")
            multi = generate_multi_section_answer(
                query,
                context_chunks,
                secs,
                law=law.lower(),
                user_id=user_id,
            )
            if multi:
                return enforce_single_state(multi, found=True)
    except Exception:
        pass

    if re.search(
        r"\b(constitutional rights?|name\s+(?:five|5)\s+.*rights|fundamental rights?)\b",
        (query or "").lower(),
    ) or plan_dict.get("kind") == "constitutional_query":
        from answer_orchestrator import format_constitutional_rights_answer

        answer = format_constitutional_rights_answer(query, context_chunks)
        if answer:
            return enforce_single_state(answer, found=True)

    if query_type in {QueryType.LIST_EXTRACTION, QueryType.SUMMARY, QueryType.TOPIC_QUERY} and entities:
        ql = query.lower()
        if query_type == QueryType.SUMMARY or re.search(r"\b(offence|offenses?|criminal)\b", ql):
            from answer_orchestrator import format_criminal_offences_summary

            answer = format_criminal_offences_summary(query, entities, context_chunks, profile)
            if answer:
                return enforce_single_state(answer, found=True)
        from answer_orchestrator import format_ipc_sections_list

        answer = format_ipc_sections_list(query, entities, context_chunks, profile)
        if answer:
            return enforce_single_state(answer, found=True)

    if query_type == QueryType.COMPARISON:
        profile.primary = QueryIntent.COMPARISON
        typed = profile.signals.get("typed_entities") or []
        if len(typed) >= 2:
            from kb_compare_engine import format_comparison_pro

            mapping_mode = bool((profile.signals or {}).get("mapping_mode"))
            answer = format_comparison_pro(
                query,
                context_chunks,
                typed,
                mapping_mode=mapping_mode,
            )
            if answer and "couldn't find" not in answer.lower():
                return enforce_single_state(answer, found=True)
        secs = profile.signals.get("entities") or []
        if len(secs) >= 2:
            profile.signals["sections"] = secs

    section_q_types = {
        QueryType.SECTION_EXPLANATION,
        QueryType.SECTION_LOOKUP,
        QueryType.PUNISHMENT_QUERY,
    }
    if profile.signals.get("multi_entity") and len(profile.signals.get("sections") or []) >= 2:
        try:
            from backend.app.services.legal_query_engine import generate_multi_section_answer

            secs = profile.signals.get("sections") or []
            law = str(profile.signals.get("primary_law") or "IPC")
            multi = generate_multi_section_answer(
                query,
                context_chunks,
                secs,
                law=law.lower(),
                user_id=user_id,
            )
            if multi:
                return enforce_single_state(multi, found=True)
        except Exception:
            pass

    primary_sec = _primary_section_for_answer(profile)
    if query_type in section_q_types and primary_sec and not profile.signals.get("multi_entity"):
        from kb_preprocess import filter_chunks_for_section
        from answer_orchestrator import format_statute_section_answer, intent_aware_fallback

        orig_q = str((profile.signals or {}).get("original_query") or query)
        law = _law_from_query(orig_q) or str((profile.signals or {}).get("law") or "")
        profile.signals["sections"] = [primary_sec]
        profile.signals["law"] = law
        scoped = filter_chunks_for_section(context_chunks, primary_sec, law=law)
        answer = build_found_answer(
            query,
            scoped or context_chunks,
            profile,
            messages=history,
            use_llm=True,
            temperature=0.12,
            max_tokens=max(int(profile.max_answer_tokens or 0), 1800),
            user_id=user_id,
        )
        if answer and "couldn't find" not in answer.lower():
            try:
                from backend.app.services.legal_query_parser import answer_satisfies_section_query

                if answer_satisfies_section_query(query, answer):
                    return enforce_single_state(answer, found=True)
            except ImportError:
                return enforce_single_state(answer, found=True)
        if query_type == QueryType.PUNISHMENT_QUERY:
            from answer_orchestrator import format_statute_section_answer as _fmt

            pun = _fmt(query, scoped or context_chunks, primary_sec, law)
            if pun:
                return enforce_single_state(pun, found=True)
        fast = format_statute_section_answer(query, scoped or context_chunks, primary_sec, law)
        if fast:
            return enforce_single_state(fast, found=True)

    section_chunks = context_chunks
    if query_type in section_q_types and primary_sec:
        from kb_preprocess import filter_chunks_for_section

        law = _law_from_query(str((profile.signals or {}).get("original_query") or query))
        filtered = filter_chunks_for_section(context_chunks, primary_sec, law=law)
        if filtered:
            section_chunks = filtered

    answer = build_found_answer(
        query,
        section_chunks,
        profile,
        messages=history,
        use_llm=query_type
        not in {
            QueryType.LIST_EXTRACTION,
            QueryType.COMPARISON,
            QueryType.SUMMARY,
        },
        temperature=0.12,
        max_tokens=max(int(profile.max_answer_tokens or 0), 1800),
        user_id=user_id,
    )
    return enforce_single_state(answer, found=True)


def kb_retrieve(
    user_id: str,
    query: str,
    history: Optional[List[Dict]],
    index_dir: Any,
    profile: IntentProfile,
    query_type: QueryType,
    entity_info: Dict[str, Any],
    *,
    thread_id: Optional[str] = None,
    document_scope: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], Dict[str, Any]]:
    from rag import get_last_query_diagnostics, get_last_query_error, query_kb
    from backend.app.core.kb_doc_scope import filter_chunks_by_scope, resolve_document_scope

    scope = document_scope or resolve_document_scope(
        user_id,
        query,
        index_dir,
        thread_id=thread_id,
        history=history,
    )
    profile.signals["document_scope"] = scope

    retrieval_q = merge_retrieval_query(
        query,
        history,
        intent_expanded=profile.expanded_query or "",
    )
    k = retrieval_k_for_type(query_type, profile.retrieval_k or 8)
    section_entities: List[str] = entity_info.get("entities") or []
    entities: List[Dict[str, str]] = []
    diag: Dict[str, Any] = {
        "query_type": query_type.value,
        "retrieval_k": k,
        "entities": section_entities,
    }

    if query_type == QueryType.COMPARISON:
        typed = entity_info.get("typed_entities") or []
        if not typed or len(typed) < 2:
            try:
                from kb_compare_engine import extract_all_comparison_entities

                typed = extract_all_comparison_entities(query)
            except Exception:
                typed = typed or []
        if len(typed) >= 2:
            from kb_compare_engine import retrieve_comparison_bundle

            bundle = retrieve_comparison_bundle(typed, index_dir, k_per_entity=8)
            chunks = bundle.all_chunks
            diag["mode"] = "compare_independent"
            diag["typed_entities"] = typed
            diag["left"] = typed[0]
            diag["right"] = typed[1] if len(typed) > 1 else {}
            diag["comparison_bundle"] = True
            profile.signals["comparison_bundle"] = {
                "left_entity": bundle.left_entity,
                "right_entity": bundle.right_entity,
                "left_chunks": len(bundle.left_chunks),
                "right_chunks": len(bundle.right_chunks),
            }
            from kb_compare_engine import _entity_in_chunk

            matched = sum(
                1
                for ent in typed[:4]
                if any(_entity_in_chunk(c.get("content", ""), ent) for c in chunks)
            )
            diag["entities_matched"] = matched
        elif len(section_entities) >= 2:
            from kb_retrieval import retrieve_chunks_per_entity

            chunks = retrieve_chunks_per_entity(
                index_dir,
                section_entities,
                "",
                k_per_entity=8,
                max_total=max(k, 14),
            )
            diag["mode"] = "per_entity_comparison"
            from kb_retrieval import ensure_per_section_chunks, section_in_chunk

            matched = sum(
                1
                for sec in section_entities
                if any(
                    str(c.get("entity", "")) == sec
                    or section_in_chunk(c.get("content", ""), sec)
                    for c in chunks
                )
            )
            diag["entities_matched"] = matched
            if matched < len(section_entities):
                extra = query_kb(retrieval_q, k=k, index_dir=index_dir, document_scope=scope)
                seen = {(c.get("content") or "")[:80] for c in chunks}
                for c in extra:
                    if (c.get("content") or "")[:80] not in seen:
                        chunks.append(c)
                chunks = ensure_per_section_chunks(chunks, section_entities, max_total=k)
    elif needs_document_wide_scan(query_type, query):
        from kb_document_scan import search_entire_document

        chunks, entities = search_entire_document(index_dir, query, query_type)
        diag["mode"] = "document_scan"
        diag["entities_found"] = len(entities)
        if not chunks and not entities:
            chunks = query_kb(retrieval_q, k=k, index_dir=index_dir, document_scope=scope)
            diag["mode"] = "document_scan_fallback_vector"
    else:
        law_hint = _law_from_query(query) or "IPC"
        if profile.signals.get("multi_entity") and len(section_entities) >= 2:
            from kb_retrieval import retrieve_chunks_per_entity

            chunks = retrieve_chunks_per_entity(
                index_dir,
                section_entities,
                "",
                k_per_entity=8,
                max_total=max(k, 14),
            )
            diag["mode"] = "multi_section_per_entity"
        elif section_entities and query_type in {
            QueryType.SECTION_LOOKUP,
            QueryType.SECTION_EXPLANATION,
            QueryType.PUNISHMENT_QUERY,
        }:
            try:
                from rag import exact_section_lookup

                exact = exact_section_lookup(
                    index_dir,
                    section_entities[:3],
                    law=law_hint,
                    top_k=k,
                )
                if exact:
                    chunks = exact
                    diag["mode"] = "exact_section"
                else:
                    chunks = query_kb(
                        retrieval_q, k=k, index_dir=index_dir, document_scope=scope
                    )
                    diag["mode"] = "vector"
            except Exception:
                chunks = query_kb(
                    retrieval_q, k=k, index_dir=index_dir, document_scope=scope
                )
                diag["mode"] = "vector"
        else:
            chunks = query_kb(retrieval_q, k=k, index_dir=index_dir, document_scope=scope)
            diag["mode"] = "vector"

    chunks = filter_chunks_by_scope(chunks, scope)
    diag["document_scope"] = scope

    diag["vector_error"] = get_last_query_error()
    diag.update(get_last_query_diagnostics() or {})

    try:
        from backend.app.core.adaptive_learning import apply_chunk_boosts

        chunks = apply_chunk_boosts(user_id, "knowledge_base", chunks)
    except Exception:
        pass

    chunks = metadata_filter(query_type, query, chunks)
    primary_sec = _primary_section_for_answer(profile)
    if (
        query_type
        in {
            QueryType.SECTION_EXPLANATION,
            QueryType.SECTION_LOOKUP,
            QueryType.PUNISHMENT_QUERY,
        }
        and primary_sec
        and not profile.signals.get("multi_entity")
    ):
        from kb_preprocess import filter_chunks_for_section

        profile.signals["sections"] = [primary_sec]
        chunks = filter_chunks_for_section(chunks, primary_sec)
    chunks = aggregate_chunks(
        chunks,
        query_type,
        profile,
        entities,
        section_entities=section_entities,
    )

    try:
        from backend.app.core.kb_pipeline_log import kb_log

        kb_log(
            "PIPELINE_RETRIEVE",
            query_type=query_type.value,
            mode=diag.get("mode"),
            k=k,
            count=len(chunks),
            entities=len(entities),
            section_entities=section_entities,
        )
        for i, c in enumerate(chunks[:6]):
            kb_log(
                "PIPELINE_CHUNK",
                i=i,
                entity=c.get("entity"),
                score=c.get("final_score"),
                file=(c.get("metadata") or {}).get("filename"),
                excerpt=(c.get("content") or "")[:120],
            )
    except Exception:
        pass

    return chunks, entities, diag


def kb_pipeline(
    user_id: str,
    query: str,
    history: Optional[List[Dict]] = None,
    index_dir: Any = None,
    thread_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    from app import get_user_index_dir
    from kb_rag_decision import evaluate_retrieval
    from kb_response_state import KB_NOT_FOUND_MESSAGE

    if index_dir is None:
        try:
            from app import resolve_rag_index_dir

            index_dir = resolve_rag_index_dir(user_id)
        except Exception:
            index_dir = get_user_index_dir(user_id)

    try:
        from backend.app.core.embedding_manager import get_manager

        mgr = get_manager()
        mgr.start_background_load()
        st = mgr.get_status()
        if not st.get("ready"):
            wait_sec = float(__import__("os").getenv("KB_EMBED_WAIT_SEC", "6"))
            if st.get("state") == "LOADING_MODEL" and wait_sec > 0:
                mgr.wait_until_ready(timeout_sec=wait_sec)
            st = mgr.get_status()
            if not st.get("ready") and st.get("state") == "FAILED":
                import logging

                logging.getLogger(__name__).warning(
                    "Embeddings not ready — continuing with keyword/docstore retrieval"
                )
    except Exception:
        pass

    original_user_query = query
    try:
        from backend.app.core.kb_query_clean import strip_chat_routing_prefix

        original_user_query = strip_chat_routing_prefix(query) or (query or "").strip()
    except Exception:
        original_user_query = (query or "").strip()
    orchestrator_query = original_user_query
    retrieval_query = original_user_query

    session_mem: Dict[str, Any] = {}
    if session_id:
        try:
            from backend.app.core.conversation_memory import get_session_legal_memory

            session_mem = dict(get_session_legal_memory(session_id) or {})
        except Exception:
            pass

    try:
        from backend.app.services.followup_detector import requires_fresh_retrieval

        if requires_fresh_retrieval(original_user_query, session_mem):
            session_mem = {}
    except Exception:
        pass
    if history:
        try:
            from conversation_context import build_conversation_state

            state = build_conversation_state(history)
            if state.active_sections:
                session_mem.setdefault("last_section", state.active_sections[0])
            if state.active_law:
                session_mem.setdefault("last_law", state.active_law.upper())
            if state.active_topic:
                session_mem.setdefault("last_topic", state.active_topic)
        except Exception:
            pass

    try:
        from backend.app.core.kb_context_resolver import build_retrieval_queries

        retrieval_query, orchestrator_query = build_retrieval_queries(
            original_user_query, session_mem, history
        )
    except Exception:
        retrieval_query = original_user_query

    # Light follow-up expansion for deictic queries only — never replace fresh retrieval query.
    try:
        from backend.app.core.kb_query_memory import expand_kb_query

        expanded = expand_kb_query(
            retrieval_query, history, session_mem=session_mem or None
        )
        if expanded and expanded.strip():
            retrieval_query = expanded.strip()
        if orchestrator_query == original_user_query and expanded:
            orchestrator_query = expanded.strip()
    except Exception:
        pass

    # V2 orchestrator is the sole controller: parse → plan → retrieve → generate → validate
    try:
        from backend.app.services.legal_orchestrator_v2 import run_legal_orchestrator_v2

        out = run_legal_orchestrator_v2(
            user_id=user_id,
            query=orchestrator_query,
            retrieval_query=retrieval_query,
            history=history,
            index_dir=index_dir,
            thread_id=thread_id,
            session_id=session_id,
        )
        # region agent log
        try:
            from backend.app.core.debug_kb_session import dbg_kb

            ans, chs, diag = out[0], out[1] if len(out) > 1 else [], out[2] if len(out) > 2 else {}
            dbg_kb(
                "H2",
                "kb_pipeline.py:kb_pipeline",
                "orchestrator_result",
                {
                    "orchestrator_query": orchestrator_query[:160],
                    "retrieval_query": retrieval_query[:160],
                    "qclass": str((diag or {}).get("query_class") or ""),
                    "answer_len": len(ans or ""),
                    "preview": (ans or "")[:180],
                },
            )
        except Exception:
            pass
        # endregion
        return out
    except Exception as orch_exc:
        import logging

        logging.getLogger(__name__).warning(
            "legal_orchestrator_v2 failed, legacy pipeline: %s", orch_exc
        )

    session_mem: Dict[str, Any] = {}
    if session_id:
        try:
            from backend.app.core.conversation_memory import get_session_legal_memory

            session_mem = get_session_legal_memory(session_id)
        except Exception:
            pass

    try:
        from backend.app.core.kb_query_memory import expand_kb_query, memory_context_block
        from backend.app.services.followup_detector import get_effective_session_memory

        effective_session_mem = get_effective_session_memory(original_user_query, session_mem)
        expanded = expand_kb_query(
            query, history, session_mem=effective_session_mem
        )
        if expanded.strip() != query.strip():
            query = expanded
    except Exception:
        pass

    try:
        from backend.legal_engine.query_parser import parse_legal_query
        from backend.app.services.followup_detector import get_effective_session_memory

        effective_session_mem = get_effective_session_memory(original_user_query, session_mem)
        legal_parse = parse_legal_query(
            original_user_query, history, session_state=effective_session_mem
        )
        if legal_parse.resolved_query and legal_parse.resolved_query.strip() != query.strip():
            query = legal_parse.resolved_query
    except Exception:
        legal_parse = None  # noqa: F841

    legal_plan = None
    try:
        from backend.app.services.legal_query_engine import analyze_legal_query

        legal_plan = analyze_legal_query(original_user_query, history)
    except Exception:
        legal_plan = None

    entity_info = extract_entities(original_user_query, history)
    query_type = entity_info["intent"]
    if legal_plan is not None:
        query_type = legal_plan.kb_query_type
        if legal_plan.sections:
            entity_info["entities"] = legal_plan.sections
        if legal_plan.typed_entities:
            entity_info["typed_entities"] = legal_plan.typed_entities
        entity_info["intent"] = query_type

    profile = classify_intent(original_user_query, history)
    try:
        from backend.app.core.adaptive_learning import enhance_intent_profile

        profile = enhance_intent_profile(user_id, "knowledge_base", profile, query)
    except Exception:
        pass
    try:
        from backend.app.core.learning_engine import prepare_kb_query

        effective_q, learn_signals = prepare_kb_query(user_id, query, profile)
        if effective_q and len(effective_q) > len(query):
            profile.expanded_query = effective_q
        profile.signals["learning_signals"] = learn_signals
        if learn_signals.get("memory_hint"):
            profile.signals["memory_hint"] = learn_signals["memory_hint"]
    except Exception:
        pass
    try:
        from backend.app.core.user_memory import build_memory_context, extract_facts_from_message

        extract_facts_from_message(user_id, query)
        mem = build_memory_context(user_id, thread_id, "knowledge_base", query=query)
        profile.signals["user_memory"] = mem.get("memory_block", "")
        profile.signals["persona_prompt"] = mem.get("persona_prompt", "")
        profile.signals["past_chat_block"] = mem.get("past_chat_block", "")
        profile.signals["memory_enabled"] = mem.get("enabled", True)
        try:
            from answer_orchestrator import _attach_learning_preferences

            _attach_learning_preferences(profile, original_user_query, user_id, session_mem)
        except Exception:
            pass
        try:
            from backend.app.core.chat_conversation_rag import (
                format_past_chat_context,
                search_past_chats,
                should_search_past_chats,
            )
            from backend.app.core.prompt_budget import budget_past_chat

            if should_search_past_chats(query):
                hits = search_past_chats(user_id, query, k=3)
                pc = budget_past_chat(format_past_chat_context(hits))
                if pc:
                    profile.signals["past_chat_block"] = (
                        profile.signals.get("past_chat_block", "") + "\n" + pc
                    ).strip()
        except Exception:
            pass
    except Exception:
        pass
    profile.signals.update(query_type_signals(query_type, original_user_query))
    profile.signals["original_query"] = original_user_query
    profile.signals["retrieval_query"] = query
    profile.signals["entities"] = entity_info["entities"]
    profile.signals["sections"] = list(entity_info["entities"])
    if legal_plan is not None:
        from backend.app.services.legal_query_engine import apply_plan_to_profile

        apply_plan_to_profile(profile, legal_plan, original_user_query)
    primary_sec = _primary_section_for_answer(profile)
    if legal_plan and legal_plan.multi_entity and len(legal_plan.sections) >= 2:
        profile.signals["sections"] = legal_plan.sections
        profile.response_mode = "multi_section"
    elif primary_sec and not (legal_plan and legal_plan.multi_entity):
        profile.signals["primary_section"] = primary_sec
        profile.signals["sections"] = [primary_sec]
    if session_mem:
        profile.signals["session_memory"] = session_mem
        try:
            from backend.app.core.kb_query_memory import memory_context_block
            from backend.app.services.followup_detector import is_new_legal_query

            if not is_new_legal_query(original_user_query):
                profile.signals["memory_context_block"] = memory_context_block(session_mem)
        except Exception:
            pass
    profile.signals["entities"] = entity_info["entities"]
    profile.signals["typed_entities"] = entity_info.get("typed_entities") or []
    if legal_parse:
        profile.signals["legal_parse"] = legal_parse.to_dict()
        if legal_parse.signals.get("sections"):
            profile.signals.setdefault("sections", legal_parse.signals["sections"])
        if legal_parse.retrieval_mode == "statute":
            profile.signals["statute_query"] = True

    if query_type == QueryType.COMPARISON:
        profile.primary = QueryIntent.COMPARISON
        typed = (
            (legal_plan.typed_entities if legal_plan else None)
            or entity_info.get("typed_entities")
            or []
        )
        if len(typed) >= 2:
            profile.signals["typed_entities"] = typed
            profile.signals["sections"] = [
                f"{e.get('type', '')} {e.get('section', '')}".strip() for e in typed
            ]
            profile.response_mode = "structured"
        elif len(entity_info["entities"]) >= 2:
            profile.signals["sections"] = entity_info["entities"]
            profile.response_mode = "table"
        if legal_plan and not legal_plan.mapping_mode:
            profile.signals["mapping_mode"] = False
            profile.signals["comparison_same_law"] = True

    try:
        from backend.app.core.kb_doc_scope import resolve_document_scope

        early_scope = resolve_document_scope(
            user_id,
            original_user_query,
            index_dir,
            thread_id=thread_id,
            history=history,
        )
        profile.signals["document_scope"] = early_scope
    except Exception:
        early_scope = profile.signals.get("document_scope") or {}

    if query_type == QueryType.ENTITY_LOOKUP:
        entity_answer = _try_entity_lookup_answer(
            user_id,
            original_user_query,
            early_scope,
            index_dir,
        )
        if entity_answer:
            try:
                from backend.app.core.adaptive_learning import record_interaction

                record_interaction(
                    user_id,
                    "knowledge_base",
                    original_user_query,
                    answer=entity_answer,
                    intent="entity_lookup",
                    found_in_kb=True,
                    best_score=0.9,
                    chunks=[],
                    thread_id=thread_id or "",
                    implicit_signal="entity_lookup_fast",
                )
            except Exception:
                pass
            return entity_answer, [], {
                "found": True,
                "found_reason": "entity_lookup_fast",
                "document_scope": early_scope,
                "query_type": query_type.value,
            }

    chunks, entities, diag = kb_retrieve(
        user_id, query, history, index_dir, profile, query_type, entity_info, thread_id=thread_id
    )

    scope = profile.signals.get("document_scope") or {}

    if query_type == QueryType.ENTITY_LOOKUP:
        entity_answer = _try_entity_lookup_answer(
            user_id,
            original_user_query,
            scope,
            index_dir,
            chunks=chunks,
        )
        if entity_answer:
            diag["found"] = True
            diag["found_reason"] = "entity_lookup_structured"
            return entity_answer, chunks, diag

    if scope.get("strict"):
        from backend.app.core.kb_doc_scope import reject_cross_document_contamination

        ok, reason = reject_cross_document_contamination(original_user_query, chunks, scope)
        if not ok:
            diag["contamination_rejected"] = reason
            chunks = []

    entity_list = entities if isinstance(entities, list) else []
    from kb_rag_decision import MIN_RETRIEVAL_THRESHOLD, threshold_for_query

    threshold = threshold_for_query(query, query_type.value if query_type else None)
    try:
        from backend.app.core.adaptive_learning import get_adaptive_threshold

        threshold = get_adaptive_threshold(user_id, "knowledge_base", base=threshold)
    except Exception:
        pass
    found, best_score, decision, eval_debug = evaluate_retrieval(
        query,
        chunks,
        entities=entity_info["entities"],
        query_type=query_type.value,
        extracted_count=len(entity_list),
        threshold=threshold,
    )
    diag["found"] = found
    diag["best_score"] = best_score
    diag["eval"] = eval_debug

    if not found and entity_list and query_type in {
        QueryType.LIST_EXTRACTION,
        QueryType.SUMMARY,
        QueryType.TOPIC_QUERY,
        QueryType.LAW_REPLACEMENT,
    }:
        found = True
        diag["found"] = True
        diag["found_reason"] = "document_entities"

    if not found and query_type == QueryType.LAW_REPLACEMENT and chunks:
        try:
            from kb_legal_query_rewrite import chunk_matches_law_query

            if any(chunk_matches_law_query(c.get("content", ""), query) for c in chunks[:8]):
                found = True
                diag["found"] = True
                diag["found_reason"] = "law_mapping_chunks"
        except Exception:
            pass

    if not found and query_type == QueryType.ENTITY_LOOKUP:
        try:
            from contract_entity_extractor import answer_entity_lookup
            from backend.app.core.document_entities import load_document_entities

            scope = profile.signals.get("document_scope") or {}
            stored = None
            if scope.get("doc_id"):
                stored = load_document_entities(user_id, document_id=scope.get("doc_id", ""))
            if stored:
                answer = answer_entity_lookup(original_user_query, stored, stored.get("_document_type", ""))
                if answer:
                    found = True
                    diag["found"] = True
                    diag["found_reason"] = "stored_entities"
                    normalized = answer
                    return normalized, chunks, diag
        except Exception:
            pass

    if not found:
        try:
            from backend.app.core.adaptive_learning import record_interaction
            from backend.app.core.learning_engine import rescue_broken_kb

            rescued = rescue_broken_kb(
                user_id,
                query,
                history=history,
                index_dir=index_dir,
                profile=profile,
                query_type=query_type,
                entity_info=entity_info,
                prior_chunks=chunks,
                diag=diag,
            )
            if rescued:
                answer, rescue_chunks, rescue_diag = rescued
                diag.update(rescue_diag)
                try:
                    from backend.app.core.learning_engine import learn_from_kb_success

                    learn_from_kb_success(
                        user_id, query, answer, rescue_chunks,
                        source=diag.get("found_reason", "rescue"),
                        confidence=float(diag.get("rescue_confidence") or 0.78),
                        thread_id=thread_id or "",
                    )
                except Exception:
                    pass
                diag["interaction_id"] = record_interaction(
                    user_id,
                    "knowledge_base",
                    query,
                    answer=answer,
                    intent=str(profile.primary.value if hasattr(profile.primary, "value") else profile.primary),
                    found_in_kb=True,
                    best_score=float(diag.get("best_score") or 0.5),
                    chunks=rescue_chunks,
                    thread_id=thread_id or "",
                    implicit_signal="kb_rescue",
                    learning_handled=True,
                )
                return answer, rescue_chunks, diag

            record_interaction(
                user_id,
                "knowledge_base",
                query,
                answer="",
                intent=str(profile.primary.value if hasattr(profile.primary, "value") else profile.primary),
                found_in_kb=False,
                best_score=float(best_score),
                chunks=chunks,
                thread_id=thread_id or "",
                implicit_signal="not_found",
            )
        except Exception:
            pass
        return "NOT_FOUND_IN_KB", [], diag

    if query_type == QueryType.COMPARISON and len(entity_info["entities"]) >= 2:
        from kb_retrieval import retrieve_chunks_per_entity, section_in_chunk

        matched = sum(
            1
            for sec in entity_info["entities"]
            if any(section_in_chunk(c.get("content", ""), sec) for c in chunks)
        )
        if matched < len(entity_info["entities"]):
            boosted = retrieve_chunks_per_entity(
                index_dir,
                entity_info["entities"],
                query,
                k_per_entity=6,
                max_total=12,
            )
            if boosted:
                chunks = boosted
                diag["pre_generate_boost"] = "per_entity"

    if legal_plan and legal_plan.multi_entity and len(legal_plan.sections) >= 2:
        from kb_retrieval import retrieve_chunks_per_entity

        per_sec = retrieve_chunks_per_entity(
            index_dir,
            legal_plan.sections,
            query,
            k_per_entity=6,
            max_total=14,
        )
        if per_sec:
            chunks = per_sec
            diag["pre_generate_boost"] = "multi_section_per_entity"

    answer = generate_answer(
        query, chunks, profile, history, query_type=query_type, entities=entity_list, user_id=user_id
    )

    if legal_plan is not None:
        try:
            from backend.app.services.legal_query_engine import validate_response_against_plan

            plan_ok, plan_reason = validate_response_against_plan(answer, legal_plan)
            diag["plan_validation"] = {"ok": plan_ok, "reason": plan_reason}
            if not plan_ok and plan_reason in (
                "unwanted_bns_mapping",
                "law_replacement_drift",
                "criminal_drift_in_constitutional",
            ):
                profile.signals["mapping_mode"] = False
                profile.signals["strict_grounding"] = True
                retry = generate_answer(
                    query,
                    chunks,
                    profile,
                    history,
                    query_type=query_type,
                    entities=entity_list,
                    user_id=user_id,
                )
                plan_ok2, _ = validate_response_against_plan(retry, legal_plan)
                if plan_ok2 and retry:
                    answer = retry
                    diag["plan_validation"] = {"ok": True, "reason": "retry"}
        except Exception:
            pass

    ok, reason = validate_answer(
        answer,
        query,
        chunks,
        query_type,
        profile_sections=entity_info["entities"],
        entity_count=len(entity_list),
    )
    diag["validation"] = {"ok": ok, "reason": reason}

    if not ok and (
        reason.startswith("unsupported_") or reason == "unsupported_by_chunks"
    ):
        profile.signals["strict_grounding"] = True
        retry_answer = generate_answer(
            query,
            chunks,
            profile,
            history,
            query_type=query_type,
            entities=entity_list,
            user_id=user_id,
        )
        ok_retry, reason_retry = validate_answer(
            retry_answer,
            query,
            chunks,
            query_type,
            profile_sections=entity_info["entities"],
            entity_count=len(entity_list),
        )
        if ok_retry and retry_answer:
            diag["validation"] = {"ok": True, "reason": f"retry:{reason_retry}"}
            answer = retry_answer
            ok = True
        else:
            diag["validation_retry"] = {"ok": ok_retry, "reason": reason_retry}

    if not ok:
        if query_type == QueryType.COMPARISON and len(entity_info["entities"]) >= 2:
            from kb_retrieval import retrieve_chunks_per_entity

            retry_chunks = retrieve_chunks_per_entity(
                index_dir,
                entity_info["entities"],
                query,
                k_per_entity=6,
                max_total=12,
            )
            if retry_chunks:
                answer2 = generate_answer(
                    query,
                    retry_chunks,
                    profile,
                    history,
                    query_type=query_type,
                    entities=entity_list,
                    user_id=user_id,
                )
                ok2, _ = validate_answer(
                    answer2,
                    query,
                    retry_chunks,
                    query_type,
                    profile_sections=entity_info["entities"],
                    entity_count=len(entity_list),
                )
                if ok2:
                    return answer2, retry_chunks, {**diag, "retried": True}

        if query_type in {QueryType.SUMMARY, QueryType.LIST_EXTRACTION, QueryType.TOPIC_QUERY}:
            from kb_document_scan import search_entire_document

            scan_chunks, scan_entities = search_entire_document(index_dir, query, query_type)
            if scan_entities:
                answer2 = generate_answer(
                    query,
                    scan_chunks,
                    profile,
                    history,
                    query_type=query_type,
                    entities=scan_entities,
                    user_id=user_id,
                )
                ok2, _ = validate_answer(
                    answer2,
                    query,
                    scan_chunks,
                    query_type,
                    profile_sections=entity_info["entities"],
                    entity_count=len(scan_entities),
                )
                if ok2 and answer2:
                    return answer2, scan_chunks, {**diag, "retried": "global_scan"}

        if reason.startswith("comparison_missing") or reason == "wrong_law_it_act_only":
            return "NOT_FOUND_IN_KB", chunks, diag

    if not answer or answer == KB_NOT_FOUND_MESSAGE:
        if entity_list and query_type in {QueryType.SUMMARY, QueryType.LIST_EXTRACTION}:
            answer = generate_answer(
                query, chunks, profile, history, query_type=query_type, entities=entity_list, user_id=user_id
            )
        if not answer or answer == KB_NOT_FOUND_MESSAGE:
            return "NOT_FOUND_IN_KB", chunks, diag

    try:
        from backend.app.core.kb_strict_policy import finalize_kb_answer

        answer = finalize_kb_answer(answer, query, chunks, query_type=query_type)
    except Exception:
        pass

    try:
        from backend.app.core.adaptive_learning import record_interaction

        diag["interaction_id"] = record_interaction(
            user_id,
            "knowledge_base",
            query,
            answer=answer,
            intent=str(profile.primary.value if hasattr(profile.primary, "value") else profile.primary),
            found_in_kb=True,
            best_score=float(diag.get("best_score") or 0),
            chunks=chunks,
            thread_id=thread_id or "",
            implicit_signal="kb_success",
            learning_handled=True,
        )

        def _bg_kb_learn() -> None:
            try:
                from backend.app.core.learning_engine import learn_from_kb_success

                learn_from_kb_success(
                    user_id,
                    query,
                    answer,
                    chunks,
                    source="kb_success",
                    confidence=min(0.95, 0.65 + float(diag.get("best_score") or 0) * 0.3),
                    thread_id=thread_id or "",
                )
            except Exception:
                pass

        import threading

        threading.Thread(target=_bg_kb_learn, daemon=True, name="kb-learn").start()
    except Exception:
        pass

    try:
        from backend.app.services.answer_validator import validate_and_clean_answer
        from backend.app.services.response_formatter import format_legal_response

        parse_dict = profile.signals.get("legal_parse") or {}
        vr = validate_and_clean_answer(
            answer,
            query,
            chunks,
            query_type=query_type,
            intent=parse_dict.get("intent", "general"),
            parse=parse_dict,
            strict_grounded=True,
            profile_sections=entity_info["entities"],
            entity_count=len(entity_list),
        )
        if vr.ok:
            answer = vr.answer
        elif vr.should_retry_retrieval and query_type == QueryType.COMPARISON:
            from kb_compare_engine import retrieve_for_comparison

            typed = entity_info.get("typed_entities") or []
            if len(typed) >= 2:
                retry = retrieve_for_comparison(typed, index_dir, query)
                if retry:
                    answer2 = generate_answer(
                        query, retry, profile, history, query_type=query_type, entities=entity_list
                    )
                    vr2 = validate_and_clean_answer(
                        answer2, query, retry, query_type=query_type,
                        intent=parse_dict.get("intent", "comparison"), parse=parse_dict,
                        profile_sections=entity_info["entities"], entity_count=len(entity_list),
                    )
                    if vr2.ok:
                        answer, chunks = vr2.answer, retry
        answer = format_legal_response(
            answer,
            intent=parse_dict.get("intent", "general"),
            parse=parse_dict,
        )
    except Exception:
        pass

    return answer, chunks, diag
