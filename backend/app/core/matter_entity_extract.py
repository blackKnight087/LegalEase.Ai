"""Structured entity extraction for matters — no sentence garbage."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

_BAD_NAME_WORDS = frozenset(
    {
        "applicable",
        "accused",
        "victim",
        "witness",
        "murder",
        "case",
        "court",
        "hearing",
        "police",
        "station",
        "stated",
        "heard",
        "screams",
        "argued",
        "denied",
        "prosecution",
        "defense",
        "defence",
        "ipc",
        "fir",
        "report",
        "document",
        "matter",
        "state",
        "india",
        "sections",
        "section",
    }
)

_PERSON_NAME = r"([A-Z][a-z]+\s+[A-Z][a-z]+)"

_HEADER_FIELDS = (
    (rf"^Victim\s*\r?\n\s*{_PERSON_NAME}\s*(?:\r?\n|$)", "victim", "Victim"),
    (rf"^Accused\s*\r?\n\s*{_PERSON_NAME}\s*(?:\r?\n|$)", "accused", "Accused"),
    (r"^Court\s*\r?\n\s*([^\r\n]{3,60})\s*(?:\r?\n|$)", "court", ""),
    (r"^Police Station\s*\r?\n\s*([^\r\n]{3,60})\s*(?:\r?\n|$)", "police_station", ""),
    (r"^FIR No\.?\s*\r?\n\s*([^\r\n]+)\s*(?:\r?\n|$)", "fir", ""),
    (r"^Case No\.?\s*\r?\n\s*([^\r\n]+)\s*(?:\r?\n|$)", "case_number", ""),
    (r"^Next Hearing\s*\r?\n\s*(\d{1,2}\s+\w+\s+\d{4})\s*(?:\r?\n|$)", "date", ""),
)

_WITNESS_BLOCK = re.compile(
    rf"WITNESS\s+STATEMENT\s*[–\-]\s*{_PERSON_NAME}",
    re.I,
)

_IPC_SECTION = re.compile(r"\bIPC\s*(\d{1,4})\b", re.I)
_DATE = re.compile(
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
    re.I,
)

_KNOWN_LOCATIONS = (
    "Salt Lake Warehouse",
    "Bidhannagar Police Station",
    "Howrah Police Station",
)


def _clean_name(raw: str) -> str:
    s = (raw or "").split("\n")[0].strip()
    s = re.sub(r"\s+", " ", s)
    for sep in (" Accused", " Victim", " Applicable", " Witness", " IPC", ","):
        if sep in s:
            s = s.split(sep)[0].strip()
    return s[:50]


def _valid_person_name(name: str) -> bool:
    n = _clean_name(name)
    words = n.split()
    if len(words) != 2:
        return False
    if not all(w[0].isupper() and w.isalpha() for w in words):
        return False
    low = n.lower()
    if any(b in low for b in _BAD_NAME_WORDS):
        return False
    return True


def _norm_date(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip())


def extract_structured_entities(text: str) -> List[Tuple[str, str, float, Dict[str, Any]]]:
    """Returns (entity_type, label, confidence, metadata)."""
    if not text:
        return []
    found: List[Tuple[str, str, float, Dict[str, Any]]] = []
    seen: Set[str] = set()

    def add(etype: str, label: str, conf: float, meta: Optional[Dict[str, Any]] = None) -> None:
        label = re.sub(r"\s+", " ", label.strip())[:80]
        if etype in ("victim", "accused", "witness", "person", "judge"):
            label = " ".join(w.capitalize() for w in label.split())
        if len(label) < 2:
            return
        if etype in ("victim", "accused", "witness", "person", "judge") and not _valid_person_name(
            label
        ):
            return
        key = f"{etype}:{label.lower()}"
        if key in seen:
            return
        seen.add(key)
        found.append((etype, label, conf, meta or {}))

    head = text[:5000]
    for pat, etype, role in _HEADER_FIELDS:
        m = re.search(pat, head, re.I | re.M)
        if m:
            lbl = m.group(1).strip()
            meta = {"role": role} if role else {}
            add(etype, lbl, 0.96, meta)

    for m in _WITNESS_BLOCK.finditer(text):
        add("witness", _clean_name(m.group(1)), 0.92, {"role": "Witness"})

    ipc_nums: Set[str] = set()
    sec_block = re.search(r"IPC\s+Sections?:?\s*([\d,\s]+)", text[:4000], re.I)
    if sec_block:
        for num in re.findall(r"\d{1,4}", sec_block.group(1)):
            ipc_nums.add(num)
    for m in _IPC_SECTION.finditer(text):
        ipc_nums.add(m.group(1))
    for num in sorted(ipc_nums, key=int):
        add("law", f"IPC {num}", 0.93, {})

    date_seen: Set[str] = set()
    for m in _DATE.finditer(text):
        dt = _norm_date(m.group(1))
        if len(dt) < 8 or dt.lower() in date_seen:
            continue
        date_seen.add(dt.lower())
        if len(date_seen) > 8:
            break
        add("date", dt, 0.88, {})

    for loc in _KNOWN_LOCATIONS:
        if loc.lower() in text.lower():
            add("location", loc, 0.9, {})

    return found
