"""

Safe post-processing for KB answers before they reach the client.

"""

from __future__ import annotations



import re

from difflib import SequenceMatcher

from typing import Any, Dict, List, Optional, Tuple



_PROMPT_LEAK_RE = re.compile(

    r"(?i)(document context|not_found|task:|length:|you are legalease|"

    r"reply exactly with the not_found|temperature discipline)"

)

_TRIPLE_HASH_ARTIFACT_RE = re.compile(r"(?<!\n)#{4,}\s*")

_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")

_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

_PAGE_NOISE_RE = re.compile(

    r"Page\s+\d+\s*[—–-]\s*[^\n]{0,80}(?=\s*Section|\s*IPC|\s*BNS|$)",

    re.I,

)

_NOT_FOUND_INLINE = re.compile(

    r"(?:I could(?:n't| not) find(?: a clear reference to that| this information)?"

    r" in the uploaded legal documents\.?|"

    r"I checked the uploaded legal documents[^\n.]*\.?|"

    r"this explanation is drawn only from your uploaded document\.?)\s*",

    re.I,

)

_SOURCE_INLINE_RE = re.compile(

    r"\n*\*{0,2}Source\*{0,2}\s*:\s*[^\n]+(?:\s*·\s*[^\n]+)?\s*$",

    re.I | re.M,

)

_SECTION_HEADER_LINE_RE = re.compile(

    r"^(?:#+\s*)?(?:IPC|BNS|CrPC)?\s*Section\s+\d{1,4}[a-z]?\s*[—–\-:]",

    re.I | re.M,

)

_TABLE_LINE_RE = re.compile(r"^\s*\|.+\|\s*$")

_BULLET_LINE_RE = re.compile(r"^\s*[-*•]\s+")





def dedupe_lines(text: str) -> str:

    seen = set()

    out: List[str] = []

    for line in (text or "").splitlines():

        key = re.sub(r"\s+", " ", line.strip().lower())

        if not key or key in seen:

            continue

        seen.add(key)

        out.append(line.strip())

    return "\n".join(out)





def _sentence_key(sentence: str) -> str:

    t = re.sub(r"[^\w\s]", "", (sentence or "").lower())

    t = re.sub(r"\s+", " ", t).strip()

    return t[:120]





def _is_fuzzy_duplicate(a: str, b: str, threshold: float = 0.82) -> bool:

    if not a or not b:

        return False

    ka, kb = _sentence_key(a), _sentence_key(b)

    if not ka or not kb:

        return False

    if ka == kb:

        return True

    if len(ka) > 30 and (ka in kb or kb in ka):

        return True

    return SequenceMatcher(None, ka, kb).ratio() >= threshold





def deduplicate_response(text: str) -> str:

    """Remove repeated sentences, section headers, and fuzzy duplicate blocks."""

    if not text:

        return ""



    lines = dedupe_lines(text).splitlines()

    if not lines:

        return ""



    out_lines: List[str] = []

    seen_lines: set = set()

    seen_sentences: List[str] = []



    for line in lines:
        stripped = line.strip()
        key = re.sub(r"\s+", " ", stripped.lower())

        if not key:
            out_lines.append("")
            continue

        if _TABLE_LINE_RE.match(stripped):
            if key in seen_lines:
                continue
            seen_lines.add(key)
            out_lines.append(stripped)
            continue

        if _BULLET_LINE_RE.match(stripped):
            label_m = re.match(
                r"^\s*[-*•]\s+\*{0,2}([^*:\n]+?)\*{0,2}\s*:",
                stripped,
                re.I,
            )
            bullet_key = (
                re.sub(r"\s+", " ", label_m.group(1).strip().lower())
                if label_m
                else key[:160]
            )
            if bullet_key in seen_lines:
                continue
            if any(_is_fuzzy_duplicate(stripped, prev) for prev in seen_sentences if len(prev) > 25):
                continue
            seen_lines.add(bullet_key)
            seen_lines.add(key)
            seen_sentences.append(stripped)
            out_lines.append(stripped)
            continue

        if key in seen_lines:
            continue

        if _SECTION_HEADER_LINE_RE.match(stripped) and key in seen_lines:
            continue

        if stripped.startswith("#"):
            seen_lines.add(key)
            out_lines.append(stripped)
            continue

        if not stripped.startswith("#"):

            parts = re.split(r"(?<=[.!?])\s+", line.strip())

            kept: List[str] = []

            for part in parts:

                p = part.strip()

                if len(p) < 12:

                    if p:

                        kept.append(p)

                    continue

                if any(_is_fuzzy_duplicate(p, s) for s in seen_sentences):

                    continue

                seen_sentences.append(p)

                kept.append(p)

            if kept:

                new_line = " ".join(kept)

                nk = re.sub(r"\s+", " ", new_line.lower())

                if nk not in seen_lines:

                    seen_lines.add(nk)

                    out_lines.append(new_line)

            continue



        seen_lines.add(key)

        out_lines.append(line.strip())



    return "\n".join(out_lines)





def _normalize_markdown_tables(text: str) -> str:
    """Ensure table rows are on separate lines for GFM rendering."""
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.count("|") >= 4 and not _TABLE_LINE_RE.match(stripped):
            parts = re.split(r"(?<=\|)\s*(?=\|)", stripped)
            if len(parts) > 2:
                for chunk in re.findall(r"\|[^|]+\|", stripped):
                    out.append(chunk.strip())
                continue
        out.append(stripped if stripped else "")
    return "\n".join(out)


def strip_section_leadin(
    text: str,
    section: str,
    law: str = "IPC",
    subtitle: str = "",
) -> str:
    """Remove echoed section titles from body text — never strip markdown # titles."""
    if not text or not section:
        return text

    title_line_re = re.compile(
        rf"^#{{1,3}}\s*(?:{law}\s+)?Section\s*{re.escape(section)}\b",
        re.I,
    )
    lines = text.splitlines()
    if len(lines) > 1:
        out: List[str] = []
        for line in lines:
            if title_line_re.match(line.strip()):
                out.append(line.strip())
                continue
            if line.strip().startswith("##"):
                out.append(line.strip())
                continue
            out.append(_strip_section_leadin_inline(line, section, law, subtitle))
        return "\n".join(out)

    if title_line_re.match(text.strip()):
        return text.strip()
    return _strip_section_leadin_inline(text, section, law, subtitle)


def _strip_section_leadin_inline(
    text: str,
    section: str,
    law: str = "IPC",
    subtitle: str = "",
) -> str:
    sec = re.escape(section)
    sub_pat = re.escape(subtitle) if subtitle else r"[^:\n]{0,60}"
    patterns = [
        rf"(?:{law}\s+)?Section\s*{sec}\s*[—–\-]\s*{sub_pat}\s*:?\s*",
        rf"Section\s*{sec}\s*(?:{law})?\s*[—–\-]\s*{sub_pat}\s*:?\s*",
        rf"Section\s*{sec}\s*[—–\-]\s*{sub_pat}\s*:?\s*",
        rf"(?:{law}\s+)?Section\s*{sec}\s*[—–\-]\s*",
        rf"Section\s*{sec}\s*:?\s*",
    ]
    t = text
    for _ in range(3):
        prev = t
        for pat in patterns:
            t = re.sub(pat, "", t, flags=re.I)
        if t == prev:
            break
    return re.sub(r"\s{2,}", " ", t).strip()


def collapse_inline_section_duplicates(
    text: str,
    section: str,
    law: str = "IPC",
    subtitle: str = "",
) -> str:
    """Fix same-line repeat: 'IPC Section 307 — X  Section 307 – X: body'."""
    if not text or not section:
        return text
    sub = subtitle or r"Attempt to [Mm]urder|Murder|Culpable Homicide|[A-Za-z ]{3,40}"
    sec = re.escape(section)
    dup = re.compile(
        rf"((?:#+\s*)?(?:{law}\s+)?Section\s*{sec}\s*[—–\-]\s*(?:{sub})\s*)"
        rf"(?:Section\s*{sec}\s*(?:{law})?\s*[—–\-]\s*(?:{sub})\s*:?\s*)+",
        re.I,
    )
    return dup.sub(r"\1", text)


def strip_redundant_section_titles(text: str, section: str, law: str = "IPC") -> str:
    """Remove echoed section headers; keep the first markdown # title."""
    if not text or not section:
        return text
    sec = section.lower()
    patterns = [
        rf"^(?:{law}\s+)?Section\s*{re.escape(sec)}\s*[—–\-:][^\n]*$",
        rf"^Section\s*{re.escape(sec)}\s*(?:{law})?\s*[—–\-:][^\n]*$",
        rf"^Section\s*{re.escape(sec)}\s*[—–\-:][^\n]*$",
    ]
    out: List[str] = []
    kept_main_title = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and re.search(rf"Section\s*{re.escape(sec)}\b", stripped, re.I):
            if not kept_main_title:
                out.append(line)
                kept_main_title = True
            continue
        if any(re.match(p, stripped, re.I) for p in patterns):
            continue
        if (
            re.match(rf"^Section\s*{re.escape(sec)}\b", stripped, re.I)
            and len(stripped) < 90
            and not stripped.startswith("#")
        ):
            continue
        out.append(line)
    return "\n".join(out)





def strip_embedded_source(text: str) -> str:

    """Remove Source: lines from answer body (rendered separately in UI)."""

    t = (text or "").strip()

    t = _SOURCE_INLINE_RE.sub("", t)

    t = re.sub(

        r"(?:^|\n)\s*📄\s*Source\s*\n[\s\S]*$",

        "",

        t,

        flags=re.I,

    ).strip()

    return t





def extract_source_meta(

    chunks: Optional[List[Dict]] = None,

    section_hint: str = "",

    text: str = "",

    queried_section: str = "",

) -> Dict[str, str]:

    """Build structured source metadata for UI footer."""

    filename = ""

    section = (queried_section or "").upper()

    if not section and section_hint:

        m = re.search(r"Section\s+(\d{1,4}[a-z]?)", section_hint, re.I)

        if m:

            section = m.group(1).upper()

    if not section and text:

        m = re.search(
            rf"(?:IPC|BNS)\s+Section\s+(\d{{1,4}}[a-z]?)\s*[—–\-]",
            text[:300],
            re.I,
        )

        if m:

            section = m.group(1).upper()

    if chunks:

        meta = (chunks[0].get("metadata") or {})

        filename = str(meta.get("filename") or meta.get("source") or "").strip()

    if not filename and text:

        m = re.search(r"Source:\s*([^\n·]+)", text, re.I)

        if m:

            filename = m.group(1).strip()

    return {"filename": filename, "section": section}





def clean_chunk_text(text: str) -> str:

    """Clean raw retrieved chunk text before synthesis."""

    if not text:

        return ""

    t = re.sub(r"#{4,}", "", text)

    t = re.sub(r"\[\s*Page\s*\d+\s*\]", " ", t, flags=re.I)

    t = _PAGE_NOISE_RE.sub(" ", t)

    t = re.sub(

        r"Page\s*\d+\s*—\s*.*?(?=Section|$)",

        " ",

        t,

        flags=re.I,

    )

    t = re.sub(r"\bPage\s+\d+\s*[—–-]\s*[A-Za-z ]+\s*", " ", t, flags=re.I)

    t = re.sub(r"\bTopic\s*/?\s*Usage\b", "", t, flags=re.I)

    t = re.sub(r"\s+", " ", t).strip()

    return t





def clean_kb_response(text: str, *, preserve_markdown: bool = True) -> str:

    """Strip prompt leaks and duplicate spacing; keep # headings when preserve_markdown."""

    if not text:

        return ""

    t = (text or "").strip()

    t = _NOT_FOUND_INLINE.sub("", t)

    if not preserve_markdown:

        t = re.sub(r"#{2,}", "", t)

    else:

        t = _TRIPLE_HASH_ARTIFACT_RE.sub("", t)

    t = re.sub(r"^\s*[\{\[]\s*[\}\]]\s*$", "", t)

    t = dedupe_lines(t)

    t = re.sub(r"\[\[.*?\]\]", "", t)

    lines = []

    for line in t.splitlines():

        if _PROMPT_LEAK_RE.search(line) and len(line) < 120:

            continue

        lines.append(line)

    cleaned_lines: List[str] = []
    for line in lines:
        if _TABLE_LINE_RE.match(line) or line.strip().startswith("#"):
            cleaned_lines.append(line.strip())
        else:
            cleaned_lines.append(_MULTI_SPACE_RE.sub(" ", line).strip())
    t = "\n".join(cleaned_lines)
    t = _MULTI_NEWLINE_RE.sub("\n\n", t)
    return t.strip()





def finalize_display_answer(

    text: str,

    chunks: Optional[List[Dict]] = None,

    *,

    section_hint: str = "",

    section: str = "",

    law: str = "IPC",

) -> Tuple[str, Dict[str, str]]:

    """

    Pipeline: clean → dedupe → strip inline source → return body + source meta.

    """

    t = clean_kb_response(text, preserve_markdown=True)

    subtitle = ""
    if section:
        try:
            from answer_orchestrator import SECTION_SUBTITLES

            subtitle = SECTION_SUBTITLES.get(section.upper(), "")
        except Exception:
            pass
        t = strip_section_leadin(t, section, law=law, subtitle=subtitle)
        t = collapse_inline_section_duplicates(t, section, law=law, subtitle=subtitle)
        t = strip_redundant_section_titles(t, section, law=law)

    if "|" in t and "---" in t:
        t = _normalize_markdown_tables(t)
    else:
        t = deduplicate_response(t)

    queried_section = section.upper() if section else ""
    if section_hint and not queried_section:
        m = re.search(r"Section\s+(\d{1,4}[a-z]?)", section_hint, re.I)
        if m:
            queried_section = m.group(1).upper()
    source_meta = extract_source_meta(
        chunks,
        section_hint=section_hint,
        text=t,
        queried_section=queried_section,
    )

    t = strip_embedded_source(t)

    t = dedupe_lines(t)

    return t.strip(), source_meta





def is_empty_payload(text: str) -> bool:

    normalized = (text or "").strip().lower()

    if not normalized:

        return True

    if normalized in {"{}", "{ }", "[]", "[ ]", "null", "none", '""', "''"}:

        return True

    if len(re.findall(r"[A-Za-z0-9]", normalized)) < 8:

        return True

    return False


