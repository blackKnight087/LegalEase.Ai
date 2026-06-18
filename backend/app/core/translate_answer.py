"""Translate synthesized legal answers — never raw search snippets."""
from __future__ import annotations

from typing import Optional

_LANG_CODES = {
    "Hindi": "hi",
    "Tamil": "ta",
    "Marathi": "mr",
    "Bengali": "bn",
    "Gujarati": "gu",
}


def translate_after_synthesis(text: str, lang: Optional[str] = "English") -> str:
    body = (text or "").strip()
    if not body or (lang or "English") == "English":
        return body
    target = _LANG_CODES.get(lang or "", "")
    if not target:
        return body
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target=target).translate(body)
    except Exception:
        return body
