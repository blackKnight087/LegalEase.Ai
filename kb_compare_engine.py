"""
Production-grade legal comparison engine for Knowledge Base.

Handles IPC/BNS, CrPC/BNSS, Evidence/BSA section and law-level comparisons.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kb_legal_mapping import (
    LAW_FULL_NAMES,
    LAW_REPLACEMENTS,
    enrich_entities_with_mapping,
    map_section,
    normalize_law_code,
    parse_mapping_row,
    reverse_map_section,
)

_COMPARE_INTENT_RE = re.compile(
    r"\b(compare|comparison|difference|differences|differentiate|distinguish|"
    r"versus|vs\.?|between|old\s+vs\s+new|replaced\s+by|equivalent)\b",
    re.I,
)

_TYPED_ENTITY_RE = re.compile(
    r"\b(IPC|BNS|CrPC|BNSS|BSA|Indian Penal Code|Evidence Act|"
    r"Code of Criminal Procedure)\s*(?:Section|Sec\.?)?\s*(\d{1,4}[a-z]?)\b",
    re.I,
)

_BARE_LAW_RE = re.compile(
    r"\b(IPC|BNS|CrPC|BNSS|BSA|Indian Penal Code|Evidence Act|"
    r"Code of Criminal Procedure)\b",
    re.I,
)

_CHART_BOILERPLATE_RE = re.compile(
    r"^(?:Topic\s*/?\s*Usage|IPC\s+Section\s+BNS\s+Section|"
    r"CrPC\s+Section\s+BNSS\s+Section|Evidence\s+Act\s+Section\s+BSA\s+Section|"
    r"Usage|Topic)\s*$",
    re.I,
)

_MISSING_DETAIL = "The uploaded document does not provide this detail."


@dataclass
class ComparisonBundle:
    """Independent left/right (or N-way) retrieval — never one combined query."""

    entities: List[Dict[str, str]] = field(default_factory=list)
    entity_chunks: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    all_chunks: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def left_entity(self) -> Dict[str, str]:
        return self.entities[0] if self.entities else {}

    @property
    def right_entity(self) -> Dict[str, str]:
        return self.entities[1] if len(self.entities) > 1 else {}

    @property
    def left_chunks(self) -> List[Dict[str, Any]]:
        if not self.entities:
            return []
        key = _entity_key(self.entities[0])
        return self.entity_chunks.get(key, [])

    @property
    def right_chunks(self) -> List[Dict[str, Any]]:
        if len(self.entities) < 2:
            return []
        key = _entity_key(self.entities[1])
        return self.entity_chunks.get(key, [])


def _entity_key(ent: Dict[str, str]) -> str:
    return f"{ent.get('type', 'IPC')}:{ent.get('section', '')}".strip(":")


def extract_all_comparison_entities(query: str) -> List[Dict[str, str]]:
    """Typed IPC/BNS pairs OR multi-section same-law: IPC 299, 300 and 307."""
    nums = re.findall(r"\b(\d{1,4}[a-z]?)\b", query or "")
    law = "BNS" if re.search(r"\bbns\b", query, re.I) else "IPC"

    # Same-law multi-section: Compare IPC 299, 300 and 307
    if is_compare_query(query) and len(nums) >= 3:
        if re.search(r"\bipc\b", query, re.I) and not re.search(r"\bbns\b", query, re.I):
            return [{"type": "IPC", "section": n.lower()} for n in nums[:4]]
        if re.search(r"\bbns\b", query, re.I):
            return [{"type": "BNS", "section": n.lower()} for n in nums[:4]]

    typed = extract_typed_entities(query)
    if len(typed) >= 2:
        return typed

    try:
        from backend.app.core.legal_offence_resolver import extract_conceptual_comparison_entities

        conceptual = extract_conceptual_comparison_entities(query)
        if len(conceptual) >= 2:
            return conceptual
    except Exception:
        pass

    from kb_retrieval import extract_comparison_sections

    secs = extract_comparison_sections(query)
    if len(secs) >= 2:
        if re.search(r"\bbns\b", query, re.I):
            law = "BNS"
        elif re.search(r"\bipc\b", query, re.I):
            law = "IPC"
        return [{"type": law, "section": s.lower()} for s in secs[:4]]

    if is_compare_query(query) and len(nums) >= 2:
        return [{"type": law, "section": n.lower()} for n in nums[:4]]

    return typed


def is_compare_query(query: str) -> bool:
    return bool(_COMPARE_INTENT_RE.search(query or ""))


def extract_typed_entities(query: str) -> List[Dict[str, str]]:
    """
    Extract typed legal entities from comparison queries.

    "Compare IPC 302 and BNS 103" →
      [{type: IPC, section: 302}, {type: BNS, section: 103}]
    """
    q = (query or "").strip()
    entities: List[Dict[str, str]] = []
    seen = set()

    for m in _TYPED_ENTITY_RE.finditer(q):
        law = normalize_law_code(m.group(1))
        sec = m.group(2).lower()
        key = (law, sec)
        if key not in seen:
            seen.add(key)
            entities.append({"type": law, "section": sec})

    # "307 and BNS equivalent" — infer BNS from mapping
    if len(entities) == 1 and re.search(r"\b(equivalent|counterpart|replacement|mapped)\b", q, re.I):
        e = entities[0]
        mapped = map_section(e["type"], e["section"])
        new_law = LAW_REPLACEMENTS.get(normalize_law_code(e["type"]))
        if mapped and new_law:
            entities.append({"type": new_law, "section": mapped, "auto_linked": True})

    # Law-level: "CrPC vs BNSS" without sections
    if not entities:
        laws_found: List[str] = []
        for m in _BARE_LAW_RE.finditer(q):
            law = normalize_law_code(m.group(1))
            if law not in laws_found:
                laws_found.append(law)
        if len(laws_found) >= 2:
            for law in laws_found[:4]:
                entities.append({"type": law, "section": "", "law_level": True})
        elif len(laws_found) == 1 and is_compare_query(q):
            old = laws_found[0]
            new = LAW_REPLACEMENTS.get(old)
            if new:
                entities.append({"type": old, "section": "", "law_level": True})
                entities.append({"type": new, "section": "", "law_level": True})

    # Same-law compare: "IPC 300 and 307" — second section may lack law prefix
    if is_compare_query(q) and len(entities) < 2:
        from kb_retrieval import extract_comparison_sections

        law = "IPC"
        if re.search(r"\bbns\b", q, re.I):
            law = "BNS"
        elif entities:
            law = normalize_law_code(entities[0].get("type", "IPC"))
        elif re.search(r"\bipc\b", q, re.I):
            law = "IPC"
        seen_secs = {e.get("section", "").lower() for e in entities if e.get("section")}
        for sec in extract_comparison_sections(q):
            sl = sec.lower()
            if sl and sl not in seen_secs:
                seen_secs.add(sl)
                entities.append({"type": law, "section": sl})

    try:
        from backend.app.services.legal_query_parser import is_mapping_comparison_intent

        if is_mapping_comparison_intent(q):
            return enrich_entities_with_mapping(entities)
    except ImportError:
        pass
    if len(entities) >= 2:
        laws = {normalize_law_code(e.get("type", "IPC")) for e in entities}
        if len(laws) == 1:
            return [dict(e) for e in entities]
    return entities


def sanitize_chunk_text(text: str) -> str:
    """Remove chart boilerplate and placeholder lines."""
    from kb_preprocess import clean_legal_text

    t = clean_legal_text(text or "")
    lines = []
    for line in t.split("\n"):
        line = line.strip()
        if not line or len(line) < 4:
            continue
        if _CHART_BOILERPLATE_RE.match(line):
            continue
        if line in ("—", "-", "–", "Topic / Usage", "Topic/Usage"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _entity_in_chunk(content: str, entity: Dict[str, str]) -> bool:
    law = entity.get("type", "")
    sec = entity.get("section", "")
    cl = (content or "").lower()
    if entity.get("law_level"):
        return law.lower() in cl or LAW_FULL_NAMES.get(law, "").lower()[:20] in cl
    if sec:
        if re.search(rf"\b{re.escape(law.lower())}\s*{re.escape(sec)}\b", cl):
            return True
        if re.search(rf"\bsection\s*{re.escape(sec)}\b", cl) and law.lower() in cl:
            return True
        if re.search(rf"\b{re.escape(law.lower())}\s*section\s*{re.escape(sec)}\b", cl):
            return True
        # Mapping row: IPC 302 → BNS 103
        if re.search(
            rf"\b{re.escape(law.lower())}\s*{re.escape(sec)}\b.*(?:→|->|-)\s*(?:bns|bnss|bsa)\s*\d",
            cl,
        ):
            return True
        if re.search(
            rf"(?:→|->|—|-)\s*{re.escape(law.lower())}\s*{re.escape(sec)}\b",
            cl,
        ):
            return True
    return False


def _counterpart_ipc_section(
    entity: Dict[str, str], all_entities: List[Dict[str, str]]
) -> Optional[str]:
    """When KB has IPC text only, map BNS/BNSS/BSA section back to IPC for mirror retrieval."""
    law = normalize_law_code(entity.get("type", ""))
    sec = (entity.get("section") or "").lower()
    if not sec or law not in ("BNS", "BNSS", "BSA"):
        return None
    old_law = {"BNS": "IPC", "BNSS": "CrPC", "BSA": "Evidence Act"}.get(law)
    if not old_law:
        return None
    for other in all_entities:
        if normalize_law_code(other.get("type", "")) != old_law:
            continue
        osec = (other.get("section") or "").lower()
        if not osec:
            continue
        mapped = map_section(old_law, osec)
        if mapped and mapped.lower() == sec:
            return osec
    return reverse_map_section(law, sec)


def _retrieve_counterpart_mirror(
    entity: Dict[str, str],
    all_entities: List[Dict[str, str]],
    index_dir: Any,
    *,
    k: int = 8,
) -> List[Dict[str, Any]]:
    """Pull IPC (or old-law) section text when new-law section is absent from the index."""
    ipc_sec = _counterpart_ipc_section(entity, all_entities)
    if not ipc_sec:
        return []

    law = normalize_law_code(entity.get("type", "BNS"))
    sec = (entity.get("section") or "").lower()
    old_law = {"BNS": "IPC", "BNSS": "CrPC", "BSA": "Evidence Act"}.get(law, "IPC")
    sub_q = f"{old_law} Section {ipc_sec}"

    from rag import query_kb

    hits: List[Dict[str, Any]] = []
    try:
        hits = query_kb(sub_q, k=k, index_dir=index_dir)
    except Exception:
        pass

    old_ent = {"type": old_law, "section": ipc_sec}
    matched = [h for h in hits if _entity_in_chunk(h.get("content", ""), old_ent)]
    if not matched and index_dir:
        try:
            from kb_legal_query_rewrite import keyword_fallback_from_vectorstore
            from rag import _load_docstore_only

            vs = _load_docstore_only(index_dir)
            if vs:
                kw_hits = keyword_fallback_from_vectorstore(
                    vs, f"{old_law} {ipc_sec}".strip(), top_k=k
                )
                matched = [h for h in kw_hits if _entity_in_chunk(h.get("content", ""), old_ent)]
        except Exception:
            pass

    try:
        from kb_preprocess import extract_section_content
    except ImportError:
        extract_section_content = None  # type: ignore

    mirrored: List[Dict[str, Any]] = []
    for h in (matched or hits[:3]):
        body = sanitize_chunk_text(h.get("content") or "")
        if extract_section_content:
            isolated = extract_section_content(body, ipc_sec) or body
        else:
            isolated = body
        if not isolated or len(isolated) < 20:
            continue
        header = f"{law} Section {sec.upper()} (mapped equivalent of {old_law} Section {ipc_sec.upper()} in your documents)"
        wrapped = f"{header}\n{isolated}"
        hc = dict(h)
        hc["content"] = wrapped
        hc["mirrored_from"] = f"{old_law}:{ipc_sec}"
        mirrored.append(hc)
    return mirrored


def _extract_entity_snippet(chunks: List[Dict], entity: Dict[str, str]) -> str:
    law = entity.get("type", "IPC")
    sec = entity.get("section", "")

    try:
        from kb_preprocess import extract_section_content
    except ImportError:
        extract_section_content = None  # type: ignore

    for ch in chunks:
        body = sanitize_chunk_text(ch.get("content") or "")
        ent_key = _entity_key(entity)
        if ch.get("entity") != ent_key and ch.get("mirrored_for") != ent_key:
            if not _entity_in_chunk(body, entity):
                continue

        if entity.get("law_level"):
            for line in body.split("\n"):
                if law.lower() in line.lower() and len(line) > 30:
                    cleaned = _clean_snippet(line)
                    if cleaned:
                        return cleaned
            return _clean_snippet(body[:400])

        if sec and extract_section_content:
            iso_sec = sec
            if ch.get("mirrored_from"):
                parts = str(ch.get("mirrored_from", "")).split(":", 1)
                if len(parts) == 2 and parts[1]:
                    iso_sec = parts[1]
            isolated = extract_section_content(body, iso_sec) or extract_section_content(body, sec) or ""
            if isolated and len(isolated) > 30:
                try:
                    from kb_content_cleaner import strip_kb_test_boilerplate

                    return strip_kb_test_boilerplate(isolated)[:900]
                except ImportError:
                    return isolated[:900]

        if sec:
            for line in body.split("\n"):
                if re.search(rf"\b{re.escape(law)}\s*Section\s*{re.escape(sec)}\b", line, re.I):
                    cleaned = _clean_snippet(line)
                    if cleaned and not _CHART_BOILERPLATE_RE.match(cleaned):
                        return cleaned
                if line.strip().lower().startswith("meaning:"):
                    cleaned = _clean_snippet(line)
                    if cleaned:
                        return cleaned

        return _clean_snippet(body[:500])

    return ""


def _clean_snippet(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"^(?:Topic\s*/?\s*Usage\s*)", "", t, flags=re.I)
    if _CHART_BOILERPLATE_RE.match(t):
        return ""
    if t in ("—", "-", "Topic / Usage"):
        return ""
    return t[:600]


def _is_question_boilerplate(sent: str) -> bool:
    t = (sent or "").strip()
    if not t:
        return True
    try:
        from kb_content_cleaner import is_kb_test_boilerplate

        if is_kb_test_boilerplate(t):
            return True
    except ImportError:
        pass
    if t.endswith("?"):
        return True
    if re.match(r"^[-•]\s*(?:what|how|explain|compare|difference)\b", t, re.I):
        return True
    if re.search(r"\bwhat is the punishment\b", t, re.I):
        return True
    if re.search(r"\bExplain IPC \d+", t, re.I):
        return True
    return False


def _extract_meaning(
    snippet: str,
    entity: Dict[str, str],
    *,
    mapping_mode: bool = False,
) -> str:
    if not snippet:
        return _MISSING_DETAIL
    law = entity.get("type", "")
    sec = entity.get("section", "")
    is_kb_test_boilerplate = lambda _t: False  # type: ignore

    try:
        from kb_content_cleaner import extract_meaning_from_block, is_kb_test_boilerplate as _is_test

        is_kb_test_boilerplate = _is_test
        labeled = extract_meaning_from_block(snippet)
        if labeled:
            return labeled
    except ImportError:
        pass

    for sent in re.split(r"(?<=[.!?])\s+", snippet):
        if _is_question_boilerplate(sent):
            continue
        if is_kb_test_boilerplate(sent):
            continue
        if re.search(
            r"\b(murder|culpable|punish|imprisonment|offence|offense|defines|shall|whoever|attempt)\b",
            sent,
            re.I,
        ):
            if not _CHART_BOILERPLATE_RE.match(sent.strip()):
                if not re.search(r"\bcorresponds to bns\b", sent, re.I):
                    return sent.strip()[:400]

    if entity.get("law_level"):
        full = LAW_FULL_NAMES.get(law, law)
        new = LAW_REPLACEMENTS.get(law)
        if new and mapping_mode:
            return (
                f"{full} has been replaced by {LAW_FULL_NAMES.get(new, new)} "
                f"under India's new criminal law reforms."
            )
        return snippet[:400]

    if (
        mapping_mode
        and sec
        and law in ("IPC", "CrPC", "Evidence Act")
        and entity.get("auto_linked")
    ):
        new_law = LAW_REPLACEMENTS.get(law, "BNS")
        mapped = map_section(law, sec)
        if mapped:
            return (
                f"Under the mapping in your document, {law} Section {sec.upper()} "
                f"corresponds to {new_law} Section {mapped.upper()}."
            )

    clean = re.sub(
        r"\b(?:Topic\s*/?\s*Usage|IPC\s+Section\s+BNS\s+Section).*$",
        "",
        snippet,
        flags=re.I,
    ).strip()
    try:
        from kb_content_cleaner import strip_kb_test_boilerplate

        clean = strip_kb_test_boilerplate(clean)
    except ImportError:
        pass
    if clean and not is_kb_test_boilerplate(clean):
        return clean[:400]
    return _MISSING_DETAIL


def _extract_punishment(snippet: str, entity: Optional[Dict[str, str]] = None) -> str:
    if not snippet:
        return _MISSING_DETAIL
    ent = entity or {}
    try:
        from kb_content_cleaner import extract_punishment_from_block

        pun = extract_punishment_from_block(
            snippet,
            section=ent.get("section", ""),
            law=ent.get("type", "IPC"),
        )
        if pun:
            return pun[:400]
    except ImportError:
        pass
    for sent in re.split(r"(?<=[.!?])\s+", snippet):
        if _is_question_boilerplate(sent):
            continue
        if re.search(r"\b(imprisonment|death|life|punish|fine|rigorous|years|extend)\b", sent, re.I):
            return sent.strip()[:300]
    return _MISSING_DETAIL


def _extract_elements(snippet: str) -> List[str]:
    elements: List[str] = []
    if not snippet:
        return elements
    keywords = (
        ("intention", "Intention to cause death or fatal harm"),
        ("knowledge", "Knowledge that the act is likely to cause death"),
        ("murder", "Murder or culpable homicide elements as defined in the source"),
        ("attempt", "Attempt — act done with intent or knowledge"),
        ("negligen", "Death caused by negligent act"),
        ("cheating", "Dishonest inducement or deception"),
        ("digital evidence", "Digital evidence admissibility"),
    )
    sl = snippet.lower()
    for kw, label in keywords:
        if kw in sl and label not in elements:
            elements.append(label)
    return elements[:4]


def retrieve_comparison_bundle(
    entities: List[Dict[str, str]],
    index_dir: Any,
    *,
    k_per_entity: int = 8,
) -> ComparisonBundle:
    """
    Independent retrieval per entity.

    left = retrieve("IPC 302")
    right = retrieve("BNS 103")
    — never retrieve("IPC 302 and BNS 103").
    """
    bundle = ComparisonBundle(entities=list(entities[:4]))
    if not entities:
        return bundle

    for ent in entities[:4]:
        key = _entity_key(ent)
        law = ent.get("type", "IPC")
        sec = ent.get("section", "")
        if ent.get("law_level"):
            sub_q = f"{law} {LAW_FULL_NAMES.get(law, law)} replacement successor"
        elif sec:
            sub_q = f"{law} Section {sec}"
        else:
            sub_q = f"{law} {LAW_FULL_NAMES.get(law, law)}"

        from rag import query_kb

        hits: List[Dict[str, Any]] = []
        try:
            hits = query_kb(sub_q, k=k_per_entity, index_dir=index_dir)
        except Exception:
            hits = []

        matched = [h for h in hits if _entity_in_chunk(h.get("content", ""), ent)]
        if not matched and index_dir:
            try:
                from kb_legal_query_rewrite import keyword_fallback_from_vectorstore
                from rag import _load_docstore_only

                vs = _load_docstore_only(index_dir)
                if vs:
                    kw_hits = keyword_fallback_from_vectorstore(
                        vs, f"{law} {sec}".strip(), top_k=k_per_entity
                    )
                    matched = [h for h in kw_hits if _entity_in_chunk(h.get("content", ""), ent)]
            except Exception:
                pass

        use = list(matched)
        mirror_used = False
        if not use and sec and normalize_law_code(law) in ("BNS", "BNSS", "BSA"):
            use = _retrieve_counterpart_mirror(ent, entities, index_dir, k=k_per_entity)
            mirror_used = bool(use)

        tagged: List[Dict[str, Any]] = []
        for h in use:
            hc = dict(h)
            hc["entity"] = key
            hc["entity_type"] = law
            hc["entity_section"] = sec
            hc["side"] = key
            hc["final_score"] = float(hc.get("final_score", 0.5)) + 0.25
            tagged.append(hc)
        bundle.entity_chunks[key] = tagged
        bundle.all_chunks.extend(tagged)

        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "BNS",
                "kb_compare_engine.py:retrieve_comparison_bundle",
                "entity_retrieval",
                {
                    "entity": key,
                    "matched": len(matched),
                    "mirror_used": mirror_used,
                    "use_count": len(use),
                    "top_preview": (use[0].get("content") or "")[:120] if use else "",
                },
            )
        except Exception:
            pass
        # endregion

    seen = set()
    deduped: List[Dict[str, Any]] = []
    for ch in bundle.all_chunks:
        k = (ch.get("content") or "")[:100]
        if k not in seen:
            seen.add(k)
            deduped.append(ch)
    bundle.all_chunks = deduped
    return bundle


def retrieve_for_comparison(
    entities: List[Dict[str, str]],
    index_dir: Any,
    base_query: str = "",
    *,
    k_per_entity: int = 8,
) -> List[Dict[str, Any]]:
    """Independent retrieval per typed entity — never one shared query."""
    _ = base_query  # intentionally ignored — no combined query retrieval
    bundle = retrieve_comparison_bundle(entities, index_dir, k_per_entity=k_per_entity)
    return bundle.all_chunks[:16]


def format_comparison_pro(
    question: str,
    chunks: List[Dict],
    entities: List[Dict[str, str]],
    *,
    bundle: Optional[ComparisonBundle] = None,
    mapping_mode: Optional[bool] = None,
) -> str:
    """Structured comparison with professional Markdown table."""
    from kb_response_state import enforce_single_state
    from response_cleaner import finalize_display_answer

    if mapping_mode is None:
        try:
            from backend.app.services.legal_query_parser import is_mapping_comparison_intent

            mapping_mode = is_mapping_comparison_intent(question)
        except ImportError:
            mapping_mode = False
    if len(entities) < 2:
        entities = extract_all_comparison_entities(question)
    if mapping_mode:
        entities = enrich_entities_with_mapping(entities)
    elif len(entities) >= 2:
        laws = {normalize_law_code(e.get("type", "IPC")) for e in entities}
        if len(laws) == 1:
            primary = normalize_law_code(entities[0].get("type", "IPC"))
            entities = [
                {"type": primary, "section": e.get("section", "")} for e in entities if e.get("section")
            ]

    if len(entities) < 2:
        from kb_response_state import KB_NOT_FOUND_MESSAGE
        return KB_NOT_FOUND_MESSAGE

    if bundle is None and chunks:
        bundle = ComparisonBundle(entities=entities, all_chunks=chunks)
        for ent in entities:
            key = _entity_key(ent)
            bundle.entity_chunks[key] = [
                c for c in chunks if _entity_in_chunk(c.get("content", ""), ent)
            ] or [c for c in chunks if c.get("entity") == key]

    # Build column labels
    labels: List[str] = []
    for ent in entities[:4]:
        law, sec = ent.get("type", ""), ent.get("section", "")
        if sec:
            labels.append(f"{law} {sec.upper()}")
        else:
            labels.append(LAW_FULL_NAMES.get(law, law))

    rows: List[tuple[str, List[str]]] = []
    meanings: List[str] = []
    punishments: List[str] = []
    for ent in entities[:4]:
        ent_chunks = (
            (bundle.entity_chunks.get(_entity_key(ent)) if bundle else None)
            or [c for c in chunks if _entity_in_chunk(c.get("content", ""), ent)]
        )
        snippet = _extract_entity_snippet(ent_chunks or [], ent)
        if not snippet and chunks:
            snippet = _extract_entity_snippet(chunks, ent)
        meanings.append(_extract_meaning(snippet, ent, mapping_mode=bool(mapping_mode)))
        punishments.append(_extract_punishment(snippet, ent))

    rows.append(("Meaning", meanings))
    rows.append(("Punishment", punishments))

    title_law = entities[0].get("type", "IPC")
    if len(entities) == 2:
        e1, e2 = entities[0], entities[1]
        title = (
            f"# Comparison: {labels[0]} vs {labels[1]}"
            if e1.get("section") or e2.get("section")
            else f"# Comparison: {labels[0]} vs {labels[1]}"
        )
    else:
        title = f"# Comparison: {', '.join(labels)}"

    parts = [title, ""]
    header = "| Aspect | " + " | ".join(labels) + " |"
    sep = "| --- | " + " | ".join(["---"] * len(labels)) + " |"
    parts.extend([header, sep])
    for aspect, cells in rows:
        while len(cells) < len(labels):
            cells.append(_MISSING_DETAIL)
        parts.append("| " + aspect + " | " + " | ".join(cells[: len(labels)]) + " |")
    parts.append("")

    if len(entities) == 2:
        diff = _key_difference(entities[0], entities[1], chunks, labels=labels)
    else:
        diff = (
            f"Your document covers **{len(entities)} distinct sections** "
            f"({', '.join(labels)}). See the table for meaning and punishment where available."
        )
    parts.extend(["## Key Difference", "", diff])

    body, _ = finalize_display_answer("\n".join(parts), chunks)
    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "CMP",
            "kb_compare_engine.py:format_comparison_pro",
            "comparison_built",
            {
                "entities": [f"{e.get('type')}:{e.get('section')}" for e in entities[:4]],
                "meanings_preview": [m[:80] for m in meanings],
                "has_boilerplate": any(
                    "rigorously test" in (m or "").lower() or "Explain IPC" in (m or "")
                    for m in meanings
                ),
            },
            runId="health-check",
        )
    except Exception:
        pass
    # endregion
    return enforce_single_state(body, found=True)


def _key_difference(
    e1: Dict,
    e2: Dict,
    chunks: List[Dict],
    *,
    labels: Optional[List[str]] = None,
) -> str:
    law1, sec1 = e1.get("type", "IPC"), e1.get("section", "")
    law2, sec2 = e2.get("type", "IPC"), e2.get("section", "")
    label_a = (labels[0] if labels and len(labels) > 0 else f"{law1} {sec1.upper()}".strip())
    label_b = (labels[1] if labels and len(labels) > 1 else f"{law2} {sec2.upper()}".strip())

    combined = "\n".join(sanitize_chunk_text(c.get("content", "")) for c in chunks[:8])
    mappings = parse_mapping_row(combined)

    for old_law, old_sec, new_law, new_sec in mappings:
        if (
            normalize_law_code(law1) == old_law
            and sec1.lower() == old_sec
            and normalize_law_code(law2) == new_law
            and sec2.lower() == new_sec
        ):
            return (
                f"Your document maps **{old_law} Section {old_sec.upper()}** to "
                f"**{new_law} Section {new_sec.upper()}**. The new code modernizes "
                f"wording and structure while continuing to govern the same class of offence."
            )

    mapped = map_section(law1, sec1)
    if mapped and normalize_law_code(law2) == LAW_REPLACEMENTS.get(normalize_law_code(law1)):
        return (
            f"**{law1} Section {sec1.upper()}** under the old code corresponds to "
            f"**{law2} Section {mapped.upper()}** under the new Bharatiya criminal laws. "
            f"The substantive offence category is preserved with updated statutory language."
        )

    if e1.get("law_level") or e2.get("law_level"):
        return (
            f"**{LAW_FULL_NAMES.get(law1, law1)}** has been replaced by "
            f"**{LAW_FULL_NAMES.get(law2, law2)}** as part of India's 2023 criminal law reforms."
        )

    s1 = _extract_entity_snippet(chunks, e1)
    s2 = _extract_entity_snippet(chunks, e2)
    m1 = _extract_meaning(s1, e1) if s1 else ""
    m2 = _extract_meaning(s2, e2) if s2 else ""
    if m1 and m2 and m1 != _MISSING_DETAIL and m2 != _MISSING_DETAIL:
        return (
            f"**{label_a}** ({m1[:180]}{'…' if len(m1) > 180 else ''}) "
            f"differs from **{label_b}** ({m2[:180]}{'…' if len(m2) > 180 else ''}). "
            f"See the table for punishment details where stated in your document."
        )
    if s1 and s2:
        return (
            f"**{label_a}** and **{label_b}** address distinct provisions in your "
            f"uploaded document. Refer to the table for meaning and punishment."
        )

    return (
        "Your document distinguishes these provisions under the old and new criminal codes. "
        "See the section summaries above for specifics available in the source."
    )


def run_compare_pipeline(
    user_id: str,
    query: str,
    index_dir: Any,
    profile: Any,
    history: Optional[List] = None,
) -> Tuple[str, List[Dict], Dict[str, Any]]:
    """Full compare pipeline: extract → retrieve per entity → format."""
    entities = extract_all_comparison_entities(query)
    if len(entities) < 2:
        from kb_retrieval import extract_comparison_sections

        secs = extract_comparison_sections(query)
        if len(secs) >= 2:
            try:
                from backend.app.services.legal_query_parser import (
                    default_law_for_query,
                    is_mapping_comparison_intent,
                )

                law = default_law_for_query(query).upper()
                entities = [{"type": law, "section": secs[0]}, {"type": law, "section": secs[1]}]
                if is_mapping_comparison_intent(query):
                    entities = enrich_entities_with_mapping(entities)
            except ImportError:
                law = "IPC" if re.search(r"\bipc\b", query, re.I) else "IPC"
                entities = [{"type": law, "section": secs[0]}, {"type": law, "section": secs[1]}]

    diag: Dict[str, Any] = {
        "mode": "compare_pipeline",
        "entities": entities,
        "entity_count": len(entities),
    }

    bundle = retrieve_comparison_bundle(entities, index_dir, k_per_entity=8)
    chunks = bundle.all_chunks
    diag["chunk_count"] = len(chunks)
    diag["independent_retrieval"] = True
    diag["left"] = _entity_key(entities[0]) if entities else ""
    diag["right"] = _entity_key(entities[1]) if len(entities) > 1 else ""

    if profile and hasattr(profile, "signals"):
        profile.signals["typed_entities"] = entities
        profile.signals["entities"] = [
            e.get("section", "") for e in entities if e.get("section")
        ]
        profile.signals["comparison_bundle"] = {
            "left": bundle.left_entity,
            "right": bundle.right_entity,
        }

    answer = format_comparison_pro(query, chunks, entities, bundle=bundle)
    return answer, chunks, diag
