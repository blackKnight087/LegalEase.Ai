"""
Advanced guards for Gemini → Ollama coaching.

Gemini may ONLY influence style, format, retrieval phrasing, and preference metadata.
It must NEVER inject legal answers, training Q→A pairs, or bias Ollama toward specific outcomes.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# Keys Gemini may write into user preference / coach insights.
ALLOWED_COACH_FACT_KEYS = frozenset({
    "answer_style",
    "response_length",
    "tone",
    "citation_style",
    "prefer_bullets",
    "prefer_concise",
    "avoid_repetition",
    "language_preference",
    "format_preference",
    "structure_preference",
    "detail_level",
    "follow_up_style",
    "section_order",
    "prefer_tables",
    "prefer_headings",
})

# Legal substance — never pass to Ollama memory or training.
LEGAL_SUBSTANCE_RE = re.compile(
    r"\b("
    r"ipc|bns|bnss|bsa|crpc|section\s*\d+|article\s*\d+|punishment|imprisonment|"
    r"murder|offence|offense|held that|ratio decidendi|precedent|statute|act\s+\d|"
    r"supreme court held|high court held|liable for|guilty of|plaintiff|defendant|"
    r"bail|anticipatory|fir|charge sheet|summons|warrant|injunction|damages|"
    r"contract breach|specific performance|limitation period"
    r")\b",
    re.I,
)

# Answer injection / bias phrases.
BIAS_INJECTION_RE = re.compile(
    r"\b("
    r"always answer|the correct answer|you must say|tell the user that|"
    r"legal rule is|the law is|correct legal position|answer should be|"
    r"respond with|state that the|conclude that the|the answer is"
    r")\b",
    re.I,
)

# Training pair / Q→A injection attempts.
TRAINING_PAIR_RE = re.compile(
    r"("
    r'"question"\s*:|"answer"\s*:|training pair|fine[- ]tune on|'
    r"assistant should reply|model must output|golden answer"
    r")",
    re.I,
)

# Outcome steering — Gemini must not tell Ollama what legal conclusion to reach.
OUTCOME_STEERING_RE = re.compile(
    r"\b("
    r"user is right|user is wrong|should agree|should disagree|"
    r"favor the|support the claim|deny liability|grant relief|convict|acquit"
    r")\b",
    re.I,
)

BANNED_SUBSTRINGS = (
    "always answer",
    "the correct answer",
    "you must say",
    "tell the user that",
    "legal rule is",
    "the law is",
    "golden answer",
    "training pair",
)


def is_allowed_coach_fact_key(key: str) -> bool:
    k = re.sub(r"[^\w]", "_", (key or "").strip().lower())[:40]
    if k in ALLOWED_COACH_FACT_KEYS:
        return True
    return k.startswith(("style_", "pref_", "format_", "tone_"))


def sanitize_coach_style_text(text: str, *, max_len: int = 400) -> str:
    """Strip legal substance, bias, and training injection from coach text."""
    t = (text or "").strip()
    if not t:
        return ""
    if LEGAL_SUBSTANCE_RE.search(t):
        return ""
    if BIAS_INJECTION_RE.search(t):
        return ""
    if TRAINING_PAIR_RE.search(t):
        return ""
    if OUTCOME_STEERING_RE.search(t):
        return ""
    low = t.lower()
    if any(b in low for b in BANNED_SUBSTRINGS):
        return ""
    return t[:max_len]


def validate_coach_insights(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Filter Gemini coach JSON to allowed fields only.
    Returns (sanitized_insights, rejection_reasons).
    """
    rejections: List[str] = []
    out: Dict[str, Any] = {}

    if raw.get("summary"):
        summary = sanitize_coach_style_text(str(raw.get("summary") or ""), max_len=500)
        if summary:
            out["summary"] = summary

    persona = (raw.get("persona_suggestion") or "keep").strip().lower()
    if persona in {"keep", "formal", "concise", "detailed", "plain", "advocate"}:
        out["persona_suggestion"] = persona
    else:
        out["persona_suggestion"] = "keep"
        if persona != "keep":
            rejections.append(f"persona_blocked:{persona[:20]}")

    notes = sanitize_coach_style_text(raw.get("communication_notes_addition") or "", max_len=300)
    if notes:
        out["communication_notes_addition"] = notes
    elif raw.get("communication_notes_addition"):
        rejections.append("communication_notes_blocked")

    facts: List[Dict[str, str]] = []
    for fact in (raw.get("suggested_facts") or [])[:4]:
        if not isinstance(fact, dict):
            continue
        key = re.sub(r"[^\w]", "_", (fact.get("key") or "").strip().lower())[:40]
        val = sanitize_coach_style_text((fact.get("value") or "").strip(), max_len=200)
        if key and val and is_allowed_coach_fact_key(key):
            facts.append({"key": key, "value": val})
        elif fact.get("key"):
            rejections.append(f"fact_blocked:{key[:20]}")
    out["suggested_facts"] = facts

    healings: List[Dict[str, str]] = []
    for heal in (raw.get("query_healings") or [])[:3]:
        if not isinstance(heal, dict):
            continue
        mode = (heal.get("mode") or "knowledge_base").strip()[:40]
        qn = (heal.get("query_norm") or heal.get("query") or "").strip()[:200]
        exp_raw = (heal.get("expansion") or "").strip()
        try:
            from backend.app.core.kb_gemini_safety import validate_retrieval_hints

            validated = validate_retrieval_hints([exp_raw], original_query=qn)
            exp = validated[0] if validated else ""
        except Exception:
            exp = sanitize_coach_style_text(exp_raw, max_len=200)
            if exp and LEGAL_SUBSTANCE_RE.search(exp) and not re.search(r"\b\d{1,4}\b", exp):
                exp = ""
        if qn and exp:
            healings.append({"mode": mode, "query_norm": qn, "expansion": exp})
        elif heal.get("expansion"):
            rejections.append("query_healing_blocked")
    out["query_healings"] = healings

    pref = raw.get("preference_updates") or {}
    if isinstance(pref, dict):
        clean_pref: Dict[str, Any] = {}
        for k, v in pref.items():
            if not is_allowed_coach_fact_key(str(k)):
                rejections.append(f"pref_key_blocked:{str(k)[:20]}")
                continue
            if isinstance(v, (int, float)):
                clean_pref[str(k)] = max(0.0, min(1.0, float(v)))
            elif isinstance(v, str):
                sv = sanitize_coach_style_text(v, max_len=120)
                if sv:
                    clean_pref[str(k)] = sv
        out["preference_updates"] = clean_pref

    # Explicitly strip forbidden keys if Gemini hallucinates them.
    for forbidden in (
        "training_pairs",
        "suggested_answers",
        "legal_rules",
        "answer_templates",
        "modelfile_system",
        "bias_directives",
    ):
        if forbidden in raw:
            rejections.append(f"forbidden_key:{forbidden}")

    return out, rejections


def parse_coach_json(text: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Parse and validate Gemini JSON coach output."""
    if not text:
        return None, ["empty_response"]
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None, ["json_parse_failed"]
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None, ["json_parse_failed"]
    if not isinstance(data, dict):
        return None, ["not_object"]
    return validate_coach_insights(data)


def guard_rlaif_style_score(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    RLAIF-style reward: style/format scores only (0–1).
    Reject if any dimension tries to score legal correctness.
    """
    if not isinstance(raw, dict):
        return None
    allowed_dims = frozenset({
        "clarity",
        "structure",
        "conciseness",
        "citation_format",
        "tone_match",
        "follow_up_quality",
    })
    scores: Dict[str, float] = {}
    for k, v in raw.items():
        if k not in allowed_dims:
            continue
        try:
            scores[k] = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            continue
    if not scores:
        return None
    overall = sum(scores.values()) / len(scores)
    return {"dimensions": scores, "overall": round(overall, 4)}
