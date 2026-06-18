"""
Question-aware KB answering layer.

Pipeline: classify query → select/rank chunks → extract facts → compose answer → quality gate.
Answers must address the user's question, not echo the first retrieved chunk.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

_STOP = frozenset(
    {
        "what", "when", "where", "which", "explain", "define", "about", "under",
        "the", "and", "for", "from", "with", "your", "this", "that", "document",
        "documents", "tell", "describe", "please", "does", "mean", "section",
        "summarize", "summary", "list", "show", "give", "say", "report", "case",
    }
)


class KBQuestionKind(str, Enum):
    DEFINITION = "definition"
    SUMMARY = "summary"
    CASE_EXPLANATION = "case_explanation"
    LIST_REQUEST = "list_request"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    CLAUSE_EXTRACTION = "clause_extraction"
    PERSON_LOOKUP = "person_lookup"
    EVIDENCE_LOOKUP = "evidence_lookup"
    CONSTITUTIONAL_PROVISION = "constitutional_provision"
    LEGAL_SECTION = "legal_section"
    GENERAL_QUESTION = "general_question"


_INTENT_WHO = re.compile(r"\bwho\b", re.I)
_INTENT_WHEN = re.compile(r"\bwhen\b", re.I)
_INTENT_WHY = re.compile(r"\bwhy\b", re.I)
_INTENT_HOW = re.compile(r"\bhow\b", re.I)
_INTENT_LIST = re.compile(
    r"\b(?:list|enumerate|name\s+(?:the|five|5)|what are the|give me the)\b",
    re.I,
)
_INTENT_SUMMARIZE = re.compile(
    r"\b(?:summarize|summarise|summary|overview|gist|key points)\b",
    re.I,
)
_INTENT_COMPARE = re.compile(
    r"\b(?:compare|comparison|difference|versus|vs\.?|between)\b",
    re.I,
)
_INTENT_EXPLAIN = re.compile(
    r"\b(?:explain|describe|walk me through|break down|what is|what's)\b",
    re.I,
)

_NDA_SAMPLE_RE = re.compile(
    r"\b(?:sample\s+nda|nda\s+agreement|sample\s+non[- ]?disclosure|"
    r"sample\s+.*\s+agreement)\b",
    re.I,
)

_CLAUSE_LABELS = (
    ("parties", r"\bpart(?:y|ies)\b"),
    ("confidential_information", r"\bconfidential\b"),
    ("term", r"\b(?:term|duration|effective)\b"),
    ("termination", r"\bterminat"),
    ("governing_law", r"\bgoverning\s+law\b"),
    ("obligations", r"\b(?:obligation|shall\s+not|must\s+not)\b"),
)


def detect_query_intents(query: str) -> List[str]:
    """Surface intents: explain, summarize, list, compare, who, what, when, why, how."""
    q = query or ""
    intents: List[str] = []
    if _INTENT_EXPLAIN.search(q):
        intents.append("explain")
    if _INTENT_SUMMARIZE.search(q):
        intents.append("summarize")
    if _INTENT_LIST.search(q):
        intents.append("list")
    if _INTENT_COMPARE.search(q):
        intents.append("compare")
    if _INTENT_WHO.search(q):
        intents.append("who")
    if re.search(r"\bwhat\b", q, re.I):
        intents.append("what")
    if _INTENT_WHEN.search(q):
        intents.append("when")
    if _INTENT_WHY.search(q):
        intents.append("why")
    if _INTENT_HOW.search(q):
        intents.append("how")
    return intents


def classify_kb_question(query: str) -> KBQuestionKind:
    """Map natural language to answer-shaping category."""
    q = (query or "").strip()
    if not q:
        return KBQuestionKind.GENERAL_QUESTION

    try:
        from kb_query_types import QueryType, detect_query_type, is_case_query

        qt = detect_query_type(q)
        if qt == QueryType.COMPARISON:
            return KBQuestionKind.COMPARISON
        if qt in (QueryType.SECTION_LOOKUP, QueryType.SECTION_EXPLANATION, QueryType.PUNISHMENT_QUERY):
            return KBQuestionKind.LEGAL_SECTION
        if qt == QueryType.LIST_EXTRACTION:
            return KBQuestionKind.LIST_REQUEST
        if qt == QueryType.SUMMARY:
            return KBQuestionKind.SUMMARY
        if qt == QueryType.ENTITY_LOOKUP:
            return KBQuestionKind.CLAUSE_EXTRACTION
        if qt == QueryType.PAGE_LOOKUP:
            return KBQuestionKind.EVIDENCE_LOOKUP
        if is_case_query(q):
            return KBQuestionKind.CASE_EXPLANATION
    except ImportError:
        pass

    try:
        from backend.app.core.constitutional_concept_map import (
            is_constitutional_rights_list_query,
            is_constitutional_query,
            resolve_article,
        )

        if is_constitutional_rights_list_query(q):
            return KBQuestionKind.LIST_REQUEST
        if is_constitutional_query(q):
            if resolve_article(q) and not _INTENT_LIST.search(q):
                return KBQuestionKind.CONSTITUTIONAL_PROVISION
            return KBQuestionKind.CONSTITUTIONAL_PROVISION
    except ImportError:
        pass

    try:
        from backend.app.core.kb_landmark_case import is_landmark_case_query

        if is_landmark_case_query(q):
            return KBQuestionKind.CASE_EXPLANATION
    except ImportError:
        pass

    if _is_contract_clause_query(q):
        return KBQuestionKind.CLAUSE_EXTRACTION

    if _INTENT_COMPARE.search(q):
        return KBQuestionKind.COMPARISON

    if _INTENT_LIST.search(q):
        return KBQuestionKind.LIST_REQUEST

    if _INTENT_SUMMARIZE.search(q):
        return KBQuestionKind.SUMMARY

    if _INTENT_WHO.search(q):
        return KBQuestionKind.PERSON_LOOKUP

    if re.search(r"\b(?:timeline|chronolog|sequence of events|hearing\s+\d)\b", q, re.I):
        return KBQuestionKind.TIMELINE

    if _INTENT_EXPLAIN.search(q) and re.search(r"\b(?:mean|definition|define)\b", q, re.I):
        return KBQuestionKind.DEFINITION

    if re.search(r"\b(?:section|ipc|bns|article)\s+\d", q, re.I):
        return KBQuestionKind.LEGAL_SECTION

    if _INTENT_EXPLAIN.search(q):
        return KBQuestionKind.GENERAL_QUESTION

    return KBQuestionKind.GENERAL_QUESTION


def _is_contract_clause_query(query: str) -> bool:
    try:
        from document_classifier import is_contract_topic_query

        if is_contract_topic_query(query):
            return True
    except ImportError:
        pass
    ql = (query or "").lower()
    if _NDA_SAMPLE_RE.search(ql):
        return True
    return bool(
        re.search(
            r"\b(?:nda|non[- ]?disclosure|confidential|disclosing\s+party|"
            r"receiving\s+party|agreement|contract)\b",
            ql,
        )
    )


def _query_terms(query: str) -> List[str]:
    return [
        w
        for w in re.findall(r"[a-z0-9]{3,}", (query or "").lower())
        if w not in _STOP
    ]


def select_chunks_for_question(
    query: str,
    chunks: Sequence[Dict[str, Any]],
    *,
    kind: Optional[KBQuestionKind] = None,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Re-rank chunks for the question — constitutional lists must not prefer case narratives."""
    if not chunks:
        return []
    kind = kind or classify_kb_question(query)
    terms = _query_terms(query)

    if kind in (KBQuestionKind.LIST_REQUEST, KBQuestionKind.CONSTITUTIONAL_PROVISION):
        try:
            from answer_orchestrator import _rank_constitutional_chunks

            return _rank_constitutional_chunks(list(chunks))[:top_k]
        except ImportError:
            pass

    if kind == KBQuestionKind.CASE_EXPLANATION:
        try:
            from backend.app.core.kb_case_context_lock import lock_chunks_to_query

            return lock_chunks_to_query(query, list(chunks))[:top_k]
        except ImportError:
            pass

    if kind == KBQuestionKind.CLAUSE_EXTRACTION:
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for ch in chunks:
            body = (ch.get("content") or "").lower()
            score = float(ch.get("final_score") or ch.get("hybrid_score") or 0)
            if re.search(r"\b(?:nda|disclosing\s+party|confidential)\b", body):
                score += 15.0
            if terms:
                score += sum(2.0 for t in terms[:5] if t in body)
            scored.append((score, ch))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k]]

    if not terms:
        return list(chunks)[:top_k]

    scored = []
    for ch in chunks:
        body = (ch.get("content") or "").lower()
        base = float(ch.get("final_score") or ch.get("hybrid_score") or 0)
        hits = sum(1.5 for t in terms if t in body)
        scored.append((base + hits, ch))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_k]]


def extract_facts_from_chunks(
    query: str,
    chunks: Sequence[Dict[str, Any]],
    *,
    kind: Optional[KBQuestionKind] = None,
) -> Dict[str, Any]:
    """Structured facts from excerpts — not raw chunk text."""
    kind = kind or classify_kb_question(query)
    selected = select_chunks_for_question(query, chunks, kind=kind)
    combined = "\n".join((c.get("content") or "") for c in selected)

    facts: Dict[str, Any] = {
        "kind": kind.value,
        "intents": detect_query_intents(query),
        "chunks": selected,
        "combined_text": combined,
        "rights": [],
        "landmark": {},
        "clauses": {},
        "list_items": [],
        "narrative": "",
    }

    if kind in (KBQuestionKind.LIST_REQUEST, KBQuestionKind.CONSTITUTIONAL_PROVISION):
        try:
            from backend.app.core.constitutional_concept_map import (
                extract_constitutional_rights_block,
                is_constitutional_rights_list_query,
            )

            block = combined
            if is_constitutional_rights_list_query(query):
                block = extract_constitutional_rights_block(combined) or combined
            for m in re.finditer(
                r"(Right\s+(?:to|against)\s+[^,()]+?\(\s*Article\s+\d{1,3}\s*\))",
                block,
                re.I,
            ):
                item = m.group(1).strip()
                if item not in facts["rights"]:
                    facts["rights"].append(item)
            for m in re.finditer(
                r"\d+\.\s*(Right[^,(\n]+?\(\s*Article\s+\d{1,3}\s*\))",
                block,
                re.I,
            ):
                item = re.sub(r"^\d+\.\s*", "", m.group(1)).strip()
                if item not in facts["rights"]:
                    facts["rights"].append(item)
        except ImportError:
            pass

    if kind == KBQuestionKind.CASE_EXPLANATION:
        try:
            from backend.app.core.kb_landmark_case import (
                is_landmark_case_query,
                landmark_keys_in_query,
                extract_landmark_passage,
            )

            if is_landmark_case_query(query):
                keys = landmark_keys_in_query(query)
                if keys:
                    key = keys[0]
                    for ch in selected:
                        passage = extract_landmark_passage(ch.get("content") or "", key)
                        if passage and len(passage) > len(facts["landmark"].get("passage", "")):
                            facts["landmark"] = {"key": key, "passage": passage}
        except ImportError:
            pass
        if not facts["landmark"]:
            try:
                from backend.app.core.case_narrative_engine import (
                    extract_case_needles,
                    filter_case_chunks,
                    select_best_case_segment,
                    collect_text_from_chunks,
                )

                needles = extract_case_needles(query)
                filtered = filter_case_chunks(list(selected), needles)
                combined_case = collect_text_from_chunks(filtered or list(selected))
                seg = select_best_case_segment(combined_case, needles) if needles else ""
                facts["narrative"] = seg or combined_case[:2000]
            except ImportError:
                facts["narrative"] = combined[:2000]

    if kind == KBQuestionKind.CLAUSE_EXTRACTION:
        try:
            from backend.app.core.kb_dense_document import extract_nda_clauses_block

            block = ""
            for ch in selected:
                block = extract_nda_clauses_block(ch.get("content") or "") or block
            facts["clauses"]["raw"] = block
            if block:
                facts["clauses"].update(_parse_nda_clauses(block))
        except ImportError:
            pass

    if kind == KBQuestionKind.LEGAL_SECTION:
        try:
            from backend.app.core.kb_document_first import parse_statute_lookup

            sec, law = parse_statute_lookup(query)
            facts["section"] = sec
            facts["law"] = law
        except ImportError:
            pass

    return facts


def _parse_nda_clauses(text: str) -> Dict[str, str]:
    """Pull labeled NDA fields from combined clause text."""
    out: Dict[str, str] = {}
    body = re.sub(r"\s+", " ", (text or "").strip())
    if not body:
        return out

    pm = re.search(r"Parties\s+involved:\s*([^.]+\.)", body, re.I)
    if pm:
        out["parties"] = pm.group(1).strip()

    cm = re.search(r"Confidential\s+information[^.]*\.", body, re.I)
    if cm:
        out["confidential_information"] = cm.group(0).strip()

    tm = re.search(
        r"(?:Term|Duration|Effective\s+date)[^.]*\.",
        body,
        re.I,
    )
    if tm:
        out["term"] = tm.group(0).strip()

    term_m = re.search(r"Upon\s+termination[^.]*\.", body, re.I)
    if term_m:
        out["termination"] = term_m.group(0).strip()

    if not out and len(body) > 60:
        out["summary"] = body[:900]
    return out


def structure_landmark_passage(key: str, passage: str) -> str:
    """Turn a landmark blurb into Case Summary / Issue / Court Decision / Doctrine."""
    text = re.sub(r"\s+", " ", (passage or "").strip())
    if not text:
        return ""

    title = "Kesavananda Bharati Case" if "kesavananda" in key.lower() else f"{key.title()} Case"
    text = re.sub(rf"^{re.escape(title)}\s*", "", text, flags=re.I).strip()
    text = re.sub(rf"^{re.escape(key)}\s*case\s*", "", text, flags=re.I).strip()

    doctrine = ""
    dm = re.search(
        r"(Basic\s+Structure\s+Doctrine[^.]*\.?|doctrine[^.]*\.)",
        text,
        re.I,
    )
    if dm:
        doctrine = dm.group(1).strip()

    court = ""
    cm = re.search(
        r"(The\s+Supreme\s+Court[^.]*\.|Court\s+(?:held|ruled|introduced)[^.]*\.)",
        text,
        re.I,
    )
    if cm:
        court = cm.group(1).strip()

    issue = ""
    if re.search(r"\bchallenged\b", text, re.I):
        im = re.search(r"([^.]+\bchallenged[^.]+\.)", text, re.I)
        if im:
            issue = im.group(1).strip()

    summary = text
    for part in (court, doctrine):
        if part and part in summary:
            summary = summary.replace(part, "").strip()

    lines = [f"## {title}", ""]
    if summary and len(summary) > 25:
        lines.extend(["### Case Summary", summary, ""])
    if issue:
        lines.extend(["### Issue", issue, ""])
    if court:
        lines.extend(["### Court Decision", court, ""])
    if doctrine:
        lines.extend(["### Doctrine", doctrine, ""])
    elif re.search(r"\bbasic\s+structure\b", text, re.I):
        lines.extend(["### Doctrine", "Basic Structure Doctrine (as stated in your document).", ""])

    body = "\n".join(lines).strip()
    return body if len(body) > 80 else ""


def compose_answer_from_facts(
    query: str,
    facts: Dict[str, Any],
    chunks: Sequence[Dict[str, Any]],
) -> str:
    """Build user-facing answer from extracted facts."""
    kind = KBQuestionKind(facts.get("kind") or KBQuestionKind.GENERAL_QUESTION.value)
    intents = facts.get("intents") or []

    if kind in (KBQuestionKind.LIST_REQUEST, KBQuestionKind.CONSTITUTIONAL_PROVISION) and facts.get(
        "rights"
    ):
        try:
            from answer_orchestrator import format_constitutional_rights_answer

            ans = format_constitutional_rights_answer(query, facts.get("chunks") or chunks)
            if ans:
                return ans
        except ImportError:
            pass
        want = 5 if re.search(r"\b(?:five|5)\b", (query or "").lower()) else 0
        title = "Five Constitutional Rights" if want else "Constitutional Rights"
        lines = [f"## {title} (from your uploaded document)", ""]
        limit = want if want else min(8, len(facts["rights"]))
        for i, item in enumerate(facts["rights"][:limit], start=1):
            lines.append(f"{i}. **{item}**")
        return "\n".join(lines)

    if kind == KBQuestionKind.CASE_EXPLANATION and facts.get("landmark"):
        lm = facts["landmark"]
        structured = structure_landmark_passage(lm.get("key", ""), lm.get("passage", ""))
        if structured:
            try:
                from backend.app.core.kb_document_first import format_kb_structured_response

                return format_kb_structured_response(
                    structured,
                    list(facts.get("chunks") or chunks)[:2],
                    confidence=0.9,
                )
            except ImportError:
                return structured
        try:
            from backend.app.core.kb_landmark_case import build_landmark_case_answer

            ans = build_landmark_case_answer(query, chunks)
            if ans:
                return ans
        except ImportError:
            pass

    if kind == KBQuestionKind.CASE_EXPLANATION and facts.get("narrative"):
        try:
            from backend.app.core.case_narrative_engine import build_structured_case_answer
            from answer_orchestrator import polish_kb_response

            body = build_structured_case_answer(query, facts["narrative"])
            if body and len(body.strip()) > 80:
                return polish_kb_response(body, list(chunks))
        except ImportError:
            pass

    if kind == KBQuestionKind.CLAUSE_EXTRACTION:
        try:
            from backend.app.core.kb_dense_document import build_nda_topic_answer

            ans = build_nda_topic_answer(query, chunks)
            if ans:
                return ans
        except ImportError:
            pass
        clauses = facts.get("clauses") or {}
        if clauses.get("raw") or clauses.get("summary"):
            lines = ["## Sample NDA (from your uploaded document)", ""]
            label_map = [
                ("Parties", "parties"),
                ("Confidential Information", "confidential_information"),
                ("Term", "term"),
                ("Termination", "termination"),
                ("Governing Law", "governing_law"),
            ]
            for label, key in label_map:
                val = clauses.get(key)
                if val:
                    lines.append(f"**{label}:** {val}")
            if len(lines) <= 2 and clauses.get("summary"):
                lines.append(clauses["summary"])
            if len(lines) > 2:
                try:
                    from backend.app.core.kb_document_first import format_kb_structured_response

                    return format_kb_structured_response(
                        "\n".join(lines),
                        list(chunks)[:2],
                        confidence=0.88,
                    )
                except ImportError:
                    return "\n".join(lines)

    if kind == KBQuestionKind.LEGAL_SECTION:
        try:
            from backend.app.core.kb_document_first import try_statute_section_lookup_answer

            ans = try_statute_section_lookup_answer(query, list(chunks))
            if ans:
                return ans
        except ImportError:
            pass

    if kind == KBQuestionKind.CONSTITUTIONAL_PROVISION:
        try:
            from backend.app.core.constitutional_concept_map import resolve_article
            from answer_orchestrator import format_constitutional_rights_answer

            if facts.get("rights"):
                return format_constitutional_rights_answer(query, list(chunks))
            art = resolve_article(query)
            if art:
                from backend.app.core.constitutional_concept_map import format_article_answer

                return format_article_answer(art, chunks=list(chunks))
        except ImportError:
            pass

    if "summarize" in intents or kind == KBQuestionKind.SUMMARY:
        return _compose_document_summary(query, facts, chunks)

    if kind == KBQuestionKind.COMPARISON:
        try:
            from kb_compare_engine import format_comparison_pro
            from kb_query_types import extract_entities

            ent = extract_entities(query)
            typed = ent.get("typed_entities") or []
            if len(typed) >= 2 or len(ent.get("entities") or []) >= 2:
                ans = format_comparison_pro(
                    query,
                    list(chunks),
                    typed or [{"section": e} for e in ent.get("entities", [])],
                )
                if ans:
                    return ans
        except ImportError:
            pass

    return ""


def _compose_document_summary(
    query: str,
    facts: Dict[str, Any],
    chunks: Sequence[Dict[str, Any]],
) -> str:
    """Bullet summary from extracted sentences — not raw chunk paste."""
    selected = facts.get("chunks") or select_chunks_for_question(query, chunks)
    terms = _query_terms(query)
    bullets: List[str] = []
    seen: set[str] = set()

    for ch in selected[:6]:
        for sent in re.split(r"(?<=[.!?])\s+", ch.get("content") or ""):
            s = re.sub(r"\s+", " ", sent).strip()
            if len(s) < 35 or len(s) > 400:
                continue
            if terms and not any(t in s.lower() for t in terms[:6]):
                continue
            key = s.lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            bullets.append(f"- {s}")
            if len(bullets) >= 6:
                break
        if len(bullets) >= 6:
            break

    if not bullets:
        return ""

    title = query.strip()[:80] or "Document summary"
    body = f"## Summary: {title}\n\n" + "\n".join(bullets)
    try:
        from backend.app.core.kb_document_first import format_kb_structured_response

        return format_kb_structured_response(body, list(selected)[:2], confidence=0.82)
    except ImportError:
        return body


def is_mostly_chunk_repetition(answer: str, chunks: Sequence[Dict[str, Any]]) -> bool:
    """True when the answer is largely copied from a single excerpt."""
    body = (answer or "").strip()
    if not body or not chunks:
        return False
    if re.search(
        r"##\s+(?:Five\s+)?Constitutional\s+Rights|###\s+(?:Case\s+Summary|Court\s+Decision|Doctrine)",
        body,
        re.I,
    ):
        return False
    if re.search(r"\*\*Parties:\*\*|\*\*Confidential\s+Information:\*\*", body, re.I):
        return False
    try:
        from backend.app.core.kb_explanation_mode import looks_like_chunk_dump

        if looks_like_chunk_dump(body):
            return True
    except ImportError:
        pass

    al = re.sub(r"#+\s*", "", body.lower())
    al = re.sub(r"\*+", "", al)
    al_num = re.sub(r"[^a-z0-9\s]", " ", al)
    al_words = set(w for w in al_num.split() if len(w) > 4)

    for ch in chunks[:3]:
        ctx = (ch.get("content") or "")[:1500].lower()
        ctx_words = set(w for w in re.findall(r"[a-z]{5,}", ctx))
        if not ctx_words or not al_words:
            continue
        overlap = len(al_words & ctx_words) / max(len(al_words), 1)
        if overlap >= 0.82 and len(body) < 600:
            return True
        if overlap >= 0.92:
            return True
    return False


def answer_addresses_question(query: str, answer: str, kind: KBQuestionKind) -> bool:
    """Internal quality gate: did we actually answer the question?"""
    body = (answer or "").strip()
    if not body or len(body) < 50:
        return False

    try:
        from kb_response_state import contains_not_found_phrase

        if contains_not_found_phrase(body):
            return False
    except ImportError:
        pass

    ql = (query or "").lower()
    al = body.lower()

    if kind == KBQuestionKind.LIST_REQUEST:
        if re.search(r"\bright\b", ql) and "article" not in al and "right to" not in al:
            return False
        if re.search(r"\b(?:five|5)\b", ql) and "constitutional" in ql:
            try:
                from backend.app.core.kb_chunk_stitch import count_numbered_rights

                if count_numbered_rights(body) < 5:
                    return False
            except ImportError:
                if body.count("\n") < 4:
                    return False

    if kind == KBQuestionKind.CASE_EXPLANATION:
        terms = _query_terms(query)
        if terms and not any(t in al for t in terms[:3]):
            return False
        if len(body) < 100 and body.count(".") < 1:
            return False
        if re.match(r"^#+\s*.+\s*$", body.strip()) and len(body) < 80:
            return False

    if kind == KBQuestionKind.CLAUSE_EXTRACTION:
        if _is_contract_clause_query(query):
            if not re.search(
                r"\b(?:party|parties|confidential|nda|agreement|termination|disclosing)\b",
                al,
            ):
                return False

    return True


def generate_question_aware_answer(
    query: str,
    chunks: Sequence[Dict[str, Any]],
    *,
    index_dir: Any = None,
    scope: Optional[Dict[str, Any]] = None,
    max_retries: int = 2,
) -> str:
    """
    Primary KB answer entry: classify → extract → compose → validate.
    Returns empty string when chunks cannot support a grounded answer.
    """
    if not chunks:
        return ""

    kind = classify_kb_question(query)
    working = list(chunks)
    if index_dir:
        try:
            from backend.app.core.kb_chunk_stitch import expand_chunks_across_page_breaks

            working = expand_chunks_across_page_breaks(query, working, index_dir)
        except ImportError:
            pass
    selected = select_chunks_for_question(query, working, kind=kind)

    for attempt in range(max_retries):
        facts = extract_facts_from_chunks(query, selected, kind=kind)
        answer = compose_answer_from_facts(query, facts, selected)

        if not answer and attempt == 0:
            try:
                from backend.app.core.kb_dense_document import try_dense_document_answer

                answer = try_dense_document_answer(
                    query,
                    selected,
                    index_dir=index_dir,
                    scope=scope,
                )
            except ImportError:
                pass

        if not answer:
            break

        if is_mostly_chunk_repetition(answer, selected):
            if attempt + 1 < max_retries:
                kind = KBQuestionKind.GENERAL_QUESTION
                continue
            return ""

        if answer_addresses_question(query, answer, kind):
            return answer

        if attempt + 1 < max_retries and index_dir:
            try:
                from backend.app.core.kb_chunk_stitch import (
                    expand_chunks_across_page_breaks,
                    rights_list_truncated,
                )

                combined = "\n".join((c.get("content") or "") for c in selected)
                if rights_list_truncated(combined, query) or (
                    kind == KBQuestionKind.LIST_REQUEST
                    and re.search(r"\b(?:five|5)\b", (query or "").lower())
                ):
                    selected = expand_chunks_across_page_breaks(
                        query, selected, index_dir, window=3
                    )
                    continue
            except ImportError:
                pass

        if attempt + 1 < max_retries:
            continue
        if len(answer.strip()) > 120:
            return answer

    return ""
