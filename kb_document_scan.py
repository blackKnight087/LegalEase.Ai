"""
Document-wide scan for list/summary queries — avoids weak top-k vector drift.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from kb_query_types import QueryType, _requested_laws
from kb_retrieval import section_in_chunk

IPC_SECTION_RE = re.compile(
    r"\b(?:IPC|Indian\s+Penal\s+Code)\s*(?:,?\s*)?(?:Section|Sec\.?)\s*(\d{1,4}[a-z]?)\b",
    re.I,
)
BNS_SECTION_RE = re.compile(
    r"\b(?:BNS|Bharatiya\s+Nyaya\s+Sanhita)\s*(?:,?\s*)?(?:Section|Sec\.?)\s*(\d{1,4}[a-z]?)\b",
    re.I,
)
GENERIC_SECTION_RE = re.compile(
    r"\bSection\s+(\d{1,4}[a-z]?)\b",
    re.I,
)
IPC_INLINE_RE = re.compile(r"\bIPC\s+(\d{1,4}[a-z]?)\b", re.I)
IT_ACT_RE = re.compile(
    r"\b(?:IT\s+Act|Information\s+Technology\s+Act|Cyber\s+Law|Section\s+66[CDEF])\b",
    re.I,
)
IT_SECTION_RE = re.compile(
    r"\b(?:IT\s+Act|Information\s+Technology)\s*(?:,?\s*)?(?:Section|Sec\.?)\s*(66[CDEF])\b",
    re.I,
)
IT_INLINE_RE = re.compile(r"\b(?:Section\s+)?(66[CDEF])\b", re.I)
OFFENCE_TOPIC_RE = re.compile(
    r"\b(offence|offenses?|criminal|murder|homicide|theft|cyber|punishment)\b",
    re.I,
)


def _load_faiss_docstore(index_dir: Union[str, Path]):
    from rag import FAISS, INDEX_NAME, _get_langchain_embeddings, _is_safe_index_dir, _resolve_index_dir, index_exists

    target = _resolve_index_dir(index_dir)
    if not _is_safe_index_dir(target) or not index_exists(target):
        return None
    embeddings = _get_langchain_embeddings()
    return FAISS.load_local(
        str(target),
        embeddings,
        index_name=INDEX_NAME,
        allow_dangerous_deserialization=True,
    )


def iter_all_index_chunks(index_dir: Union[str, Path]) -> List[Dict[str, Any]]:
    vs = _load_faiss_docstore(index_dir)
    if vs is None:
        return []
    out: List[Dict[str, Any]] = []
    for _idx, doc_id in vs.index_to_docstore_id.items():
        doc = vs.docstore.search(doc_id)
        if not doc or not getattr(doc, "page_content", ""):
            continue
        meta = getattr(doc, "metadata", None) or {}
        content = (doc.page_content or "").strip()
        if len(content) < 20:
            continue
        out.append(
            {
                "content": content,
                "metadata": dict(meta) if isinstance(meta, dict) else {},
                "score": 0.5,
                "final_score": 0.5,
                "hybrid_score": 0.5,
                "source": "document_scan",
            }
        )
    return out


def _title_after_section(text: str, section: str, window: int = 120) -> str:
    patterns = [
        rf"(?:IPC|Indian Penal Code)\s*(?:Section|Sec\.?)\s*{re.escape(section)}\s*[—–\-:]?\s*([^\n.]{8,80})",
        rf"\bSection\s*{re.escape(section)}\s*[—–\-:]?\s*([^\n.]{8,80})",
        rf"\bIPC\s*{re.escape(section)}\s*[—–\-:]?\s*([^\n.]{8,80})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip(" -—–:")
            if len(title) >= 4:
                return title[:80]
    return ""


def extract_ipc_sections_from_chunks(
    chunks: List[Dict[str, Any]],
    laws_filter: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    Scan all chunk text and return deduplicated IPC/BNS sections with short titles.
    """
    laws = laws_filter or ["ipc"]
    prefer_ipc = "ipc" in laws and "it_act" not in laws
    found: OrderedDict[str, Dict[str, str]] = OrderedDict()

    for ch in chunks:
        text = ch.get("content") or ""
        if prefer_ipc and IT_ACT_RE.search(text) and not re.search(
            r"\b(?:IPC|Indian Penal Code)\b", text, re.I
        ):
            continue

        candidates: List[Tuple[str, str]] = []
        for rx, law in (
            (IPC_SECTION_RE, "IPC"),
            (BNS_SECTION_RE, "BNS"),
            (IPC_INLINE_RE, "IPC"),
        ):
            if law == "IPC" and "ipc" not in laws and "bns" not in laws:
                continue
            if law == "BNS" and "bns" not in laws:
                continue
            for m in rx.finditer(text):
                sec = m.group(1).lower()
                if sec.isdigit() and not (1 <= int(sec) <= 599):
                    continue
                candidates.append((sec, law))

        if "ipc" in laws or "bns" in laws:
            for m in GENERIC_SECTION_RE.finditer(text):
                sec = m.group(1).lower()
                if sec in {c[0] for c in candidates}:
                    continue
                prefix = text[max(0, m.start() - 60) : m.start()]
                if re.search(
                    r"\b(?:IT\s+Act|Information\s+Technology|Cyber\s*Law|66[CDEF])\b",
                    prefix,
                    re.I,
                ):
                    continue
                if re.search(rf"\b(?:IPC|Indian Penal Code|BNS)\b", prefix, re.I):
                    law = "BNS" if re.search(r"\bBNS\b", prefix, re.I) else "IPC"
                    candidates.append((sec, law))

        for sec, law in candidates:
            key = f"{law}:{sec}"
            if key in found:
                continue
            title = _title_after_section(text, sec)
            found[key] = {
                "section": sec,
                "law": law,
                "title": title,
                "label": f"{law} {sec.upper()}" + (f" — {title}" if title else ""),
            }

    def _sort_key(item: Dict[str, str]) -> Tuple[int, str]:
        s = item["section"]
        return (int(re.sub(r"[a-z]$", "", s) or "0"), s)

    return sorted(found.values(), key=_sort_key)


def extract_all_offences_from_chunks(
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Extract IPC/BNS + IT Act offences for document-wide summaries."""
    ipc = extract_ipc_sections_from_chunks(chunks, laws_filter=["ipc", "bns"])
    found: OrderedDict[str, Dict[str, str]] = OrderedDict()
    for ent in ipc:
        found[f"{ent['law']}:{ent['section']}"] = ent

    for ch in chunks:
        text = ch.get("content") or ""
        for m in IT_SECTION_RE.finditer(text):
            sec = m.group(1).upper()
            key = f"IT:{sec}"
            if key in found:
                continue
            title = _title_after_section(text, sec.lower()) or _it_offence_title(sec)
            found[key] = {
                "section": sec,
                "law": "IT Act",
                "title": title,
                "label": f"IT Act {sec}" + (f" — {title}" if title else ""),
            }
        if IT_ACT_RE.search(text):
            for m in IT_INLINE_RE.finditer(text):
                sec = m.group(1).upper()
                prefix = text[max(0, m.start() - 40) : m.start()]
                if not re.search(r"\b(?:IT|Information Technology|Cyber)\b", prefix, re.I):
                    continue
                key = f"IT:{sec}"
                if key in found:
                    continue
                title = _it_offence_title(sec)
                found[key] = {
                    "section": sec,
                    "law": "IT Act",
                    "title": title,
                    "label": f"IT Act {sec} — {title}",
                }

    def _sort_key(item: Dict[str, str]) -> Tuple[int, str]:
        s = item["section"]
        num = re.sub(r"[^0-9]", "", s) or "0"
        return (0 if item["law"] == "IPC" else 1, int(num), s)

    return sorted(found.values(), key=_sort_key)


def _it_offence_title(sec: str) -> str:
    titles = {
        "66C": "Identity Theft",
        "66D": "Cheating by Personation",
        "66E": "Violation of Privacy",
        "66F": "Cyber Terrorism",
    }
    return titles.get(sec.upper(), "")


def filter_chunks_by_law(
    chunks: List[Dict[str, Any]],
    requested_laws: List[str],
) -> List[Dict[str, Any]]:
    if not requested_laws or "it_act" in requested_laws:
        return chunks
    filtered: List[Dict[str, Any]] = []
    for ch in chunks:
        text = (ch.get("content") or "").lower()
        is_it_only = bool(IT_ACT_RE.search(text)) and not re.search(
            r"\b(?:ipc|indian penal code|bns)\b", text, re.I
        )
        if "ipc" in requested_laws and is_it_only:
            continue
        if "ipc" in requested_laws or "bns" in requested_laws:
            if re.search(r"\b(?:ipc|indian penal code|bns|section\s+\d)\b", text, re.I):
                ch = dict(ch)
                ch["final_score"] = float(ch.get("final_score", 0.5)) + 0.15
                filtered.append(ch)
            elif not is_it_only:
                filtered.append(ch)
        else:
            filtered.append(ch)
    return filtered if filtered else chunks


def search_entire_document(
    index_dir: Union[str, Path],
    query: str,
    query_type: QueryType,
    *,
    max_chunks: int = 40,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Load all chunks, extract entities, return relevant chunks + structured entities.
    """
    all_chunks = iter_all_index_chunks(index_dir)
    if not all_chunks:
        return [], []

    ql = (query or "").lower()
    try:
        from kb_query_types import is_case_query

        if is_case_query(query):
            keys = [
                k
                for k in (
                    "nirbhaya",
                    "kesavananda",
                    "vishaka",
                    "puttaswamy",
                    "shayara",
                    "maneka gandhi",
                )
                if k in ql
            ]
            if keys:
                matched = [
                    ch
                    for ch in all_chunks
                    if any(k in (ch.get("content") or "").lower() for k in keys)
                ]
                if matched:
                    return matched[:max_chunks], []
    except ImportError:
        pass

    if re.search(r"\b(constitutional rights?|name\s+(?:five|5)\s+.*rights)\b", ql):
        matched = [
            ch
            for ch in all_chunks
            if re.search(
                r"\b(Article\s+\d+|Constitutional Rights|Right to Equality|Right to Freedom)\b",
                ch.get("content") or "",
                re.I,
            )
        ]
        if matched:
            return matched[:max_chunks], []

    laws = _requested_laws(query)
    include_it = (
        "it_act" in laws
        or re.search(r"\b(criminal|offence|offenses?|cyber|it act)\b", ql)
        or query_type in {QueryType.SUMMARY, QueryType.TOPIC_QUERY}
    )
    filtered = filter_chunks_by_law(all_chunks, laws if laws else [])
    if include_it or not laws:
        entities = extract_all_offences_from_chunks(filtered)
    else:
        entities = extract_ipc_sections_from_chunks(filtered, laws_filter=laws or ["ipc"])

    if query_type == QueryType.LIST_EXTRACTION:
        relevant: List[Dict[str, Any]] = []
        for ent in entities:
            sec = ent["section"]
            for ch in filtered:
                if section_in_chunk(ch.get("content", ""), sec):
                    relevant.append(ch)
                    break
        if not relevant:
            relevant = [
                ch
                for ch in filtered
                if re.search(r"\b(?:IPC|Section)\s+\d", ch.get("content", ""), re.I)
            ][:max_chunks]
        return relevant[:max_chunks], entities

    if query_type in {QueryType.SUMMARY, QueryType.TOPIC_QUERY}:
        relevant: List[Dict[str, Any]] = []
        for ent in entities:
            sec = str(ent.get("section", "")).lower()
            law = ent.get("law", "IPC")
            for ch in filtered:
                body = ch.get("content", "")
                if law == "IT Act":
                    if re.search(rf"\b{re.escape(sec)}\b", body, re.I) and IT_ACT_RE.search(body):
                        relevant.append(ch)
                        break
                elif section_in_chunk(body, sec):
                    relevant.append(ch)
                    break
        if not relevant:
            relevant = [
                ch for ch in filtered if OFFENCE_TOPIC_RE.search(ch.get("content", ""))
            ]
        return (relevant or filtered)[:max_chunks], entities

    return filtered[:max_chunks], entities
