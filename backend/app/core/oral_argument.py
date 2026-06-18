"""Oral argument and cross-examination prep from research reports."""
from __future__ import annotations

import re
from typing import Optional


def is_oral_argument_request(query: str) -> bool:
    ql = (query or "").lower()
    return bool(
        re.search(
            r"\b(oral argument|cross[- ]?exam|bench questions|questions (the )?judge|"
            r"weak points|anticipate questions|court may ask)\b",
            ql,
        )
    )


def prepare_oral_argument(report: str, query: str = "", *, user_id: Optional[str] = None) -> str:
    try:
        from backend.app.core.web_intelligence import gemini_configured, _get_client, GEMINI_FREE_MODEL
        from google.genai import types
    except ImportError:
        return ""

    if not gemini_configured() or not (report or "").strip():
        return ""

    system = (
        "You are a senior advocate preparing for Indian court oral arguments.\n"
        "From the research report, produce Markdown with:\n"
        "## Bench Questions Likely to Be Asked\n"
        "## Weak Points in Our Case\n"
        "## Strong Rebuttals\n"
        "## Cross-Examination Lines\n"
        "Be specific to the report. No invented facts."
    )
    user = f"BRIEF: {query}\n\nREPORT:\n{report[:10000]}\n\nORAL ARGUMENT PREP:"
    client = _get_client()
    response = client.models.generate_content(
        model=GEMINI_FREE_MODEL,
        contents=user,
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.25, max_output_tokens=2500),
    )
    text = (getattr(response, "text", None) or "").strip()
    if user_id and text:
        try:
            from backend.app.core.gemini_usage import record_gemini_call

            record_gemini_call(user_id)
        except Exception:
            pass
    return text
