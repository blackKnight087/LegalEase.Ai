"""
Legal section mapping — IPC↔BNS, CrPC↔BNSS, Evidence↔BSA.

Used for comparison queries, auto-linking, and cross-code retrieval.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# IPC section → BNS section (substantive criminal law)
IPC_TO_BNS: Dict[str, str] = {
    "302": "103",
    "300": "101",
    "299": "100",
    "307": "109",
    "304": "104",
    "304a": "106",
    "375": "63",
    "376": "64",
    "420": "318",
    "498a": "84",
    "354": "74",
    "363": "137",
    "376a": "65",
    "302a": "103",
}

# CrPC → BNSS (procedure)
CRPC_TO_BNSS: Dict[str, str] = {
    "154": "173",
    "437": "480",
    "438": "481",
    "439": "482",
    "125": "144",
    "156": "175",
}

# Evidence Act → BSA
EVIDENCE_TO_BSA: Dict[str, str] = {
    "3": "3",
    "65b": "63",
    "45": "45",
}

LAW_ALIASES = {
    "ipc": "IPC",
    "indian penal code": "IPC",
    "bns": "BNS",
    "bharatiya nyaya sanhita": "BNS",
    "crpc": "CrPC",
    "cr pc": "CrPC",
    "cr.pc": "CrPC",
    "code of criminal procedure": "CrPC",
    "bnss": "BNSS",
    "bharatiya nagarik suraksha sanhita": "BNSS",
    "evidence act": "Evidence Act",
    "indian evidence act": "Evidence Act",
    "bsa": "BSA",
    "bharatiya sakshya adhiniyam": "BSA",
}

LAW_FULL_NAMES = {
    "IPC": "Indian Penal Code (IPC), 1860",
    "BNS": "Bharatiya Nyaya Sanhita (BNS), 2023",
    "CrPC": "Code of Criminal Procedure (CrPC), 1973",
    "BNSS": "Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023",
    "Evidence Act": "Indian Evidence Act, 1872",
    "BSA": "Bharatiya Sakshya Adhiniyam (BSA), 2023",
}

LAW_REPLACEMENTS = {
    "IPC": "BNS",
    "CrPC": "BNSS",
    "Evidence Act": "BSA",
}


def normalize_law_code(raw: str) -> str:
    key = (raw or "").strip().lower()
    return LAW_ALIASES.get(key, raw.strip())


def map_section(old_law: str, section: str) -> Optional[str]:
    """Map old-law section to new-law equivalent."""
    law = normalize_law_code(old_law)
    sec = (section or "").lower().strip()
    if not sec:
        return None
    if law == "IPC":
        return IPC_TO_BNS.get(sec)
    if law == "CrPC":
        return CRPC_TO_BNSS.get(sec)
    if law == "Evidence Act":
        return EVIDENCE_TO_BSA.get(sec)
    return None


def reverse_map_section(new_law: str, section: str) -> Optional[str]:
    """Map new-law section back to old-law equivalent."""
    law = normalize_law_code(new_law)
    sec = (section or "").lower().strip()
    if law == "BNS":
        for ipc, bns in IPC_TO_BNS.items():
            if bns.lower() == sec:
                return ipc
    if law == "BNSS":
        for crpc, bnss in CRPC_TO_BNSS.items():
            if bnss.lower() == sec:
                return crpc
    if law == "BSA":
        for ev, bsa in EVIDENCE_TO_BSA.items():
            if bsa.lower() == sec:
                return ev
    return None


def parse_mapping_row(text: str) -> List[Tuple[str, str, str, str]]:
    """
    Parse mapping chart lines like 'IPC 302 → BNS 103'.
    Returns list of (old_law, old_sec, new_law, new_sec).
    """
    results: List[Tuple[str, str, str, str]] = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.search(
            r"\b(IPC|CrPC|Evidence Act)\s*(\d{1,4}[a-z]?)\s*[→\-\–—>]+\s*(BNS|BNSS|BSA)\s*(\d{1,4}[a-z]?)",
            line,
            re.I,
        )
        if m:
            results.append(
                (
                    normalize_law_code(m.group(1)),
                    m.group(2).lower(),
                    normalize_law_code(m.group(3)),
                    m.group(4).lower(),
                )
            )
    return results


def enrich_entities_with_mapping(entities: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Auto-link missing counterpart via mapping table (only when mapping intent)."""
    if len(entities) >= 2:
        types = {normalize_law_code(e.get("type", "")) for e in entities}
        secs = [e.get("section", "") for e in entities if e.get("section")]
        if len(secs) >= 2 and len(types) == 1 and types <= {"IPC"}:
            return [dict(e) for e in entities]
        if len(secs) >= 2 and types <= {"BNS"}:
            return [dict(e) for e in entities]

    if len(entities) < 2:
        out = [dict(e) for e in entities]
        if len(out) == 1:
            e = out[0]
            mapped = map_section(e.get("type", ""), e.get("section", ""))
            if mapped:
                new_law = LAW_REPLACEMENTS.get(normalize_law_code(e.get("type", "")))
                if new_law:
                    out.append({"type": new_law, "section": mapped, "auto_linked": True})
        return out

    types = {normalize_law_code(e.get("type", "")) for e in entities}
    has_old = bool(types & {"IPC", "CrPC", "Evidence Act"})
    has_new = bool(types & {"BNS", "BNSS", "BSA"})
    if has_old and has_new:
        return [dict(e) for e in entities]

    out = [dict(e) for e in entities]
    if len(out) == 1 and has_old:
        e = out[0]
        mapped = map_section(e.get("type", ""), e.get("section", ""))
        new_law = LAW_REPLACEMENTS.get(normalize_law_code(e.get("type", "")))
        if mapped and new_law:
            out.append({"type": new_law, "section": mapped, "auto_linked": True})
    return out
