"""
Legal domain router — classify query domain BEFORE retrieval.

Priority: deterministic routing → exact entity → scoped retrieval → semantic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from backend.app.core.constitutional_concept_map import (
    expand_constitutional_query,
    is_constitutional_query,
    resolve_article,
    resolve_topic,
)


class LegalDomain(str, Enum):
    IPC = "ipc"
    BNS = "bns"
    CONSTITUTION = "constitution"
    CASE_LAW = "case_law"
    CONTRACT = "contract"
    NDA = "nda"
    FIR = "fir"
    PROPERTY = "property"
    PERSONAL_DOC = "personal_doc"
    GENERAL_DOC = "general_doc"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class DomainRoute:
    domain: LegalDomain
    expanded_query: str = ""
    article: str = ""
    constitutional_topic: str = ""
    block_ipc: bool = False
    block_bns: bool = False


def route_legal_domain(query: str) -> DomainRoute:
    q = (query or "").strip()
    ql = q.lower()

    try:
        from kb_query_types import is_case_query

        if is_case_query(q):
            return DomainRoute(domain=LegalDomain.CASE_LAW)
    except ImportError:
        pass

    if is_constitutional_query(q):
        art = resolve_article(q) or ""
        topic = resolve_topic(q) or ""
        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "CONST",
                "legal_domain_router.py:route_legal_domain",
                "domain_constitution",
                {"query": q[:100], "article": art, "topic": topic},
            )
        except Exception:
            pass
        # endregion
        return DomainRoute(
            domain=LegalDomain.CONSTITUTION,
            expanded_query=expand_constitutional_query(q),
            article=art,
            constitutional_topic=topic,
            block_ipc=True,
            block_bns=True,
        )

    if re.search(r"\bipc\b", ql) or re.search(
        r"\b(?:indian penal code)\b", ql
    ):
        return DomainRoute(domain=LegalDomain.IPC, block_bns=False)

    if re.search(r"\bbns\b", ql) or re.search(r"\bbharatiya nyaya\b", ql):
        return DomainRoute(domain=LegalDomain.BNS)

    if re.search(r"\b(?:fir|first information report|police station|complainant)\b", ql):
        return DomainRoute(domain=LegalDomain.FIR)

    if re.search(r"\b(?:nda|non[- ]?disclosure|confidentiality)\b", ql):
        return DomainRoute(domain=LegalDomain.NDA)

    if re.search(
        r"\b(?:contract|agreement|termination|party a|party b|indemnity|consideration)\b",
        ql,
    ):
        return DomainRoute(domain=LegalDomain.CONTRACT)

    if re.search(r"\b(?:petitioner|respondent|judgment|judgement|bench|hon'?ble)\b", ql):
        return DomainRoute(domain=LegalDomain.CASE_LAW)

    if re.search(r"\b(?:registry|sale deed|immovable property|land record)\b", ql):
        return DomainRoute(domain=LegalDomain.PROPERTY)

    try:
        from document_classifier import is_contract_topic_query

        if is_contract_topic_query(q):
            return DomainRoute(domain=LegalDomain.CONTRACT)
    except Exception:
        pass

    try:
        from kb_query_types import is_case_query

        if is_case_query(q):
            return DomainRoute(domain=LegalDomain.CASE_LAW)
    except Exception:
        pass

    if re.search(r"\bsection\s+\d{1,4}\b", ql) and not re.search(
        r"\b(?:right|article|constitution|fundamental)\b", ql
    ):
        return DomainRoute(domain=LegalDomain.IPC)

    return DomainRoute(domain=LegalDomain.UNKNOWN)


def _is_case_narrative_for_constitution(body: str) -> bool:
    """Case PDF chunks that only mention Article N in passing — not a rights list."""
    bl = (body or "").lower()
    if re.search(r"\bcase\s+\d+\s*:", bl) and (
        "fir no" in bl or "hearing" in bl or re.search(r"\bvs\.?\s+", bl)
    ):
        return True
    if bl.count("hearing") >= 2 and not re.search(r"fundamental\s+rights", bl):
        return True
    return False


def filter_chunks_for_domain(
    chunks: List[dict],
    route: DomainRoute,
) -> List[dict]:
    """Drop IPC/BNS contamination when domain is constitutional."""
    if route.domain != LegalDomain.CONSTITUTION:
        return chunks
    out: List[dict] = []
    for ch in chunks or []:
        body = (ch.get("content") or "").lower()
        raw = ch.get("content") or ""
        if _is_case_narrative_for_constitution(raw):
            continue
        if re.search(r"\bipc\s+section\s+\d", body) and not re.search(
            r"\barticle\s+\d", body
        ):
            continue
        if re.search(r"\bbns\s+section\s+\d", body) and not re.search(
            r"\barticle\s+\d", body
        ):
            continue
        out.append(ch)
    return out if out else list(chunks or [])
