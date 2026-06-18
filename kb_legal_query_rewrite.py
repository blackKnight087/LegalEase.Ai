"""
Legal query normalization, synonym expansion, and mapping-table retrieval helpers.

Handles IPC→BNS / CrPC→BNSS / Evidence Act→BSA replacement charts where dense
embeddings alone often miss wording like "new law replacing IPC".
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

REPLACE_SYNONYMS = (
    "replace",
    "replaced",
    "replacing",
    "successor",
    "new law",
    "became",
    "equivalent",
    "instead of",
    "mapped to",
    "corresponds",
    "what is the new",
    "which law replaced",
    "what replaced",
)

LAW_MAPPINGS: Dict[str, Dict[str, str]] = {
    "ipc": {
        "old_short": "IPC",
        "old_full": "Indian Penal Code (IPC), 1860",
        "new_short": "BNS",
        "new_full": "Bharatiya Nyaya Sanhita (BNS), 2023",
        "aliases": (r"\bipc\b", r"\bindian penal code\b"),
    },
    "crpc": {
        "old_short": "CrPC",
        "old_full": "Code of Criminal Procedure (CrPC), 1973",
        "new_short": "BNSS",
        "new_full": "Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023",
        "aliases": (r"\bcrpc\b", r"\bcriminal procedure code\b", r"\bcode of criminal procedure\b"),
    },
    "evidence": {
        "old_short": "Evidence Act",
        "old_full": "Indian Evidence Act, 1872",
        "new_short": "BSA",
        "new_full": "Bharatiya Sakshya Adhiniyam (BSA), 2023",
        "aliases": (r"\bevidence act\b", r"\bindian evidence act\b"),
    },
}

_ARROW_RE = re.compile(r"[→\-\–—>]")
_MAPPING_LINE_RE = re.compile(
    r"(?:IPC|CrPC|BNS|BNSS|BSA|Indian Penal Code|Evidence Act|Criminal Procedure)"
    r".{0,120}?(?:IPC|CrPC|BNS|BNSS|BSA|Indian Penal Code|Evidence Act|Criminal Procedure|Bharatiya)",
    re.I,
)


def is_law_replacement_query(query: str) -> bool:
    ql = (query or "").lower().strip()
    if not ql:
        return False
    try:
        from backend.app.services.legal_query_parser import (
            is_law_replacement_intent,
            is_section_lookup_query,
        )

        if is_section_lookup_query(query):
            return False
        if is_law_replacement_intent(ql):
            return True
    except ImportError:
        pass
    try:
        from backend.app.services.legal_query_parser import has_legal_section_entities

        if has_legal_section_entities(query):
            return False
    except ImportError:
        pass
    has_law = any(re.search(p, ql) for m in LAW_MAPPINGS.values() for p in m["aliases"])
    has_law = has_law or bool(re.search(r"\b(bns|bnss|bsa)\b", ql))
    has_replace = any(s in ql for s in REPLACE_SYNONYMS)
    if has_law and has_replace:
        return True
    if re.search(r"\bnew\s+(?:criminal\s+)?law\b", ql) and re.search(r"\b(ipc|crpc|evidence)\b", ql):
        return True
    if re.search(r"\b(?:ipc|crpc)\s*\d{1,4}\b.*\b(?:became|replaced|mapped|equivalent|what)\b", ql):
        return True
    if re.search(r"\bwhat\s+changed\b.*\b(?:criminal|law|bns|ipc)\b", ql):
        return True
    return False


def detect_target_laws(query: str) -> List[str]:
    ql = (query or "").lower()
    targets: List[str] = []
    for key, meta in LAW_MAPPINGS.items():
        if any(re.search(p, ql) for p in meta["aliases"]):
            targets.append(key)
    if re.search(r"\bbns\b", ql) and "ipc" not in targets:
        targets.append("ipc")
    if re.search(r"\bbnss\b", ql) and "crpc" not in targets:
        targets.append("crpc")
    if re.search(r"\bbsa\b", ql) and "evidence" not in targets:
        targets.append("evidence")
    dedup: List[str] = []
    seen = set()
    for t in targets:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup


def normalize_legal_query(query: str) -> str:
    """Rewrite colloquial law-replacement questions into retrieval-friendly text."""
    q = (query or "").strip()
    ql = q.lower()
    if not q:
        return q

    targets = detect_target_laws(q)
    rewrites: List[str] = []

    for key in targets:
        meta = LAW_MAPPINGS[key]
        rewrites.append(f"{meta['old_full']} replaced by {meta['new_full']}")
        rewrites.append(f"{meta['old_short']} to {meta['new_short']} mapping")

    m = re.search(r"\bipc\s*(\d{1,4}[a-z]?)\b.*\b(?:became|replaced|mapped|equivalent|what)\b", ql)
    if m:
        rewrites.append(f"IPC {m.group(1)} BNS mapping section replacement")
    m = re.search(r"\b(?:compare|difference)\s+ipc\s*(\d+).*(?:bns|and)\s*(\d+)", ql)
    if m:
        rewrites.append(f"IPC {m.group(1)} BNS {m.group(2)} comparison mapping")

    if re.search(r"\bwhat\s+changed\b|\bnew\s+criminal\s+law", ql):
        rewrites.append("digital evidence online FIR forensic investigation criminal law reforms")

    if rewrites:
        return rewrites[0]
    return q


def expand_law_replacement_queries(query: str) -> List[str]:
    q = (query or "").strip()
    if not q:
        return []
    out: List[str] = [q, normalize_legal_query(q)]
    ql = q.lower()
    targets = detect_target_laws(q)

    for syn in ("replacement", "successor", "replaced by", "mapping", "equivalent", "new law"):
        out.append(f"{q} {syn}")

    for key in targets:
        meta = LAW_MAPPINGS[key]
        out.extend([
            f"{meta['old_short']} {meta['new_short']}",
            f"{meta['old_full']} {meta['new_full']}",
            f"{meta['old_short']} replaced {meta['new_short']}",
        ])

    if "ipc" in ql or "ipc" in targets:
        out.extend([
            "Indian Penal Code IPC Bharatiya Nyaya Sanhita BNS",
            "IPC replaced BNS 2023",
        ])
    if "crpc" in ql or "crpc" in targets:
        out.extend(["CrPC BNSS Bharatiya Nagarik Suraksha Sanhita"])
    if "evidence" in ql or "evidence" in targets:
        out.extend(["Indian Evidence Act BSA Bharatiya Sakshya Adhiniyam"])

    seen = set()
    unique: List[str] = []
    for item in out:
        norm = re.sub(r"\s+", " ", item.strip().lower())
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(item.strip())
    return unique[:12]


def build_fallback_keywords(query: str) -> List[str]:
    ql = (query or "").lower()
    keys = ["ipc", "crpc", "bns", "bnss", "bsa", "replace", "mapping", "replaced", "successor"]
    for key in detect_target_laws(query):
        meta = LAW_MAPPINGS[key]
        keys.extend([meta["old_short"].lower(), meta["new_short"].lower()])
    m = re.search(r"\bipc\s*(\d{1,4})\b", ql)
    if m:
        keys.append(f"ipc {m.group(1)}")
        keys.append(f"bns {m.group(1)}")
    m = re.search(r"\bbns\s*(\d{1,4})\b", ql)
    if m:
        keys.append(f"bns {m.group(1)}")
    if re.search(r"\bdigital evidence|online fir|forensic", ql):
        keys.extend(["digital evidence", "online fir", "forensic"])
    dedup: List[str] = []
    seen = set()
    for k in keys:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            dedup.append(kl)
    return dedup


def build_baseline_law_answer(query: str) -> Optional[str]:
    """
    Deterministic IPC/CrPC/Evidence replacement answers without requiring indexed chunks.
    Used as KB rescue when embeddings or FAISS fail.
    """
    ql = (query or "").lower().strip()
    if not ql:
        return None

    if not is_law_replacement_query(query):
        if not re.search(r"\b(ipc|crpc|evidence|bns|bnss|bsa)\b", ql):
            return None

    targets = detect_target_laws(query)
    if not targets:
        if re.search(r"\bipc\b|\bindian penal", ql):
            targets = ["ipc"]
        elif re.search(r"\bcrpc\b|\bcriminal procedure", ql):
            targets = ["crpc"]
        elif re.search(r"\bevidence act\b", ql):
            targets = ["evidence"]

    answers: List[str] = []
    for key in targets:
        if key == "ipc":
            answers.append(
                "The Indian Penal Code (IPC), 1860 has been replaced by the "
                "Bharatiya Nyaya Sanhita (BNS), 2023. BNS is India's new criminal "
                "law framework that defines offences and punishments."
            )
        elif key == "crpc":
            answers.append(
                "The Code of Criminal Procedure (CrPC), 1973 has been replaced by the "
                "Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023, which governs "
                "criminal procedure including investigation, trial, and bail."
            )
        elif key == "evidence":
            answers.append(
                "The Indian Evidence Act, 1872 has been replaced by the "
                "Bharatiya Sakshya Adhiniyam (BSA), 2023, which governs "
                "rules of evidence in criminal and civil proceedings."
            )

    if re.search(r"\bwhat\s+changed\b|\bnew\s+criminal\s+law\b", ql):
        answers.append(
            "India's new criminal laws (BNS, BNSS, BSA) introduce reforms including "
            "recognition of digital evidence, online FIR registration, and expanded "
            "forensic investigation provisions."
        )

    if not answers:
        return None
    return "\n\n".join(dict.fromkeys(answers))


def is_law_mapping_chunk(content: str) -> bool:
    cl = (content or "").strip()
    if not cl:
        return False
    if _ARROW_RE.search(cl) and _MAPPING_LINE_RE.search(cl):
        return True
    if re.search(r"\bIPC\b.*\bBNS\b", cl, re.I):
        return True
    if re.search(r"\bCrPC\b.*\bBNSS\b", cl, re.I):
        return True
    if re.search(r"\bEvidence Act\b.*\bBSA\b", cl, re.I):
        return True
    return False


def chunk_matches_law_query(content: str, query: str) -> bool:
    cl = (content or "").lower()
    ql = (query or "").lower()
    if not cl:
        return False

    targets = detect_target_laws(query)
    for key in targets:
        meta = LAW_MAPPINGS[key]
        old = meta["old_short"].lower()
        new = meta["new_short"].lower()
        if old in cl and new in cl:
            return True

    m = re.search(r"\bipc\s*(\d{1,4})\b", ql)
    if m:
        sec = m.group(1)
        if re.search(rf"\bipc\s*{re.escape(sec)}\b", cl) and re.search(r"\bbns\s*\d", cl):
            return True

    if re.search(r"\bwhat\s+changed\b|\bnew\s+criminal", ql):
        if any(t in cl for t in ("digital evidence", "online fir", "forensic", "reform")):
            return True

    return is_law_mapping_chunk(content)


def keyword_fallback_from_vectorstore(vs: Any, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """Exact keyword scan over all indexed chunks — last resort before NOT_FOUND."""
    keywords = build_fallback_keywords(query)
    if not keywords or vs is None:
        return []

    from rag import _format_result

    scored: List[Tuple[Dict[str, Any], float]] = []
    try:
        doc_ids = vs.index_to_docstore_id.values()
    except Exception:
        return []

    for doc_id in doc_ids:
        try:
            doc = vs.docstore.search(doc_id)
        except Exception:
            continue
        if not doc or not getattr(doc, "page_content", ""):
            continue
        content = doc.page_content
        cl = content.lower()
        score = 0.0
        for kw in keywords:
            if kw in cl:
                score += 1.0
        if score <= 0:
            continue
        if chunk_matches_law_query(content, query):
            score += 3.0
        if is_law_mapping_chunk(content):
            score += 1.5
        result = _format_result(doc, 1.5)
        result["final_score"] = min(1.0, 0.35 + score * 0.12)
        result["hybrid_score"] = result["final_score"]
        result["source"] = "keyword_fallback"
        scored.append((result, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in scored[:top_k]]


def extract_law_mapping_answer(query: str, chunks: List[Dict[str, Any]]) -> Optional[str]:
    """Deterministic natural-language answer from mapping chart chunks."""
    if not chunks:
        return None
    try:
        from kb_query_types import is_section_focus_query

        if is_section_focus_query(query):
            return None
    except Exception:
        pass
    combined = "\n".join((c.get("content") or "") for c in chunks[:8])
    ql = (query or "").lower()

    m = re.search(r"\bipc\s*(\d{1,4})\b", ql)
    if m and re.search(r"\b(?:mapped|equivalent|replaced|became|correspond|→)\b", ql):
        sec = m.group(1)
        row = re.search(
            rf"IPC\s*{re.escape(sec)}\s*[→\-\–—>]\s*BNS\s*(\d{{1,4}})",
            combined,
            re.I,
        )
        if row:
            return (
                f"Under your document's mapping chart, IPC Section {sec} corresponds to "
                f"BNS Section {row.group(1)}."
            )

    if re.search(r"\bwhat\s+changed\b|\bnew\s+criminal\s+law", ql):
        changes: List[str] = []
        if re.search(r"digital evidence", combined, re.I):
            changes.append("recognition and admissibility of digital evidence")
        if re.search(r"online\s+fir", combined, re.I):
            changes.append("online FIR registration")
        if re.search(r"forensic", combined, re.I):
            changes.append("expanded forensic investigation provisions")
        if changes:
            joined = ", ".join(changes[:-1]) + (" and " + changes[-1] if len(changes) > 1 else changes[0])
            return (
                f"Your document highlights several reforms in India's new criminal laws, "
                f"including {joined}."
            )

    targets = detect_target_laws(query)
    if not targets and re.search(r"\b(ipc|crpc|evidence|bns|bnss|bsa)\b", ql):
        if not is_law_replacement_query(query):
            return None
        targets = detect_target_laws(query + " ipc crpc evidence")

    for key in targets:
        meta = LAW_MAPPINGS[key]
        pattern = (
            rf"{re.escape(meta['old_short'])}[^→\-\–—>\n]{{0,80}}[→\-\–—>]\s*"
            rf"(?:{re.escape(meta['new_short'])}|Bharatiya[^\n]{{0,60}})"
        )
        if re.search(pattern, combined, re.I):
            if key == "ipc":
                return (
                    "The Indian Penal Code (IPC), 1860 has been replaced by the "
                    "Bharatiya Nyaya Sanhita (BNS), 2023. BNS is India's new criminal "
                    "law framework that defines offences and punishments."
                )
            if key == "crpc":
                return (
                    "The Code of Criminal Procedure (CrPC), 1973 has been replaced by the "
                    "Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023, which governs "
                    "criminal procedure including investigation, trial, and bail."
                )
            if key == "evidence":
                return (
                    "The Indian Evidence Act, 1872 has been replaced by the "
                    "Bharatiya Sakshya Adhiniyam (BSA), 2023, which governs "
                    "rules of evidence in criminal and civil proceedings."
                )

    return None


def log_rag_debug(
    *,
    user_query: str,
    rewritten_query: str,
    expanded_queries: List[str],
    top_chunks: List[Dict[str, Any]],
    selected_chunk: Optional[Dict[str, Any]] = None,
    prompt_preview: str = "",
) -> None:
    try:
        from backend.app.core.kb_pipeline_log import kb_log

        kb_log(
            "RAG_DEBUG",
            user_query=user_query[:200],
            rewritten_query=rewritten_query[:200],
            expanded=expanded_queries[:8],
        )
        for i, ch in enumerate(top_chunks[:8]):
            kb_log(
                "RAG_DEBUG_CHUNK",
                rank=i + 1,
                score=round(float(ch.get("final_score", ch.get("hybrid_score", 0))), 4),
                file=(ch.get("metadata") or {}).get("filename"),
                excerpt=(ch.get("content") or "")[:140],
            )
        if selected_chunk:
            kb_log(
                "RAG_DEBUG_SELECTED",
                file=(selected_chunk.get("metadata") or {}).get("filename"),
                excerpt=(selected_chunk.get("content") or "")[:200],
            )
        if prompt_preview:
            kb_log("RAG_DEBUG_PROMPT", preview=prompt_preview[:400])
    except Exception:
        pass

    logger.info(
        "[RAG DEBUG] query=%r rewritten=%r top_k=%s",
        user_query[:120],
        rewritten_query[:120],
        len(top_chunks),
    )
    for i, ch in enumerate(top_chunks[:8]):
        logger.info(
            "[RAG DEBUG] #%s score=%.4f excerpt=%s",
            i + 1,
            float(ch.get("final_score", ch.get("hybrid_score", 0))),
            (ch.get("content") or "")[:100].replace("\n", " "),
        )
