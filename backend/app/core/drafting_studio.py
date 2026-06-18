"""Smart drafting — template wizard + optional Ollama polish (isolated from KB pipeline)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

SMART_DRAFT_SPECS: Dict[str, Dict[str, Any]] = {
    "legal_notice_salary": {
        "label": "Legal Notice — Unpaid Salary",
        "template_name": "Legal Notice",
        "practice_area": "Employment",
        "questions": [
            {"id": "employer_name", "label": "Employer name", "required": True},
            {"id": "employee_name", "label": "Employee name", "required": True},
            {"id": "amount_due", "label": "Amount due (₹)", "required": True},
            {"id": "employment_period", "label": "Employment period", "required": True},
            {"id": "venue", "label": "City / jurisdiction", "required": True},
        ],
    },
    "nda": {
        "label": "Non-Disclosure Agreement",
        "template_name": "Nda",
        "practice_area": "Corporate",
        "questions": [
            {"id": "disclosing_party", "label": "Disclosing party", "required": True},
            {"id": "receiving_party", "label": "Receiving party", "required": True},
            {"id": "purpose", "label": "Purpose of disclosure", "required": True},
            {"id": "venue", "label": "Governing city", "required": True},
        ],
    },
    "bail_application": {
        "label": "Bail Application",
        "template_name": "Bail Application",
        "practice_area": "Criminal",
        "questions": [
            {"id": "applicant_name", "label": "Applicant name", "required": True},
            {"id": "case_number", "label": "Case number", "required": True},
            {"id": "court", "label": "Court", "required": True},
            {"id": "sections", "label": "Sections invoked", "required": True},
        ],
    },
}


def list_smart_draft_types() -> List[Dict[str, Any]]:
    return [
        {
            "id": key,
            "label": spec["label"],
            "practice_area": spec.get("practice_area", "General"),
            "question_count": len(spec.get("questions") or []),
        }
        for key, spec in SMART_DRAFT_SPECS.items()
    ]


def get_smart_draft_questions(draft_type: str) -> Dict[str, Any]:
    spec = SMART_DRAFT_SPECS.get(draft_type)
    if not spec:
        return {"error": "Unknown draft type"}
    return {
        "draft_type": draft_type,
        "label": spec["label"],
        "questions": spec["questions"],
        "template_name": spec.get("template_name"),
    }


def _map_answers_to_template_vars(draft_type: str, answers: Dict[str, str]) -> Dict[str, str]:
    """Map wizard answers to template placeholders."""
    a = {k: str(v).strip() for k, v in (answers or {}).items()}
    if draft_type == "legal_notice_salary":
        return {
            "sender_name": a.get("employee_name", ""),
            "recipient_name": a.get("employer_name", ""),
            "subject": "Unpaid salary — legal notice",
            "facts": (
                f"The employee worked during {a.get('employment_period', 'the stated period')}. "
                f"Salary of {a.get('amount_due', 'the due amount')} remains unpaid."
            ),
            "demand": f"Pay {a.get('amount_due', 'all dues')} within 15 days failing which legal action may follow.",
            "date": a.get("date", "________"),
            "venue": a.get("venue", "________"),
        }
    if draft_type == "nda":
        return {
            "disclosing_party": a.get("disclosing_party", ""),
            "receiving_party": a.get("receiving_party", ""),
            "purpose": a.get("purpose", ""),
            "venue": a.get("venue", ""),
            "date": a.get("date", "________"),
        }
    return a


def generate_smart_draft(
    user_id: str,
    draft_type: str,
    answers: Dict[str, str],
    *,
    use_ai_polish: bool = False,
) -> Dict[str, Any]:
    spec = SMART_DRAFT_SPECS.get(draft_type)
    if not spec:
        return {"error": "Unknown draft type"}

    missing = [
        q["id"]
        for q in spec.get("questions") or []
        if q.get("required") and not str(answers.get(q["id"]) or "").strip()
    ]
    if missing:
        return {"error": "Missing required fields", "missing": missing}

    from backend.app.core.clause_repo import list_templates, render_template
    from backend.app.core.practice_schema import seed_builtin_templates_if_empty

    seed_builtin_templates_if_empty()
    tpl_name = (spec.get("template_name") or "").lower()
    templates = list_templates(user_id, practice_area=spec.get("practice_area", ""))
    tpl_id = ""
    for t in templates:
        if tpl_name in (t.get("template_name") or "").lower():
            tpl_id = t["template_id"]
            break
    if not tpl_id and templates:
        tpl_id = templates[0]["template_id"]

    body = ""
    missing_vars: List[str] = []
    if tpl_id:
        vars_map = _map_answers_to_template_vars(draft_type, answers)
        out = render_template(user_id, tpl_id, vars_map)
        body = out.get("rendered") or ""
        missing_vars = out.get("missing_variables") or []

    if not body:
        body = _fallback_draft_body(draft_type, answers)

    if use_ai_polish and body:
        body = _polish_with_ollama(draft_type, body, answers)

    return {
        "draft_type": draft_type,
        "rendered": body,
        "missing_variables": missing_vars,
        "template_used": bool(tpl_id),
    }


def _fallback_draft_body(draft_type: str, answers: Dict[str, str]) -> str:
    a = answers or {}
    if draft_type == "legal_notice_salary":
        return (
            f"LEGAL NOTICE\n\n"
            f"To: {a.get('employer_name', '________')}\n\n"
            f"From: {a.get('employee_name', '________')}\n\n"
            f"Under employment during {a.get('employment_period', '________')}, "
            f"salary of {a.get('amount_due', '________')} remains unpaid.\n\n"
            f"You are called upon to pay within 15 days at {a.get('venue', '________')}.\n"
        )
    return json.dumps(a, indent=2)


def _polish_with_ollama(draft_type: str, body: str, answers: Dict[str, str]) -> str:
    try:
        from backend.app.core.llm_orchestrator import get_generator_for_task
        from backend.app.core.llm_task_router import TaskType, router_enabled
        from llms import get_generator

        gen = (
            get_generator_for_task(TaskType.DRAFT_POLISH, user_id="")
            if router_enabled()
            else get_generator(user_id="")
        )
        if not getattr(gen, "available", True):
            return body
        prompt = (
            f"Polish this Indian legal draft ({draft_type}) for professional tone. "
            f"Keep all facts; do not invent parties or amounts.\n\n"
            f"Facts JSON: {json.dumps(answers)}\n\nDraft:\n{body[:6000]}\n\n"
            f"Return only the polished document text."
        )
        out = gen.generate(prompt, temperature=0.15, max_tokens=2400)
        if out and len(out) > 80 and "unavailable" not in out.lower():
            return out.strip()
    except Exception:
        pass
    return body
