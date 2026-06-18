"""
Build smoke-test queries from whatever is actually in the user's FAISS index.

No hardcoded PDF — works for criminal statutes, contracts, policies, judgments, or any upload.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Set

# Fallback only when index introspection finds nothing useful
GENERIC_SMOKE_QUERIES: List[Dict[str, str]] = [
    {"id": "doc_summary", "query": "Summarize the main topics in my uploaded documents"},
    {"id": "doc_obligations", "query": "What are the key obligations or duties described in the documents?"},
    {"id": "doc_parties", "query": "Who are the parties mentioned in the documents?"},
]


def _scan_index_samples(index_dir: Any, *, max_chunks: int = 400) -> List[Dict[str, Any]]:
    """Lightweight docstore scan — no embeddings."""
    try:
        from pathlib import Path

        from rag import _load_docstore_only

        vs = _load_docstore_only(Path(index_dir))
        if not vs:
            return []
        doc_dict = getattr(getattr(vs, "docstore", None), "_dict", None) or {}
        samples: List[Dict[str, Any]] = []
        for doc in list(doc_dict.values())[:max_chunks]:
            content = getattr(doc, "page_content", None) or str(doc)
            meta = dict(getattr(doc, "metadata", None) or {})
            samples.append({"content": content, "metadata": meta})
        return samples
    except Exception:
        return []


def _sections_from_samples(samples: List[Dict[str, Any]]) -> List[str]:
    found: Set[str] = set()
    for s in samples:
        meta = s.get("metadata") or {}
        raw = str(meta.get("section_numbers") or "")
        for part in raw.split(","):
            p = part.strip().lower()
            if p and p.isdigit():
                found.add(p)
        body = (s.get("content") or "")[:800]
        for m in re.finditer(r"\bIPC Section (\d{1,4}[a-z]?)\b", body, re.I):
            found.add(m.group(1).lower())
    return sorted(found, key=lambda x: int(re.sub(r"[a-z]", "", x) or "0"))


def _document_types_from_samples(samples: List[Dict[str, Any]]) -> Set[str]:
    types: Set[str] = set()
    for s in samples:
        dt = str((s.get("metadata") or {}).get("document_type") or "").lower()
        if dt and dt != "unknown":
            types.add(dt)
    return types


def _filenames_from_samples(samples: List[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    seen: Set[str] = set()
    for s in samples:
        fn = str((s.get("metadata") or {}).get("filename") or "").strip()
        if fn and fn not in seen:
            seen.add(fn)
            names.append(fn)
    return names


def _body_has_any(samples: List[Dict[str, Any]], *needles: str) -> bool:
    combined = " ".join((s.get("content") or "")[:500].lower() for s in samples[:80])
    return any(n in combined for n in needles)


def build_smoke_queries_from_index(
    index_dir: Any,
    *,
    max_queries: int = 10,
) -> List[Dict[str, str]]:
    """
    Universal smoke queries derived from indexed PDF content.
    """
    samples = _scan_index_samples(index_dir)
    if not samples:
        return list(GENERIC_SMOKE_QUERIES)

    queries: List[Dict[str, str]] = []
    sections = _sections_from_samples(samples)
    doc_types = _document_types_from_samples(samples)
    filenames = _filenames_from_samples(samples)

    if sections:
        if len(sections) >= 2:
            queries.append(
                {
                    "id": "compare_sections",
                    "query": f"Difference between IPC {sections[0]} and IPC {sections[1]}",
                }
            )
        mid = sections[len(sections) // 2]
        queries.append({"id": "section_explain", "query": f"Explain IPC {mid}"})
        queries.append({"id": "section_punish", "query": f"Punishment under IPC {sections[-1]}"})
        if len(sections) >= 3:
            queries.append(
                {"id": "section_lookup", "query": f"IPC Section {sections[2]}"}
            )
        queries.append({"id": "bare_section", "query": f"section {sections[0]}"})

    if _body_has_any(
        samples,
        "fundamental rights",
        "constitutional rights",
        "article 14",
        "article 19",
        "right to equality",
    ):
        queries.append(
            {
                "id": "constitutional",
                "query": "What fundamental or constitutional rights are described?",
            }
        )

    if doc_types & {"nda", "contract", "agreement"} or _body_has_any(
        samples, "confidential", "non-disclosure", "disclosing party", "indemnity"
    ):
        queries.append(
            {
                "id": "contract",
                "query": "What are the confidentiality or contract obligations in the documents?",
            }
        )

    if doc_types & {"court_judgment"} or _body_has_any(
        samples, "petitioner", "respondent", "court held", "judgment"
    ):
        queries.append(
            {
                "id": "judgment",
                "query": "What did the court hold according to the uploaded judgment?",
            }
        )

    if doc_types & {"legal_notice"} or _body_has_any(samples, "legal notice", "demand notice"):
        queries.append(
            {"id": "notice", "query": "What does the legal notice require?"}
        )

    if doc_types & {"fir"} or _body_has_any(samples, "first information report", "complainant"):
        queries.append({"id": "fir", "query": "Summarize the FIR or complaint details"})

    if doc_types & {"policy_document"} or _body_has_any(samples, "privacy policy", "terms of service"):
        queries.append(
            {"id": "policy", "query": "What are the main policy terms in the document?"}
        )

    if not queries:
        fn = filenames[0] if filenames else "the uploaded document"
        queries.append(
            {
                "id": "generic_summary",
                "query": f"Summarize the main content of {fn}",
            }
        )
        queries.append(
            {
                "id": "generic_key_points",
                "query": "What are the key legal points in my uploaded documents?",
            }
        )

    # Dedupe by query text
    seen: Set[str] = set()
    out: List[Dict[str, str]] = []
    for q in queries:
        key = q["query"].lower()[:80]
        if key not in seen:
            seen.add(key)
            out.append(q)
        if len(out) >= max_queries:
            break

    return out or list(GENERIC_SMOKE_QUERIES)
