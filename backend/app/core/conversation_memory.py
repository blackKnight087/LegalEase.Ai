"""Session conversation memory — wraps conversation_context for API use."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from conversation_context import (
    build_conversation_state,
    enrich_query_with_context,
    extract_case_title_from_text,
    extract_law_from_text,
    extract_sections_from_text,
    merge_retrieval_query,
)

from backend.app.core.session_store import get_session, set_session


def get_session_legal_memory(session_id: str) -> Dict[str, Any]:
    """GPT-style session memory for follow-up resolution."""
    sess = get_session(session_id) or {}
    mem = dict(sess.get("legal_memory") or {})
    state = sess.get("state") or {}
    if not mem.get("last_section") and state.get("active_sections"):
        mem.setdefault("last_section", state["active_sections"][0])
    if not mem.get("last_law") and state.get("active_law"):
        mem.setdefault("last_law", str(state["active_law"]).upper())
    if not mem.get("last_topic") and state.get("active_topic"):
        mem.setdefault("last_topic", state["active_topic"])
    if not mem.get("last_case") and state.get("active_case"):
        mem.setdefault("last_case", state["active_case"])
    return mem


def update_session_legal_memory(
    session_id: str,
    *,
    query: str = "",
    parse: Optional[Dict[str, Any]] = None,
    mode: str = "",
    answer: str = "",
    source_meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist last legal topic after each turn."""
    sess = get_session(session_id)
    if not sess:
        sess = {"history": [], "state": {}}
    mem = dict(sess.get("legal_memory") or {})

    if parse:
        if parse.get("section"):
            mem["last_section"] = str(parse["section"]).lower()
            if parse.get("intent") == "section_lookup":
                mem.pop("last_entities", None)
        if parse.get("law"):
            mem["last_law"] = str(parse["law"]).upper()
        if parse.get("case_name"):
            mem["last_case"] = parse["case_name"]
        if parse.get("entities") and parse.get("intent") == "comparison":
            mem["last_entities"] = parse["entities"]
        if parse.get("intent"):
            mem["last_topic"] = (
                f"{parse.get('law', '')} Section {parse.get('section', '').upper()}".strip()
                if parse.get("section")
                else parse.get("case_name") or parse.get("intent", "")
            )
    elif query:
        ql = (query or "").lower()
        if re.search(
            r"\b(?:fundamental|constitutional|nda|agreement|contract|witness|"
            r"medical|blood pressure|financial|policy|compliance)\b",
            ql,
        ):
            mem["last_domain"] = "document"
            mem["last_topic"] = query[:200]
            if re.search(r"\b(?:fundamental|constitutional)\b", ql):
                mem["last_domain"] = "constitution"
        try:
            from backend.app.core.constitutional_concept_map import resolve_article, resolve_topic

            art = resolve_article(query)
            if art:
                mem["last_domain"] = "constitution"
                mem["last_constitutional_article"] = art
                mem["last_topic"] = resolve_topic(query) or f"Article {art}"
                mem.pop("last_section", None)
                mem["last_law"] = "CONSTITUTION"
        except ImportError:
            art = None
        if not mem.get("last_constitutional_article"):
            case_title = extract_case_title_from_text(query)
            if case_title:
                mem["last_case"] = case_title
                mem["last_topic"] = case_title
                mem.pop("last_section", None)
            else:
                secs = extract_sections_from_text(query, include_articles=False)
                law = extract_law_from_text(query)
                if secs and not re.search(r"\barticle\s+\d", (query or "").lower()):
                    mem["last_section"] = secs[0]
                    mem["last_law"] = (law or mem.get("last_law") or "ipc").upper()
                    mem["last_topic"] = f"{mem['last_law']} Section {secs[0].upper()}"
                elif law:
                    mem["last_law"] = law.upper()

    if source_meta:
        fn = str(
            source_meta.get("filename")
            or source_meta.get("source_file")
            or source_meta.get("document")
            or ""
        ).strip()
        if fn:
            mem["last_document"] = fn
            mem["last_filename"] = fn
        sec_meta = source_meta.get("section")
        if sec_meta and not mem.get("last_section"):
            mem["last_section"] = str(sec_meta).lower()

    if mode:
        mem["last_mode"] = mode
    if query:
        mem["last_user_query"] = query[:400]
        case_from_query = extract_case_title_from_text(query)
        if case_from_query:
            mem["last_case"] = case_from_query
            mem["last_topic"] = case_from_query
            mem.pop("last_section", None)
    if answer:
        mem["last_assistant_summary"] = answer[:800]
        if mem.get("last_case") and len((answer or "").strip()) < 200:
            pass
        elif mem.get("last_user_query") and extract_case_title_from_text(
            str(mem.get("last_user_query") or "")
        ):
            mem["last_topic"] = mem.get("last_case") or mem.get("last_topic")
        al = answer.lower()
        art_m = re.search(r"\barticle\s+(\d{1,3})\b", al)
        if art_m and (
            "right to" in al
            or "constitutional" in al
            or "fundamental" in al
            or parse.get("intent") == "constitutional"
        ):
            mem["last_domain"] = "constitution"
            mem["last_constitutional_article"] = art_m.group(1).lower()
            mem["last_topic"] = mem.get("last_topic") or f"Article {art_m.group(1)}"
            mem.pop("last_section", None)
        elif re.search(r"\bipc\s+section\s+\d", al):
            secs = extract_sections_from_text(answer)
            if secs and (not parse or not parse.get("section")):
                mem.setdefault("last_section", secs[0])
                mem.setdefault(
                    "last_law",
                    (extract_law_from_text(answer) or mem.get("last_law") or "IPC").upper(),
                )
                if not mem.get("last_topic"):
                    mem["last_topic"] = f"{mem.get('last_law', 'IPC')} Section {secs[0].upper()}"
        elif parse and parse.get("section") and parse.get("law", "").lower() not in ("article", ""):
            pass
        else:
            secs = extract_sections_from_text(answer)
            if secs and (not parse or not parse.get("section")):
                if not re.search(r"\barticle\s+\d", al):
                    mem.setdefault("last_section", secs[0])
                    mem.setdefault(
                        "last_law",
                        (extract_law_from_text(answer) or mem.get("last_law") or "IPC").upper(),
                    )

    sess["legal_memory"] = mem
    set_session(session_id, sess)


def _resolve_follow_up_rules(question: str, session_memory: Dict[str, Any]) -> str:
    """Rule-based follow-up expansion (original logic)."""
    q = (question or "").strip()
    ql = q.lower()
    sec = str(session_memory.get("last_section") or "").lower()
    law = str(session_memory.get("last_law") or "IPC").upper()
    topic = session_memory.get("last_topic") or (f"{law} Section {sec.upper()}" if sec else "")
    last_case = str(session_memory.get("last_case") or "").strip()

    const_art = str(session_memory.get("last_constitutional_article") or "").lower()
    if session_memory.get("last_domain") == "constitution" or const_art:
        try:
            from backend.app.core.constitutional_concept_map import (
                ARTICLE_TITLES,
                expand_constitutional_query,
                is_constitutional_follow_up,
            )

            if is_constitutional_follow_up(q):
                title = ARTICLE_TITLES.get(const_art, topic or f"Article {const_art}")
                if any(c in ql for c in ("summarize", "summary", "key point", "main point")):
                    return expand_constitutional_query(f"Explain {title}")
                if any(c in ql for c in ("simple", "beginner", "plain", "layman", "eli5")):
                    return expand_constitutional_query(f"Explain {title} in simple language")
                if any(c in ql for c in ("meaning", "purpose", "what does")):
                    return expand_constitutional_query(f"Explain {title}")
                return expand_constitutional_query(f"{q} regarding {title}")
        except ImportError:
            pass

    if not sec and not topic and not last_case:
        return q

    if last_case and len(q.split()) <= 12:
        try:
            from backend.app.core.case_entity_resolver import extract_case_parties

            a, b = extract_case_parties(q)
            if a and b:
                return q
        except ImportError:
            pass
        ql = q.lower()
        if re.match(r"^explain\s*[.!?]?\s*$", ql):
            return (
                f"Explain the case {last_case} in detail using only the uploaded "
                f"documents, including facts, parties, legal issues, and court observations."
            )
        if any(c in ql for c in ("simple", "beginner", "plain", "eli5", "layman")):
            return f"Explain the case {last_case} in simple language."
        if any(c in ql for c in ("more", "elaborate", "detail", "deeper", "summary", "summarize")):
            return f"Provide a detailed explanation of the case {last_case}."
        if any(c in ql for c in ("example", "illustrate")):
            return f"Give examples related to the case {last_case}."
        if any(
            c in ql
            for c in (
                "it", "that", "this", "same", "above", "continue", "details",
            )
        ):
            return f"{q} (regarding the case: {last_case})"
        if "explain" in ql:
            try:
                from backend.app.core.case_entity_resolver import is_case_style_query

                if is_case_style_query(q):
                    return q
            except ImportError:
                pass
            return f"{q} (regarding the case: {last_case})"

    try:
        from kb_query_types import is_bare_section_query, is_case_query

        if is_bare_section_query(q) or is_case_query(q):
            return q
    except ImportError:
        pass

    current_secs = extract_sections_from_text(q)
    try:
        from kb_rag_decision import extract_query_sections

        for s in extract_query_sections(q):
            if s and s not in current_secs:
                current_secs.append(s)
    except Exception:
        pass

    if current_secs:
        # User named an explicit section — never substitute session's old section.
        target_sec = current_secs[0]
        if any(
            c in ql
            for c in ("punishment", "penalty", "sentence", "fine", "imprisonment", "applies")
        ):
            return f"What is the punishment prescribed for {law} Section {target_sec.upper()}?"
        return q

    if any(c in ql for c in ("punishment", "penalty", "sentence", "fine", "imprisonment", "applies")):
        return f"What is the punishment prescribed for {law} Section {sec.upper()}?"

    if any(c in ql for c in ("example", "illustrate", "scenario")):
        return f"Give a practical example of {law} Section {sec.upper()}."

    if any(c in ql for c in ("simple", "beginner", "plain", "eli5", "layman")):
        return f"Explain {topic} in simple language."

    if any(c in ql for c in ("more", "elaborate", "detail", "deeper")):
        return f"Provide a detailed explanation of {topic}."

    if "compare" in ql or "difference" in ql or " vs " in ql:
        nums = extract_sections_from_text(q)
        if len(nums) >= 2:
            return (
                f"Compare {law} Section {nums[0].upper()} and Section {nums[1].upper()}."
            )
        if nums and sec:
            return f"Compare {law} Section {sec.upper()} with Section {nums[0].upper()}."
        entities = session_memory.get("last_entities") or []
        if len(entities) >= 2:
            a, b = entities[0], entities[1]
            return (
                f"Compare {a.get('law', law)} Section {a.get('section', '').upper()} "
                f"and {b.get('law', '')} Section {b.get('section', '').upper()}."
            )

    if len(q.split()) <= 10 and any(
        c in ql
        for c in (
            "it", "that", "this", "same", "above", "punishment", "penalty",
            "compare", "difference", "simple", "more", "example", "detail", "details",
            "explain", "elaborate", "continue",
        )
    ):
        try:
            from backend.app.core.kb_context_resolver import classify_retrieval_context

            rctx = classify_retrieval_context(q, session_memory)
            if rctx.get("continuity_allowed"):
                return f"{q} (regarding {topic})"
        except ImportError:
            return f"{q} (regarding {topic})"
        return q

    return q


def resolve_follow_up_query(question: str, session_memory: Dict[str, Any]) -> str:
    """
    Expand vague follow-ups using semantic intent + session memory.
    """
    q_in = (question or "").strip()
    try:
        from backend.app.services.followup_detector import is_new_legal_query

        if is_new_legal_query(q_in):
            # region agent log
            try:
                from backend.app.core.debug_session_log import debug_log

                debug_log(
                    "H1",
                    "conversation_memory.py:resolve_follow_up_query",
                    "new_legal_query_skip_expand",
                    {"query": q_in[:120], "last_section": session_memory.get("last_section")},
                    run_id="post-fix3",
                )
            except Exception:
                pass
            # endregion
            return q_in
    except ImportError:
        pass

    from backend.app.core.follow_up_intent import classify_follow_up_intent, expand_query_with_intent

    try:
        from backend.app.core.kb_context_resolver import classify_retrieval_context

        from conversation_context import is_meta_follow_up

        rctx = classify_retrieval_context(q_in, session_memory)
        meta = is_meta_follow_up(q_in)
        if rctx.get("topic_shift") and not meta:
            return q_in
        if rctx.get("fresh_retrieval") and not meta and not (
            "punishment" in q_in.lower() or "penalty" in q_in.lower()
        ):
            return q_in
    except ImportError:
        pass

    intent_info = classify_follow_up_intent(q_in, session_memory)
    expanded, _ = expand_query_with_intent(q_in, session_memory, intent_info)
    if expanded and expanded != q_in:
        out = expanded
    else:
        out = _resolve_follow_up_rules(q_in, session_memory)
    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "H1",
            "conversation_memory.py:resolve_follow_up_query",
            "follow_up_resolved",
            {
                "query_in": q_in[:120],
                "query_out": out[:160],
                "last_section": session_memory.get("last_section"),
                "intent": intent_info.get("intent"),
            },
            run_id="post-fix3",
        )
    except Exception:
        pass
    # endregion
    return out


def enrich_session_from_thread(
    session_memory: Dict[str, Any],
    thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Merge persisted thread summary into session memory for cross-mode follow-ups."""
    mem = dict(session_memory or {})
    if not thread_id:
        return mem
    try:
        from backend.app.core.user_memory import get_thread_summary

        ts = get_thread_summary(thread_id)
        if ts.get("last_query") and not mem.get("last_user_query"):
            mem["last_user_query"] = ts["last_query"]
        if ts.get("topics") and not mem.get("last_topic"):
            mem["last_topic"] = ", ".join(ts["topics"][:3])
        if ts.get("summary") and not mem.get("thread_summary"):
            mem["thread_summary"] = ts["summary"][:600]
    except Exception:
        pass
    return mem


def resolve_unified_follow_up(
    question: str,
    session_id: Optional[str] = None,
    history: Optional[List[Dict]] = None,
    thread_id: Optional[str] = None,
    mode: str = "",
) -> str:
    """
    Cross-mode follow-up resolution — KB session memory + web conversation + thread summary.
    """
    q = (question or "").strip()
    if not q:
        return q

    try:
        from backend.app.services.followup_detector import is_new_legal_query

        if is_new_legal_query(q):
            return q
    except ImportError:
        pass

    try:
        from legal_web_query import is_conversational_feedback

        if is_conversational_feedback(q, history):
            return q
    except ImportError:
        pass

    session_mem = get_session_legal_memory(session_id) if session_id else {}
    if mode in ("web_search", "open_law"):
        try:
            from legal_web_query import resolve_web_conversation_query, is_self_contained_web_query

            if is_self_contained_web_query(q):
                return q
            return resolve_web_conversation_query(q, history, session_mem)
        except ImportError:
            return q

    session_mem = enrich_session_from_thread(session_mem, thread_id)
    resolved = resolve_follow_up_query(q, session_mem)

    if mode in ("deep_case", "hybrid"):
        try:
            from legal_web_query import resolve_web_conversation_query

            resolved = resolve_web_conversation_query(resolved, history, session_mem)
        except ImportError:
            pass

    return resolved


def get_or_create_session(session_id: Optional[str] = None) -> str:
    sid = session_id or str(uuid4())
    data = get_session(sid)
    if not data or "history" not in data:
        set_session(sid, {"history": [], "state": {}})
    return sid


def get_session_history(session_id: str) -> List[Dict[str, str]]:
    return list(get_session(session_id).get("history", []))


def append_turn(session_id: str, role: str, content: str) -> None:
    sess = get_session(session_id)
    if not sess:
        sess = {"history": [], "state": {}}
    sess["history"].append({"role": role, "content": content})
    sess["history"] = sess["history"][-20:]
    state = build_conversation_state(sess["history"])
    sess["state"] = {
        "active_topic": state.active_topic,
        "active_sections": state.active_sections,
        "active_law": state.active_law,
        "active_case": state.active_case,
        "compared_sections": state.compared_sections,
        "answer_mode": state.answer_mode,
    }
    set_session(session_id, sess)


def get_session_state(session_id: str) -> Dict[str, Any]:
    return dict(get_session(session_id).get("state", {}))


def enrich_query(
    question: str,
    session_id: Optional[str] = None,
    history: Optional[List[Dict]] = None,
) -> str:
    hist = history if history is not None else (
        get_session_history(session_id) if session_id else []
    )
    return enrich_query_with_context(question, hist)


def merge_query(
    question: str,
    session_id: Optional[str] = None,
    history: Optional[List[Dict]] = None,
    intent_expanded: str = "",
) -> str:
    hist = history if history is not None else (
        get_session_history(session_id) if session_id else []
    )
    return merge_retrieval_query(question, hist, intent_expanded=intent_expanded)
