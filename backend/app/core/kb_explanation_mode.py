"""
KB EXPLANATION MODE — synthesize teaching-style answers; never dump retrieved lists.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_EXPLANATION_CUES = re.compile(
    r"\b(?:"
    r"explain(?:\s+it)?(?:\s+properly|\s+in\s+detail|\s+simply|\s+clearly)?|"
    r"explain\s+properly|explain\s+in\s+detail|explain\s+simply|"
    r"what\s+does\s+(?:this|it)\s+mean|what\s+is\s+the\s+meaning|"
    r"teach\s+me|walk\s+me\s+through|break\s+down|"
    r"in\s+simple\s+language|simple\s+language|layman|"
    r"overview|summarize|summarise|elaborate|in\s+depth"
    r")\b",
    re.I,
)

_DEEP_EXPLANATION_CUES = re.compile(
    r"\b(?:properly|in\s+detail|detailed|comprehensive|full|thorough|"
    r"teach\s+me|walk\s+me\s+through|elaborate|in\s+depth|overview)\b",
    re.I,
)

_LIST_DUMP_RE = re.compile(
    r"^(?:\d+\.\s*)?(?:Right\s+to|Right\s+against|Article\s+\d+)",
    re.I,
)

KB_EXPLANATION_MODE_PROMPT = """
EXPLANATION MODE — STRICT GROUNDING (mandatory):
- Expand, reorganize, paraphrase, or summarize ONLY what appears in DOCUMENT CONTEXT.
- If the excerpts are short, write a shorter answer. NEVER pad with outside law or virtue lists.
- Do NOT invent clauses, articles, cases, punishments, or examples absent from the excerpts.
- For any sub-question not covered by excerpts, write exactly:
  "The uploaded document does not contain sufficient information to answer this part of the question."

Required structure (use these exact ### headings):
### Definition
### Detailed Explanation
### Key Components
### Examples
### Practical Importance
### Conclusion

Under ### Key Components: one bullet per right/section named in the excerpts only.
Under ### Examples: only scenarios explicitly supported by the excerpts.
Do not include a Source line in the body.
"""

_VIRTUE_PADDING_WORDS = frozenset(
    {
        "justice", "fairness", "accountability", "transparency", "trustworthiness",
        "reliability", "dependability", "stability", "resilience", "strength",
        "courage", "perseverance", "determination", "fortitude", "patience",
        "kindness", "compassion", "empathy", "understanding", "tolerance",
        "forgiveness", "generosity", "humility", "modesty", "simplicity",
        "contentment", "gratitude", "hope", "faith", "love", "peace", "joy",
    }
)


def explanation_mode_active(query: str) -> bool:
    q = (query or "").strip()
    if not q:
        return False
    if _EXPLANATION_CUES.search(q):
        return True
    try:
        from conversation_context import is_meta_follow_up

        if is_meta_follow_up(q):
            return True
    except ImportError:
        pass
    return False


def explanation_mode_deep(query: str) -> bool:
    return bool(_DEEP_EXPLANATION_CUES.search(query or ""))


def explanation_mode_instruction(query: str, *, topic_hint: str = "") -> str:
    topic = topic_hint or query.strip()
    return (
        f"Topic: {topic[:120]}. EXPLANATION MODE: paraphrase DOCUMENT CONTEXT only. "
        "If excerpts are brief, keep the answer concise. No outside law or virtue padding."
    )


def _context_text(chunks: List[Dict]) -> str:
    return "\n".join((c.get("content") or "") for c in (chunks or [])[:10])


def strip_virtue_padding(text: str) -> str:
    """Remove repetitive abstract-noun spam (common when models pad word count)."""
    if not text:
        return ""
    out_lines: List[str] = []
    for line in text.splitlines():
        words = re.findall(r"[a-zA-Z]+", line.lower())
        if len(words) >= 12:
            pad = sum(1 for w in words if w in _VIRTUE_PADDING_WORDS)
            if pad >= max(8, int(len(words) * 0.45)):
                continue
        cleaned = re.sub(
            r"(?:\b(?:justice|fairness|accountability|transparency|trustworthiness|"
            r"reliability|dependability|stability|resilience|fortitude|compassion|"
            r"empathy|tolerance|forgiveness|generosity|humility|modesty|simplicity|"
            r"contentment|gratitude|hope|faith|love|peace|joy)\b\s*){6,}.*$",
            "",
            line,
            flags=re.I,
        ).strip()
        if cleaned:
            out_lines.append(cleaned)
    return "\n".join(out_lines).strip()


def _articles_in_text(text: str) -> set:
    return {m.group(1) for m in re.finditer(r"\barticle\s+(\d{1,3})\b", text or "", re.I)}


def sanitize_explanation_answer(answer: str, chunks: List[Dict]) -> str:
    """Post-process Ollama output: drop padding spam; prefer excerpt-only fallback if ungrounded."""
    body = strip_virtue_padding((answer or "").strip())
    if not body:
        return ""
    try:
        from backend.app.core.kb_claim_audit import (
            answer_has_legal_definition_leak,
            audit_and_prune_answer,
        )

        if answer_has_legal_definition_leak(body, chunks):
            return audit_and_prune_answer(body, chunks) or ""
        body = audit_and_prune_answer(body, chunks)
    except ImportError:
        pass
    ctx = _context_text(chunks)
    if not ctx.strip():
        return body
    cited = _articles_in_text(body)
    supported = _articles_in_text(ctx)
    if cited and cited - supported:
        body = re.sub(
            r"^\s*[-*•].*?\barticle\s+(?:" + "|".join(re.escape(a) for a in cited - supported) + r")\b.*$",
            "",
            body,
            flags=re.I | re.M,
        )
    try:
        from kb_validate import verify_claims_grounded

        ok, _reason = verify_claims_grounded(body, chunks)
        if not ok:
            fb = build_explanation_from_chunks("", chunks, strict=True)
            return fb or body
    except ImportError:
        pass
    return body


def looks_like_chunk_dump(answer: str) -> bool:
    """True when the model echoed a rights/section list without explanation structure."""
    body = (answer or "").strip()
    if not body or len(body) < 80:
        return False
    if re.search(r"###\s+Definition\b", body, re.I) and re.search(
        r"###\s+Detailed\s+Explanation\b", body, re.I
    ):
        return False
    lines = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines:
        return False
    list_like = sum(1 for ln in lines if _LIST_DUMP_RE.match(ln))
    if list_like >= 3 and list_like >= max(2, int(len(lines) * 0.55)):
        return True
    if len(body) < 350 and list_like >= 2:
        return True
    return False


def apply_explanation_signals(
    signals: Dict[str, Any],
    query: str,
    *,
    query_class: str = "",
) -> Dict[str, Any]:
    out = dict(signals or {})
    out["kb_synthesis"] = True
    out["kb_explanation_mode"] = True
    out["original_query"] = query
    hint = query
    if query_class == "constitutional":
        hint = "Fundamental / constitutional rights"
    out["kb_ollama_instruction"] = explanation_mode_instruction(
        query, topic_hint=hint
    )
    out["kb_explanation_single_shot"] = True
    out["kb_no_learning_inject"] = True
    return out


_RIGHT_ARTICLE_RE = re.compile(
    r"(Right\s+to\s+[^,(]+|Right\s+against\s+[^,(]+)\s*\(Article\s+(\d+)\)",
    re.I,
)


def _explanation_topic(query: str) -> str:
    q = (query or "").strip()
    q = re.sub(
        r"\b(?:explain(?:\s+it)?(?:\s+properly|\s+in\s+detail|\s+simply)?|"
        r"teach\s+me|what\s+does\s+this\s+mean|overview|summarize|summarise)\b",
        "",
        q,
        flags=re.I,
    ).strip(" ?.,!")
    if not q:
        return "This topic"
    return q[:1].upper() + q[1:]


def build_explanation_from_chunks(
    question: str,
    chunks: List[Dict],
    *,
    strict: bool = False,
) -> str:
    """
    Structured answer built only from KB excerpts — no LLM (fast fallback).
    When strict=True, never invent examples or legal facts outside the chunks.
    """
    if not chunks:
        return ""
    try:
        from backend.app.core.kb_claim_audit import try_statute_safe_answer

        safe = try_statute_safe_answer(question, chunks)
        if safe:
            return safe
    except ImportError:
        pass
    combined = re.sub(
        r"\s+",
        " ",
        _context_text(chunks),
    ).strip()
    if not combined:
        return ""

    topic = _explanation_topic(question)
    rights = _RIGHT_ARTICLE_RE.findall(combined)
    seen: set = set()
    components: List[str] = []
    for label, art in rights:
        key = art.strip()
        if key in seen:
            continue
        seen.add(key)
        clean = label.strip().rstrip(",")
        components.append(f"- **{clean} (Article {art})** — as described in your uploaded document.")

    snippet = combined[:700].strip()
    if len(combined) > 700:
        snippet += "…"

    definition = (
        f"**{topic}** — based on your knowledge base excerpt: {snippet[:280]}"
        + ("…" if len(snippet) > 280 else "")
    )
    detailed = (
        "Your indexed document states the following (paraphrased from the source text):\n\n"
        f"{snippet}"
    )

    key_block = "### Key Components\n"
    if components:
        key_block += "\n".join(components)
    else:
        key_block += f"- See the source excerpt above for the elements named in your document."

    examples = "### Examples\n"
    if strict or rights:
        examples += (
            "- Use only scenarios explicitly mentioned in your PDF; "
            "the excerpt above lists the rights/sections available in this knowledge base."
        )
    else:
        examples += "- Refer to the document excerpt in **Detailed Explanation**."

    importance = (
        "### Practical Importance\n"
        "These provisions in your uploaded material define how the topic is framed for study "
        "and reference in your knowledge base."
    )
    conclusion = (
        "### Conclusion\n"
        f"**{topic}** in your knowledge base is summarized from the retrieved excerpt. "
        "Add or re-index a fuller constitution/statute PDF for richer detail."
    )

    return "\n\n".join(
        [
            f"## {topic}",
            f"### Definition\n{definition}",
            f"### Detailed Explanation\n{detailed}",
            key_block,
            examples,
            importance,
            conclusion,
        ]
    )
