"""
Strip dense KB test-document boilerplate and extract structured section fields.

Used by section answers and comparison tables so meta-instructions never
appear as user-facing legal content.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

_TEST_META_RE = re.compile(
    r"\b("
    r"rigorously test retrieval|section mapping,?\s*punishment extraction|"
    r"semantic search,?\s*and legal comparison|should return relevant answers|"
    r"stress test\s+legalease|dense legal testing"
    r")\b",
    re.I,
)

_QUERY_EXAMPLE_RE = re.compile(
    r"^(?:Queries such as|as\s+[\"\u201c]?(?:Explain|Compare|Difference|Punishment))",
    re.I,
)

_BOILERPLATE_LINE_RE = re.compile(
    r"^(?:Explanation:|Example:|Key Legal Point:)\b",
    re.I,
)

_MEANING_RE = re.compile(
    r"Meaning:\s*(.+?)(?=\n(?:Explanation|Example|Key Legal Point|IPC\s+Section|BNS\s+Section|\Z))",
    re.I | re.S,
)

_PUNISHMENT_LABEL_RE = re.compile(
    r"Punishment(?:\s+for\s+[^:\n]+)?:\s*(.+?)(?=\n(?:Explanation|Example|Meaning|IPC\s+Section|\Z))",
    re.I | re.S,
)

_EXPLANATION_RE = re.compile(
    r"Explanation:\s*(.+?)(?=\n(?:Example|Key Legal Point|IPC\s+Section|BNS\s+Section|\Z))",
    re.I | re.S,
)

_EXAMPLE_RE = re.compile(
    r"Example:\s*(.+?)(?=\n(?:Key Legal Point|Explanation|IPC\s+Section|BNS\s+Section|\Z))",
    re.I | re.S,
)

_KEY_LEGAL_POINT_RE = re.compile(
    r"Key Legal Point:\s*(.+?)(?=\n(?:IPC\s+Section|BNS\s+Section|\Z))",
    re.I | re.S,
)

_SECTION_FIELD_LINE_RE = re.compile(
    r"^(?:Meaning|Explanation|Example|Key Legal Point|Punishment)\s*:",
    re.I,
)


_SUGGESTED_QUESTIONS_RE = re.compile(
    r"suggested questions for testing",
    re.I,
)


def is_kb_test_boilerplate(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    # Structured statute fields (Meaning/Explanation/Example) are user-facing content.
    if _SECTION_FIELD_LINE_RE.match(t):
        return False
    if re.search(
        r"\b(?:legalease\s+kb\s+testing\s+document|realistic\s+indian[- ]style\s+legal\s+case\s+compilation|"
        r"created\s+for\s+testing\s+legalease\s+kb\s+retrieval)\b",
        t,
        re.I,
    ):
        return True
    if _SUGGESTED_QUESTIONS_RE.search(t):
        return True
    if _QUERY_EXAMPLE_RE.match(t):
        return True
    if re.search(r"\bExplain IPC \d+[\"'\u201d]?", t):
        return True
    if _TEST_META_RE.search(t):
        return True
    if re.search(r"\btest retrieval accuracy\b", t, re.I):
        return True
    if _BOILERPLATE_LINE_RE.match(t):
        return True
    return False


def is_index_meta_boilerplate(text: str) -> bool:
    """True for test-doc meta pages (suggested question lists, not substantive law)."""
    return is_kb_test_boilerplate(text)


def strip_kb_test_boilerplate(text: str) -> str:
    """Remove test-document instruction lines; keep substantive legal content."""
    if not text:
        return ""
    kept: list[str] = []
    for line in (text or "").splitlines():
        ls = line.strip()
        if not ls:
            if kept and kept[-1]:
                kept.append("")
            continue
        if is_kb_test_boilerplate(ls):
            continue
        kept.append(ls)
    return "\n".join(kept).strip()


def extract_meaning_from_block(block: str) -> str:
    raw = block or ""
    if not raw:
        return ""
    m = _MEANING_RE.search(raw)
    if m:
        meaning = re.sub(r"\s+", " ", m.group(1).strip())
        if meaning and not is_kb_test_boilerplate(meaning):
            return meaning[:500]
    for line in block.splitlines():
        ls = line.strip()
        if ls.lower().startswith("meaning:"):
            val = ls.split(":", 1)[-1].strip()
            if val and not is_kb_test_boilerplate(val):
                return val[:500]
    return ""


def _is_incomplete_section_field(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 20:
        return True
    if re.search(r"\b(?:involving|including|such as)\s*$", t, re.I):
        return True
    return False


def sanitize_section_field(text: str) -> str:
    """Trim query-example tails from dense KB test fields; keep readable prose."""
    if not text:
        return ""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.split(r"\.\s*Queries such as\b", t, maxsplit=1, flags=re.I)[0].strip()
    t = re.split(r"\.\s*as\s+[\"\u201c]?(?:Explain|Compare|Difference|Punishment)\b", t, maxsplit=1, flags=re.I)[0].strip()
    if t.endswith(","):
        t = t[:-1].strip()
    if is_kb_test_boilerplate(t) or _is_incomplete_section_field(t):
        return ""
    return t[:900]


def extract_explanation_from_block(block: str) -> str:
    raw = block or ""
    if not raw:
        return ""
    m = _EXPLANATION_RE.search(raw)
    if m:
        val = sanitize_section_field(m.group(1).strip())
        if val:
            return val
    for line in raw.splitlines():
        ls = line.strip()
        if ls.lower().startswith("explanation:"):
            val = sanitize_section_field(ls.split(":", 1)[-1].strip())
            if val:
                return val
    return ""


def extract_example_from_block(block: str) -> str:
    raw = block or ""
    if not raw:
        return ""
    m = _EXAMPLE_RE.search(raw)
    if m:
        val = sanitize_section_field(m.group(1).strip())
        if val:
            return val
    for line in raw.splitlines():
        ls = line.strip()
        if ls.lower().startswith("example:"):
            val = sanitize_section_field(ls.split(":", 1)[-1].strip())
            if val:
                return val
    return ""


def extract_key_legal_point_from_block(block: str) -> str:
    raw = block or ""
    if not raw:
        return ""
    m = _KEY_LEGAL_POINT_RE.search(raw)
    if m:
        val = sanitize_section_field(m.group(1).strip())
        if val:
            return val
    for line in raw.splitlines():
        ls = line.strip()
        if ls.lower().startswith("key legal point:"):
            val = sanitize_section_field(ls.split(":", 1)[-1].strip())
            if val:
                return val
    return ""


def extract_punishment_from_block(block: str, *, section: str = "", law: str = "") -> str:
    raw = block or ""
    block = strip_kb_test_boilerplate(raw)
    if not raw and not block:
        return ""

    m = _PUNISHMENT_LABEL_RE.search(raw) or (_PUNISHMENT_LABEL_RE.search(block) if block else None)
    if m:
        pun = re.sub(r"\s+", " ", m.group(1).strip())
        if pun and not is_kb_test_boilerplate(pun):
            return pun[:400]

    meaning = extract_meaning_from_block(block)
    if meaning and re.search(
        r"\b(punish|imprisonment|death penalty|life imprisonment|fine|rigorous|years)\b",
        meaning,
        re.I,
    ):
        if ";" in meaning:
            for part in meaning.split(";"):
                part = part.strip()
                if re.search(
                    r"\b(punish|imprisonment|death|life|fine|years|extend)\b", part, re.I
                ):
                    return part[:400]
        for sent in re.split(r"(?<=[.;])\s+", meaning):
            if re.search(
                r"\b(punish|imprisonment|death|life|fine|years|extend)\b", sent, re.I
            ):
                return sent.strip()[:400]

    # Murder / culpable homicide sections often point to separate punishment sections in the same doc.
    sec = (section or "").lower()
    law_u = (law or "IPC").upper()
    src = raw or block
    if sec == "300" and re.search(r"\bmurder\b", src, re.I):
        return (
            "Murder is defined in this section; punishment (death or imprisonment for life "
            "and fine) is typically under IPC Section 302 in your document."
        )
    if sec == "299" and re.search(r"\bculpable homicide\b", src, re.I):
        return (
            "Culpable homicide is defined here; punishment for homicide not amounting to "
            "murder may appear under IPC Section 304 in your document."
        )
    return ""


def parse_section_fields(
    block: str,
    *,
    section: str = "",
    law: str = "IPC",
) -> Dict[str, str]:
    cleaned = strip_kb_test_boilerplate(block or "")
    meaning = extract_meaning_from_block(cleaned)
    explanation = extract_explanation_from_block(cleaned)
    example = extract_example_from_block(cleaned)
    key_point = extract_key_legal_point_from_block(cleaned)
    punishment = extract_punishment_from_block(cleaned, section=section, law=law)
    return {
        "meaning": meaning,
        "explanation": explanation,
        "example": example,
        "key_legal_point": key_point,
        "punishment": punishment,
        "body": cleaned[:1200],
    }


def format_statute_section_fields(
    block: str,
    *,
    section: str = "",
    law: str = "IPC",
) -> str:
    """Render Meaning, Explanation, Example, and related fields from a statute block."""
    fields = parse_section_fields(block, section=section, law=law)
    law_u = (law or "IPC").upper()
    sec_u = (section or "").upper()
    if not sec_u:
        header_m = re.search(r"(?:IPC|BNS)\s+Section\s+(\d+[A-Za-z]?)", block or "", re.I)
        if header_m:
            sec_u = header_m.group(1).upper()
    if not fields.get("meaning") and not fields.get("explanation") and not fields.get("body"):
        return ""

    try:
        from answer_orchestrator import statute_section_heading

        header = statute_section_heading(sec_u or section, law_u)
    except ImportError:
        header = f"## {law_u} Section {sec_u}" if sec_u else f"## {law_u} Section"
    meaning = fields.get("meaning") or ""
    if meaning and sec_u:
        subtitle_m = re.search(
            rf"^(?:IPC|BNS)\s+Section\s+{re.escape(sec_u)}\s*[—–\-]\s*(.+)$",
            (block or "").split("\n", 1)[0],
            re.I,
        )
        if subtitle_m and subtitle_m.group(1).strip().lower() not in header.lower():
            header = f"{header} — {subtitle_m.group(1).strip()}"

    parts: List[str] = [header, ""]
    if meaning:
        parts.append(f"**Meaning:** {meaning}")
    if fields.get("explanation") and not is_kb_test_boilerplate(fields["explanation"]):
        parts.extend(["", f"**Explanation:** {fields['explanation']}"])
    if fields.get("example") and not _is_incomplete_section_field(fields["example"]):
        parts.extend(["", f"**Example:** {fields['example']}"])
    if fields.get("key_legal_point"):
        parts.extend(["", f"**Key Legal Point:** {fields['key_legal_point']}"])
    if fields.get("punishment"):
        parts.extend(["", f"**Punishment:** {fields['punishment']}"])
    if len(parts) <= 2 and fields.get("body"):
        parts.extend(["", fields["body"][:1200]])
    return "\n".join(parts).strip()
