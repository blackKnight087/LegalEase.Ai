"""
Deterministic constitutional concept → Article mapping and query expansion.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Longest phrases first when matching
RIGHT_TO_ARTICLE: Dict[str, str] = {
    "right to equality": "14",
    "equality before law": "14",
    "equal protection": "14",
    "right to freedom of speech": "19",
    "freedom of speech": "19",
    "right to freedom": "19",
    "right against exploitation": "23",
    "right to freedom of religion": "25",
    "right to religion": "25",
    "freedom of religion": "25",
    "right to constitutional remedies": "32",
    "constitutional remedies": "32",
    "right to life and personal liberty": "21",
    "right to life": "21",
    "personal liberty": "21",
    "equality": "14",
    "exploitation": "23",
    "religion": "25",
    "freedom": "19",
}

ARTICLE_TITLES: Dict[str, str] = {
    "14": "Right to Equality",
    "19": "Right to Freedom",
    "21": "Right to Life",
    "23": "Right Against Exploitation",
    "25": "Right to Freedom of Religion",
    "32": "Right to Constitutional Remedies",
}

ARTICLE_BASELINE: Dict[str, Dict[str, str]] = {
    "14": {
        "meaning": (
            "Guarantees equality before the law and equal protection of laws to every person."
        ),
        "purpose": "Prevents arbitrary discrimination and unequal treatment by the State.",
        "key_point": "The State cannot unfairly discriminate between citizens.",
    },
    "19": {
        "meaning": "Protects freedoms including speech, assembly, association, movement, and profession.",
        "purpose": "Enables democratic participation and personal liberty subject to reasonable restrictions.",
        "key_point": "Freedoms are not absolute — reasonable restrictions are permitted under the Constitution.",
    },
    "21": {
        "meaning": "Protects life and personal liberty — no person shall be deprived except by procedure established by law.",
        "purpose": "Foundation for due process, dignity, and expanded rights through judicial interpretation.",
        "key_point": "Procedure must be fair, just, and reasonable — not arbitrary.",
    },
    "23": {
        "meaning": "Prohibits traffic in human beings, begar, and other similar forms of forced labour.",
        "purpose": "Protects human dignity and bans exploitative labour practices.",
        "key_point": "Forced labour and trafficking are constitutionally prohibited.",
    },
    "25": {
        "meaning": "Guarantees freedom of conscience and the right to profess, practise, and propagate religion.",
        "purpose": "Allows religious liberty subject to public order, morality, and health.",
        "key_point": "Religious freedom is protected but not unlimited.",
    },
    "32": {
        "meaning": "Provides the right to move the Supreme Court for enforcement of Fundamental Rights.",
        "purpose": "Acts as the constitutional remedy when other rights are violated.",
        "key_point": "Called the heart and soul of the Constitution by Dr. Ambedkar.",
    },
}

_CONSTITUTIONAL_CUE_RE = re.compile(
    r"\b(right\s+to|fundamental\s+rights?|constitutional\s+rights?|constitution|article\s+\d+)\b",
    re.I,
)


def is_constitutional_query(query: str) -> bool:
    ql = (query or "").lower()
    try:
        from kb_query_types import is_case_query

        if is_case_query(query):
            return False
    except ImportError:
        if re.search(r"\b\w+(?:\s+\w+){0,4}\s+vs\.?\s+\w+", query or "", re.I):
            return False
    if is_constitutional_rights_list_query(query):
        return True
    if _CONSTITUTIONAL_CUE_RE.search(ql):
        return True
    if resolve_article(query):
        return True
    if re.search(r"\bwhat are (?:the )?constitutional rights\b", ql):
        return True
    if re.search(r"\bname\s+(?:five|5)\s+.*rights\b", ql):
        return True
    return False


def is_constitutional_rights_list_query(query: str) -> bool:
    """List/name/enumerate fundamental or constitutional rights (not single-article explain)."""
    ql = (query or "").lower().strip()
    if not ql:
        return False
    try:
        from kb_query_types import is_case_query

        if is_case_query(query):
            return False
    except ImportError:
        if re.search(r"\b\w+(?:\s+\w+){0,4}\s+vs\.?\s+\w+", query or "", re.I):
            return False
    if re.search(r"\bexplain\b", ql) and re.search(r"\bright\s+to\b", ql):
        return False
    if resolve_article(query) and not re.search(
        r"\b(?:five|5|list|name|what are|enumerate|state)\b", ql
    ):
        return False
    if re.search(r"\b(?:five|5)\s+constitutional\s+rights?\b", ql):
        return True
    if re.search(
        r"\b(?:what are|name|list|enumerate|state|give)\s+(?:the\s+)?"
        r"(?:(?:five|5)\s+)?(?:fundamental|constitutional)\s+rights?\b",
        ql,
    ):
        return True
    if re.search(r"\b(?:five|5)\b", ql) and "constitutional" in ql and "right" in ql:
        return True
    if ql in ("fundamental rights", "constitutional rights", "five constitutional rights"):
        return True
    if re.search(r"\bfundamental\s+rights?\b", ql) and not re.search(
        r"\bexplain\b", ql
    ):
        return True
    return False


def extract_constitutional_rights_block(text: str) -> str:
    """Isolate the rights enumeration block from mixed KB test / multi-topic chunks."""
    body = re.sub(r"\(cid:\d+\)\s*", "", text or "")
    body = re.sub(r"\s+", " ", body).strip()
    if not body:
        return ""
    m = re.search(
        r"(?:Five Constitutional Rights|Fundamental Rights)(?:\s*\([^)]*\))?\s*[:.]?\s*",
        body,
        re.I,
    )
    if m:
        segment = body[m.start() :]
        end = re.search(
            r"\b(?:BNS\s+Section|IPC\s+Section|Case\s+\d+|Suggested\s+KB|"
            r"Compare\s+IPC|Sample\s+(?:Non[- ]?)?Disclosure|Parties involved)\b",
            segment[40:],
            re.I,
        )
        if end:
            segment = segment[: 40 + end.start()]
        return segment.strip()
    return body


def resolve_article(query: str) -> Optional[str]:
    """Map query text to Article number, if any."""
    ql = (query or "").lower()
    m = re.search(r"\barticle\s+(\d{1,3}[a-z]?)\b", ql, re.I)
    if m:
        return m.group(1).lower()
    for phrase, art in sorted(RIGHT_TO_ARTICLE.items(), key=lambda x: -len(x[0])):
        if phrase in ql:
            return art
    return None


def resolve_topic(query: str) -> str:
    art = resolve_article(query)
    if art and art in ARTICLE_TITLES:
        return ARTICLE_TITLES[art].lower()
    ql = (query or "").lower()
    for phrase in sorted(RIGHT_TO_ARTICLE.keys(), key=len, reverse=True):
        if phrase in ql:
            return phrase
    if "constitutional rights" in ql or "fundamental rights" in ql:
        return "constitutional rights"
    return ""


def _count_articles_in_text(text: str) -> int:
    return len(re.findall(r"\barticle\s+\d{1,3}\b", text or "", re.I))


def extract_article_snippet(
    text: str,
    article: str,
    *,
    topic: str = "",
) -> str:
    """Pull one right's text from a comma-separated constitutional list line."""
    art = (article or "").strip().lower()
    if not art or not text:
        return ""
    body = (text or "").strip()
    if _count_articles_in_text(body) <= 1 and re.search(rf"\barticle\s*{re.escape(art)}\b", body, re.I):
        return body[:800]

    patterns = [
        re.compile(
            rf"(Right\s+(?:to|against)\s+[^,(]+?\(\s*Article\s+{re.escape(art)}\s*\))",
            re.I,
        ),
        re.compile(
            rf"(\d+\.\s*Right[^.(]+?\(\s*Article\s+{re.escape(art)}\s*\))",
            re.I,
        ),
        re.compile(rf"([^,.]+?\(\s*Article\s+{re.escape(art)}\s*\))", re.I),
    ]
    for pat in patterns:
        m = pat.search(body)
        if m:
            return m.group(1).strip().rstrip(".,;")

    if topic:
        tl = topic.lower()
        for part in re.split(r"[,;]", body):
            part = part.strip()
            if tl in part.lower() and re.search(rf"\barticle\s*{re.escape(art)}\b", part, re.I):
                return part[:400]
    return ""


def is_constitutional_follow_up(query: str) -> bool:
    ql = (query or "").lower().strip()
    if is_constitutional_query(query):
        return False
    if len(ql.split()) > 14:
        return False
    cues = (
        "summarize",
        "summary",
        "key points",
        "key point",
        "main points",
        "in simple",
        "simple language",
        "explain more",
        "tell me more",
        "elaborate",
        "what does it mean",
        "purpose",
        "meaning",
    )
    return any(c in ql for c in cues)


def expand_constitutional_query(query: str) -> str:
    """Deterministic expansion before retrieval — never IPC."""
    art = resolve_article(query)
    topic = resolve_topic(query)
    parts = [query.strip()]
    if art:
        parts.append(f"Article {art.upper()} {ARTICLE_TITLES.get(art, '')} Constitution of India")
    if topic and topic not in (query or "").lower():
        parts.append(topic)
    parts.append("Fundamental Rights Constitution of India")
    return " ".join(p for p in parts if p)


def format_article_answer(
    article: str,
    *,
    topic: str = "",
    doc_snippet: str = "",
    chunks: Optional[List[Dict]] = None,
) -> str:
    """Structured constitutional answer — doc-grounded with baseline fill."""
    art = (article or "").strip().lower()
    title = ARTICLE_TITLES.get(art, topic.title() or f"Article {art.upper()}")
    base = ARTICLE_BASELINE.get(art, {})
    lines = [f"## {title} (Article {art.upper()})", ""]

    snippet = (doc_snippet or "").strip()
    if snippet:
        isolated = extract_article_snippet(snippet, art, topic=topic) or snippet
        if _count_articles_in_text(isolated) > 1:
            isolated = extract_article_snippet(isolated, art, topic=topic) or ""
        snippet = isolated
    use_snippet = bool(
        snippet
        and not re.search(r"\bipc\s+section\s+\d", snippet, re.I)
        and _count_articles_in_text(snippet) <= 1
        and len(snippet) > 15
    )
    if use_snippet:
        lines.append(snippet[:800])
        lines.append("")
    else:
        if base.get("meaning"):
            lines.extend(["### Meaning", base["meaning"], ""])
        if base.get("purpose"):
            lines.extend(["### Purpose", base["purpose"], ""])
        if base.get("key_point"):
            lines.extend(["### Key Point", base["key_point"], ""])
        if doc_snippet and re.search(r"\bipc\s+section", doc_snippet, re.I):
            lines.append(
                "_Your indexed documents did not contain a dedicated Article "
                f"{art.upper()} passage; the summary above reflects standard constitutional "
                "principles. Upload a constitutional text for document-specific wording._"
            )
            lines.append("")

    try:
        from citation_formatter import polish_kb_response

        return polish_kb_response("\n".join(lines).strip(), chunks or [])
    except Exception:
        return "\n".join(lines).strip()


def list_rights_answer(chunks: Optional[List] = None) -> str:
    """Five rights list when document lacks enumeration."""
    items = [
        f"**{ARTICLE_TITLES[a]}** (Article {a})" for a in ("14", "19", "23", "25", "32")
    ]
    body = "## Constitutional Rights\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))
    try:
        from answer_orchestrator import format_constitutional_rights_answer

        if chunks:
            doc = format_constitutional_rights_answer("What are constitutional rights?", chunks)
            if doc and "Constitutional Rights" in doc:
                return doc
    except Exception:
        pass
    try:
        from citation_formatter import polish_kb_response

        return polish_kb_response(body, chunks or [])
    except Exception:
        return body
