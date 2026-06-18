"""
Response Mode Controller — adaptive answer shape by query complexity.

Decides HOW to answer (length, structure, tokens) before LLM synthesis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from intent_engine import IntentProfile, QueryIntent, classify_intent

ANTI_REPETITION_RULES = (
    "Never repeat headings or section titles.\n"
    "Never restate identical legal points in different words.\n"
    "Avoid duplicate explanations — say each fact once.\n"
    "Do not echo the question back as the opening sentence."
)

_DRAFT_RE = re.compile(
    r"\b(draft|prepare|write|create|generate)\b.*\b("
    r"fir|legal notice|notice|affidavit|petition|plaint|"
    r"complaint|chargesheet|charge sheet|contract|agreement|"
    r"memorandum|rejoinder|written statement|bail application)\b",
    re.I,
)
_QUICK_RE = re.compile(
    r"^(?:what is|what's|what replaced|which law replaced|define|"
    r"who is|when did|name of)\b",
    re.I,
)
_DEEP_RE = re.compile(
    r"\b(explain|differences?|difference between|implications?|"
    r"analysis|compare|versus|vs\.?|in detail|comprehensive|"
    r"walk me through|break down)\b",
    re.I,
)
_CASE_RE = re.compile(
    r"\b(case|judgment|judgement|verdict|ruling|petition)\b|"
    r"\b(vishaka|kesavananda|maneka gandhi|nirbhaya|puttaswamy|"
    r"navtej|shayara|indira gandhi|basic structure)\b|"
    r"\bguidelines?\b",
    re.I,
)
_COMPARE_RE = re.compile(
    r"\b(compare|comparison|difference|differences|versus|vs\.?|between)\b",
    re.I,
)


@dataclass
class ResponseModeSpec:
    mode: str = "quick_answer"
    complexity: str = "short"
    target_words: str = "50-120"
    max_tokens: int = 350
    temperature: float = 0.10
    frequency_penalty: float = 0.35
    presence_penalty: float = 0.20
    use_table: bool = False
    headings: List[str] = field(default_factory=list)
    structure_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "complexity": self.complexity,
            "target_words": self.target_words,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "use_table": self.use_table,
            "headings": self.headings,
            "structure_hint": self.structure_hint,
        }


def detect_response_mode(
    question: str,
    profile: Optional[IntentProfile] = None,
    messages: Optional[List[Dict]] = None,
) -> ResponseModeSpec:
    """
    Route query to response mode.

    Modes: quick_answer | detailed_analysis | case_explanation | comparison | legal_drafting
    """
    q = (question or "").strip()
    ql = q.lower()
    words = len(q.split())
    profile = profile or classify_intent(q, messages)

    if _DRAFT_RE.search(q):
        return ResponseModeSpec(
            mode="legal_drafting",
            complexity="deep",
            target_words="400-1200",
            max_tokens=2200,
            temperature=0.25,
            frequency_penalty=0.25,
            presence_penalty=0.15,
            headings=["Document Title", "Parties", "Facts", "Legal Grounds", "Prayer / Relief"],
            structure_hint="Professional Indian legal drafting format with formal headings.",
        )

    if _CASE_RE.search(q) or profile.primary == QueryIntent.GENERAL_ANALYSIS and "case" in ql:
        return ResponseModeSpec(
            mode="case_explanation",
            complexity="deep",
            target_words="300-700",
            max_tokens=1400,
            temperature=0.15,
            frequency_penalty=0.40,
            presence_penalty=0.25,
            headings=[
                "Overview",
                "Facts",
                "Issues",
                "Judgement",
                "Significance",
                "Present Legal Position",
            ],
            structure_hint=(
                "Include a **Citation Block** with: Source, Court, Bench, Year, Citation, "
                "Legal Principle — only from context/sources."
            ),
        )

    from kb_retrieval import is_comparison_query

    sections = profile.signals.get("sections") or []
    if (
        profile.primary == QueryIntent.COMPARISON
        or _COMPARE_RE.search(q)
        or (is_comparison_query(q) and len(sections) >= 2)
    ):
        deep = words > 12 or "implication" in ql or "provision" in ql
        return ResponseModeSpec(
            mode="comparison",
            complexity="deep" if deep else "medium",
            target_words="300-800" if deep else "150-400",
            max_tokens=1600 if deep else 900,
            temperature=0.12,
            frequency_penalty=0.35,
            presence_penalty=0.20,
            use_table=True,
            headings=["Overview", "Side-by-Side Comparison", "Key Difference", "Practical Implication"],
            structure_hint="Use a Markdown comparison table when comparing two statutes/sections.",
        )

    if _DEEP_RE.search(q) and words > 10:
        return ResponseModeSpec(
            mode="detailed_analysis",
            complexity="deep",
            target_words="300-800",
            max_tokens=1600,
            temperature=0.14,
            frequency_penalty=0.35,
            presence_penalty=0.22,
            headings=["Overview", "Explanation", "Key Sections", "Implications", "Example"],
            structure_hint="Structured legal analysis with examples and section references from context.",
        )

    if _QUICK_RE.match(q) or words <= 9:
        return ResponseModeSpec(
            mode="quick_answer",
            complexity="short",
            target_words="50-120",
            max_tokens=280,
            temperature=0.08,
            frequency_penalty=0.45,
            presence_penalty=0.30,
            structure_hint="Direct answer in 2-4 sentences. No headings unless user asked for structure.",
        )

    if profile.primary in (QueryIntent.SUMMARIZATION, QueryIntent.LIST_EXTRACTION):
        return ResponseModeSpec(
            mode="detailed_analysis",
            complexity="medium",
            target_words="150-400",
            max_tokens=900,
            temperature=0.12,
            frequency_penalty=0.35,
            presence_penalty=0.20,
            headings=["Overview", "Key Points"],
            structure_hint="Concise bullets or short paragraphs.",
        )

    return ResponseModeSpec(
        mode="quick_answer" if words <= 12 else "detailed_analysis",
        complexity="short" if words <= 12 else "medium",
        target_words="50-120" if words <= 12 else "150-350",
        max_tokens=350 if words <= 12 else 800,
        temperature=0.10,
        frequency_penalty=0.38,
        presence_penalty=0.22,
    )


def apply_mode_to_profile(profile: IntentProfile, mode: ResponseModeSpec) -> IntentProfile:
    """Merge response mode into intent profile for downstream synthesis."""
    profile.complexity = mode.complexity
    profile.max_answer_tokens = mode.max_tokens
    profile.response_mode = mode.mode
    profile.signals["response_mode"] = mode.to_dict()
    if mode.mode == "comparison" and mode.use_table:
        profile.response_mode = "table"
    elif mode.mode == "case_explanation":
        profile.response_mode = "structured"
    elif mode.mode == "quick_answer":
        profile.response_mode = "minimal"
    elif mode.mode == "legal_drafting":
        profile.response_mode = "structured"
    return profile


def mode_instructions(mode: ResponseModeSpec) -> str:
    """Prompt block for the active response mode."""
    lines = [
        f"RESPONSE MODE: {mode.mode.replace('_', ' ').title()}",
        f"TARGET LENGTH: {mode.target_words} words.",
        ANTI_REPETITION_RULES,
    ]
    if mode.mode == "quick_answer":
        lines.append(
            "Answer in 2-4 crisp sentences. No boilerplate headings. "
            "Example: 'IPC has been replaced by Bharatiya Nyaya Sanhita (BNS), 2023.'"
        )
    elif mode.mode == "detailed_analysis":
        lines.append(
            "Provide explanation, relevant sections, implications, and a brief example "
            "ONLY if supported by context."
        )
        if mode.headings:
            lines.append("Use these ### subsections where helpful: " + ", ".join(mode.headings))
    elif mode.mode == "case_explanation":
        lines.append(mode.structure_hint)
        lines.append(
            "Required ### sections: "
            + ", ".join(mode.headings)
        )
        lines.append(
            "Citation Block format (fill only from context):\n"
            "- **Source:** ...\n- **Court:** ...\n- **Bench:** ...\n"
            "- **Year:** ...\n- **Citation:** ...\n- **Legal Principle:** ..."
        )
    elif mode.mode == "comparison":
        if mode.use_table:
            lines.append(
                "Use a Markdown table: | Aspect | First | Second | then Key Difference paragraph."
            )
        else:
            lines.append("Side-by-side prose comparison with a clear conclusion.")
    elif mode.mode == "legal_drafting":
        lines.append(mode.structure_hint)
        lines.append("Use formal legal language and proper Indian court format.")
    if mode.structure_hint and mode.mode not in ("case_explanation", "legal_drafting"):
        lines.append(mode.structure_hint)
    return "\n".join(lines)
