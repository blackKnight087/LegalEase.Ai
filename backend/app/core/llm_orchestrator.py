"""
Multi-model LLM orchestration — generate, classify, and legal-reason per task.

Never routes embeddings through an LLM; retrieval uses EmbeddingManager only.
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional

import os

from backend.app.core.llm_task_router import (
    INTAKE_LEGAL_TIMEOUT_SEC,
    LEGAL_TIMEOUT_SEC,
    OLLAMA_MODEL_LEGAL,
    OLLAMA_MODEL_LEGAL_FALLBACK,
    ModelRole,
    TaskType,
    generation_limits_for_task,
    model_name_for_role,
    primary_ollama_model,
    route_task,
    router_enabled,
    skip_fast_classifier_llm,
)

logger = logging.getLogger("legalease.llm_orchestrator")

LEGAL_SAFETY_SYSTEM = """You are LegalEase AI — an Indian legal research assistant.

Rules:
- Base criminal/civil answers on IPC, BNS, BNSS, CrPC, and Constitution only when confident.
- NEVER invent section numbers. If unsure, say: "Possible applicable sections may include…" and list only well-known candidates.
- Prefer retrieve → verify → reason → answer. Do not fabricate citations or case names.
- If context documents are provided, use ONLY those for factual claims about the user's matter.
- This is legal information, not legal advice."""

_CLASSIFY_SYSTEM = """You classify Indian legal intake queries. Reply with ONLY valid JSON, no markdown.
Schema:
{
  "category": "Family Law|Criminal|Commercial|Property|Employment|Constitutional|General",
  "subtype": "short label e.g. Maintenance, Cheating, Eviction",
  "urgency": "LOW|MEDIUM|HIGH",
  "intent": "SNAKE_CASE intent e.g. FAMILY_LAW, CRIMINAL_DEFENSE",
  "entities": {"amount": "", "venue": "", "parties": []}
}"""


def get_generator_for_task(
    task: TaskType | str,
    *,
    user_id: str = "",
    allow_fallback: bool = True,
):
    """Return an Ollama/LM Studio client for the task's model role."""
    from llms import get_generator

    if not router_enabled():
        return get_generator(user_id=user_id)

    role = route_task(task)
    if role == ModelRole.EMBEDDING:
        raise ValueError("Embeddings must use EmbeddingManager, not an LLM")

    model = model_name_for_role(role)
    primary = primary_ollama_model()
    # Same model as legacy KB path → use get_generator() so OLLAMA_KB_LOCK_MODEL + per-user tuned apply.
    if (model or "").lower() == primary.lower():
        client = get_generator(user_id=user_id)
    else:
        client = get_generator(model=model, user_id=user_id)

    if (
        allow_fallback
        and role == ModelRole.LEGAL_REASONING
        and OLLAMA_MODEL_LEGAL_FALLBACK
        and OLLAMA_MODEL_LEGAL_FALLBACK.lower() != (model or "").lower()
    ):
        if not getattr(client, "available", True):
            fb_name = OLLAMA_MODEL_LEGAL_FALLBACK
            if fb_name.lower() == primary.lower():
                fb = get_generator(user_id=user_id)
            else:
                fb = get_generator(model=fb_name, user_id=user_id)
            if getattr(fb, "available", True):
                return fb
    return client


def generate_for_task(
    task: TaskType | str,
    prompt: str,
    *,
    system_prompt: str = "",
    user_id: str = "",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Run generation for a routed task. Never raises — returns error in ``text`` on failure.
    """
    limits = generation_limits_for_task(task)
    temp = temperature if temperature is not None else limits["temperature"]
    mtok = max_tokens if max_tokens is not None else limits["max_tokens"]
    timeout = timeout_sec if timeout_sec is not None else limits.get("timeout_sec", LEGAL_TIMEOUT_SEC)

    role = route_task(task)
    model_used = model_name_for_role(role) if router_enabled() else ""

    sys = system_prompt.strip()
    if task in (TaskType.LEGAL_REASONING, TaskType.DRAFT_POLISH) and LEGAL_SAFETY_SYSTEM not in sys:
        sys = f"{LEGAL_SAFETY_SYSTEM}\n\n{sys}".strip() if sys else LEGAL_SAFETY_SYSTEM

    try:
        client = get_generator_for_task(task, user_id=user_id)
        model_used = getattr(client, "model", model_used) or model_used

        def _run() -> str:
            return (
                client.generate(
                    prompt,
                    temperature=temp,
                    max_tokens=mtok,
                    system_prompt=sys,
                )
                or ""
            ).strip()

        with ThreadPoolExecutor(max_workers=1) as pool:
            text = pool.submit(_run).result(timeout=timeout)
        return {
            "ok": True,
            "text": text,
            "model": model_used,
            "task": str(task),
            "role": role.value,
        }
    except FuturesTimeout:
        logger.warning("LLM timeout task=%s model=%s", task, model_used)
        return {
            "ok": False,
            "text": "",
            "error": "timeout",
            "model": model_used,
            "task": str(task),
            "role": role.value,
        }
    except Exception as exc:
        logger.warning("LLM error task=%s: %s", task, exc)
        return {
            "ok": False,
            "text": "",
            "error": str(exc)[:200],
            "model": model_used,
            "task": str(task),
            "role": role.value,
        }


def _parse_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def classify_fast(text: str, *, user_id: str = "") -> Dict[str, Any]:
    """
    Fast case-type / urgency / intent classification.
    Skipped when fast model is the same as legalease-tuned (avoids duplicate LLM calls).
    Optional separate model only when OLLAMA_MODEL_FAST differs from OLLAMA_MODEL_LEGAL.
    """
    q = (text or "").strip()
    if not q:
        return {}
    if skip_fast_classifier_llm():
        return {"source": "skipped_same_model", "model": primary_ollama_model()}

    prompt = f"Classify this client intake (Indian law):\n\n{q[:2000]}"
    result = generate_for_task(
        TaskType.CLASSIFICATION,
        prompt,
        system_prompt=_CLASSIFY_SYSTEM,
        user_id=user_id,
        max_tokens=280,
    )
    if not result.get("ok") or not result.get("text"):
        return {"source": "llm_failed", "error": result.get("error")}

    parsed = _parse_json_object(result["text"])
    if not parsed:
        return {"source": "llm_parse_failed", "raw": result["text"][:400]}

    out = {
        "category": str(parsed.get("category") or "").strip(),
        "subtype": str(parsed.get("subtype") or "").strip(),
        "urgency": str(parsed.get("urgency") or "MEDIUM").upper(),
        "intent": str(parsed.get("intent") or "").strip().upper(),
        "entities": parsed.get("entities") if isinstance(parsed.get("entities"), dict) else {},
        "source": "llm_fast",
        "model": result.get("model"),
    }
    if out["urgency"] not in {"LOW", "MEDIUM", "HIGH"}:
        out["urgency"] = "MEDIUM"
    return out


def legal_reason(
    prompt: str,
    *,
    system_prompt: str = "",
    user_id: str = "",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """Primary legal reasoning entry (Qwen 8B class model with fallback)."""
    result = generate_for_task(
        TaskType.LEGAL_REASONING,
        prompt,
        system_prompt=system_prompt,
        user_id=user_id,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return result.get("text") or ""


def _rule_based_intake_markdown(query: str, classification: Dict[str, Any]) -> str:
    """Instant CRM analysis when Ollama is busy or times out."""
    intent = classification.get("intent") or "GENERAL_CONSULTATION"
    case_type = classification.get("case_type") or intent.replace("_", " ").title()
    urgency = classification.get("urgency") or "MEDIUM"
    sections = classification.get("likely_sections") or []
    params = classification.get("parameters") or {}
    sec_line = (
        ", ".join(sections)
        if sections
        else "Possible applicable sections may include IPC/BNS provisions for cheating, breach of trust, or breach of contract — verify with counsel."
    )
    amt = params.get("amount_in_dispute") or ""
    venue = params.get("venue") or params.get("jurisdiction") or ""
    return (
        f"## Case Type\n{case_type} ({intent.replace('_', ' ').title()})\n\n"
        f"## Urgency\n{urgency}\n\n"
        f"## Possible Sections\n{sec_line}\n\n"
        f"## Strength\nMedium — based on intake rules; confirm with documents.\n\n"
        f"## Documents Needed\n"
        f"Agreement/PO, payment proof{f' ({amt})' if amt else ''}, email/chat with vendor, company registration.\n\n"
        f"## Recommended Action\n"
        f"Send legal notice; preserve evidence; evaluate FIR/complaint vs civil recovery"
        f"{f' in {venue}' if venue else ''}.\n\n"
        f"*Summary:* {(query or '')[:200]}"
    )


def generate_intake_legal_analysis(
    query: str,
    classification: Dict[str, Any],
    *,
    user_id: str = "",
    kb_snippets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Structured intake analysis after classification.
    Uses a shorter timeout than KB chat so CRM endpoints stay responsive.
    """
    if os.getenv("LLM_INTAKE_LEGAL_ANALYSIS", "0").lower() not in {"1", "true", "yes"}:
        return {
            "ok": True,
            "markdown": _rule_based_intake_markdown(query, classification),
            "model_role": "rules",
        }

    ctx = ""
    if kb_snippets:
        ctx = "\n\nRetrieved references:\n" + "\n---\n".join(s[:600] for s in kb_snippets[:4])

    sys = (
        f"{LEGAL_SAFETY_SYSTEM}\n\n"
        "Produce a concise intake analysis for an Indian law firm CRM.\n"
        "Use markdown sections: Case Type, Possible Sections, Strength, Documents Needed, Recommended Action.\n"
        "For sections use cautious language if not verified from references."
    )
    user = (
        f"Client query:\n{query}\n\n"
        f"Classification: {json.dumps(classification, ensure_ascii=False)}\n"
        f"{ctx}\n\n"
        "Intake analysis:"
    )
    result = generate_for_task(
        TaskType.LEGAL_REASONING,
        user,
        system_prompt=sys,
        user_id=user_id,
        max_tokens=550,
        temperature=0.1,
        timeout_sec=INTAKE_LEGAL_TIMEOUT_SEC,
    )
    text = (result.get("text") or "").strip()
    if text and result.get("ok"):
        return {"ok": True, "markdown": text, "model_role": ModelRole.LEGAL_REASONING.value}
    fallback = _rule_based_intake_markdown(query, classification)
    return {
        "ok": True,
        "markdown": fallback,
        "model_role": "rules_fallback",
        "llm_error": result.get("error"),
    }


def merge_classification(
    rules: Dict[str, Any],
    llm: Dict[str, Any],
) -> Dict[str, Any]:
    """Prefer learned rules; enrich with LLM when rules are weak."""
    out = dict(rules or {})
    if not llm or llm.get("source") in ("llm_failed", "llm_parse_failed"):
        return out

    conf = float(out.get("confidence") or 0)
    if llm.get("intent") and (conf < 0.75 or out.get("source") == "fallback"):
        out["intent"] = llm["intent"]
        out["confidence"] = max(conf, 0.72)
        out["source"] = "llm_enriched"

    if llm.get("category"):
        out["case_type"] = llm["category"]
    if llm.get("subtype"):
        out["subtype"] = llm["subtype"]
    if llm.get("urgency"):
        out["urgency"] = llm["urgency"]

    params = dict(out.get("parameters") or {})
    ents = llm.get("entities") or {}
    if isinstance(ents, dict):
        for k in ("amount", "venue", "parties"):
            if ents.get(k) and not params.get(k):
                params[k] = ents[k]
    out["parameters"] = params
    return out
