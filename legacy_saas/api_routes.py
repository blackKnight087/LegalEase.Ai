"""Extended API routes — full Streamlit feature parity."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api_server import _current_user

router = APIRouter(prefix="/api", tags=["features"])


# ---------- Dashboard (enhanced) ----------

@router.get("/dashboard/full")
def dashboard_full(user: Dict = Depends(_current_user)):
    from app import (
        get_user_stats,
        get_knowledge_base_status,
        get_chat_history,
        run_query,
    )
    from llms import generator_status

    uid = user["id"]
    stats = get_user_stats(uid)
    kb = get_knowledge_base_status(uid) or {}
    gen = generator_status()
    history = get_chat_history(uid, limit=5) or []
    recent_queries = [
        {"question": q, "answer": (a or "")[:400], "created_at": c}
        for q, a, _lang, c in history
    ]
    docs = run_query(
        "SELECT filename, pages, uploaded_at FROM documents WHERE uploader_id = ? ORDER BY uploaded_at DESC LIMIT 5",
        (uid,),
        fetch=True,
    ) or []
    practice = {}
    try:
        from backend.app.services.practice_dashboard import practice_overview

        practice = practice_overview(uid)
    except Exception:
        pass
    return {
        "username": user["username"],
        "membership": user["membership"],
        "documents": stats.get("documents", 0),
        "queries": stats.get("queries", 0),
        "kb_status": kb.get("status", "unknown"),
        "kb_chunks": kb.get("total_chunks", 0),
        "llm_online": bool(gen.get("online") or gen.get("available")),
        "recent_queries": recent_queries,
        "recent_documents": [
            {"filename": r[0], "pages": r[1], "uploaded_at": r[2]} for r in docs
        ],
        "practice": practice,
    }


# ---------- KB health ----------

@router.get("/kb/health")
def kb_health(user: Dict = Depends(_current_user)):
    from app import (
        get_knowledge_base_status,
        get_user_document_count,
        get_user_index_dir,
        run_query,
    )
    from rag import diagnose_kb_health, index_exists

    uid = user["id"]
    kb = get_knowledge_base_status(uid)
    doc_count = get_user_document_count(uid)
    index_dir = get_user_index_dir(uid)
    chunk_row = run_query(
        "SELECT COUNT(*) FROM documents WHERE uploader_id = ?",
        (uid,),
        fetch=True,
    )
    report = diagnose_kb_health(
        index_dir=index_dir,
        document_count=doc_count,
        db_chunk_count=kb.get("total_chunks", 0),
        db_status=kb.get("status", "unknown"),
    )
    return {
        "status": kb.get("status"),
        "documents": doc_count,
        "chunks": kb.get("total_chunks", 0),
        "index_exists": index_exists(index_dir),
        "last_updated": kb.get("last_updated"),
        "health": report,
    }


# ---------- Documents extras ----------

@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, user: Dict = Depends(_current_user)):
    from app import delete_user_document, build_faiss_index
    if not delete_user_document(doc_id, user["id"]):
        raise HTTPException(404, "Document not found")
    build_faiss_index(user["id"])
    return {"status": "deleted"}


@router.get("/documents/{doc_id}/timeline")
def document_timeline(doc_id: str, user: Dict = Depends(_current_user)):
    from app import run_query
    owned = run_query(
        "SELECT id FROM documents WHERE id = ? AND uploader_id = ?",
        (doc_id, user["id"]),
        fetch=True,
    )
    if not owned:
        raise HTTPException(404, "Document not found")
    events = run_query(
        "SELECT event_date, mention_text, page FROM document_timeline WHERE document_id = ? ORDER BY event_date",
        (doc_id,),
        fetch=True,
    ) or []
    return {
        "events": [
            {"date": e[0], "text": e[1], "page": e[2]} for e in events
        ]
    }


@router.get("/documents/{doc_id}/entities")
def document_entities(doc_id: str, user: Dict = Depends(_current_user)):
    from app import run_query
    owned = run_query(
        "SELECT id FROM documents WHERE id = ? AND uploader_id = ?",
        (doc_id, user["id"]),
        fetch=True,
    )
    if not owned:
        raise HTTPException(404, "Document not found")
    rows = run_query(
        "SELECT plaintiff, defendant, judge, court, case_number, sections FROM case_entities WHERE document_id = ? LIMIT 1",
        (doc_id,),
        fetch=True,
    )
    if not rows:
        return {"entities": None}
    r = rows[0]
    return {
        "entities": {
            "plaintiff": r[0],
            "defendant": r[1],
            "judge": r[2],
            "court": r[3],
            "case_number": r[4],
            "sections": r[5],
        }
    }


# ---------- Legal tools ----------

class IpcConvertRequest(BaseModel):
    section: str


class IpcBulkRequest(BaseModel):
    sections: List[str]


class CourtFeeRequest(BaseModel):
    suit_value: float
    region: str
    suit_type: str = "civil"
    court_level: str = "district"


class CasePredictionRequest(BaseModel):
    case_details: str
    court_type: str = "District Court"


class CitationsRequest(BaseModel):
    citations: List[str]


class OdrRequest(BaseModel):
    complainant: str
    respondent: str
    complaint_type: str
    dispute_value: float
    details: str


def _ipc_lookup_response(out: Dict[str, Any]) -> Dict[str, Any]:
    from backend.app.core.ipc_bns_engine_v3 import NOT_FOUND_MSG

    if not out.get("found"):
        return {
            **out,
            "status": "not_found",
            "ipc_section": out.get("ipc_section"),
            "bns_section": out.get("bns_section") or "Not found in database",
            "description": out.get("message") or NOT_FOUND_MSG,
        }
    return {
        **out,
        "status": "mapped",
        "ipc_section": out.get("ipc_section"),
        "bns_section": out.get("bns_section"),
        "description": out.get("short_description") or out.get("offence_title"),
    }


@router.get("/tools/ipc-bns/ipc/{section}")
def ipc_lookup_get(section: str):
    from backend.app.core.ipc_bns_engine_v3 import lookup_ipc

    return _ipc_lookup_response(lookup_ipc(section.strip()))


@router.get("/tools/ipc-bns/bns/{section}")
def bns_lookup_get(section: str):
    from backend.app.core.ipc_bns_engine_v3 import lookup_bns

    return _ipc_lookup_response(lookup_bns(section.strip()))


@router.post("/tools/ipc-bns/convert")
def ipc_convert(req: IpcConvertRequest):
    from backend.app.core.ipc_bns_engine_v3 import lookup_ipc

    return _ipc_lookup_response(lookup_ipc(req.section.strip()))


@router.post("/tools/ipc-bns/bulk")
def ipc_bulk(req: IpcBulkRequest):
    from backend.app.core.ipc_bns_engine_v3 import bulk_convert_ipc

    data = bulk_convert_ipc(req.sections)
    legacy = []
    for r in data.get("results") or []:
        legacy.append(
            {
                "status": "mapped" if r.get("found") else "not_found",
                "ipc_section": r.get("ipc_section"),
                "bns_section": r.get("bns_section") if r.get("found") else "Not found in database",
                "description": r.get("short_description") if r.get("found") else r.get("message"),
            }
        )
    return {"results": legacy}


@router.get("/tools/ipc-bns/categories")
def ipc_categories():
    return {
        "categories": [
            "murder", "theft", "robbery", "assault", "sexual_offenses",
            "cheating", "forgery", "defamation", "kidnapping", "dowry", "trespass",
        ]
    }


@router.get("/tools/ipc-bns/category/{category}")
def ipc_category(category: str):
    from legal_tools import get_bns_by_category
    return {"sections": get_bns_by_category(category)}


@router.get("/tools/court-fee/regions")
def court_fee_regions():
    from utils.court_fee import get_available_regions
    return {"regions": get_available_regions()}


@router.post("/tools/court-fee")
def court_fee(req: CourtFeeRequest):
    from utils.court_fee import get_fee_breakdown
    region = req.region.lower().replace(" ", "_")
    return get_fee_breakdown(
        req.suit_value, region, req.suit_type.lower(), req.court_level.lower()
    )


@router.post("/tools/contract-review")
async def contract_review(file: UploadFile = File(...), user: Dict = Depends(_current_user)):
    from PyPDF2 import PdfReader
    from llms import analyze_contract
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF required")
    data = await file.read()
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:
        raise HTTPException(400, f"Could not read PDF: {e}") from e
    if not text.strip():
        raise HTTPException(400, "No text in PDF")
    return {"analysis": analyze_contract(text)}


@router.post("/tools/case-prediction")
def case_prediction(req: CasePredictionRequest, user: Dict = Depends(_current_user)):
    raise HTTPException(
        410,
        "Case outcome prediction has been removed. Use IPC-BNS Intelligence for verified legal reference.",
    )
    from llms import predict_case_outcome  # noqa: F401 — unreachable
    if not req.case_details.strip():
        raise HTTPException(400, "case_details required")
    return {"prediction": predict_case_outcome(req.case_details, req.court_type)}


@router.post("/tools/citations")
def citations_check(req: CitationsRequest, user: Dict = Depends(_current_user)):
    from llms import check_citation_validity
    if not req.citations:
        raise HTTPException(400, "citations required")
    return {"result": check_citation_validity(req.citations)}


@router.post("/tools/odr")
def odr_proposal(req: OdrRequest, user: Dict = Depends(_current_user)):
    from llms import generate_odr_resolution
    return {
        "proposal": generate_odr_resolution({
            "complainant": req.complainant,
            "respondent": req.respondent,
            "type": req.complaint_type,
            "value": req.dispute_value,
            "details": req.details,
        })
    }


# Fix missing io import in contract_review
import io  # noqa: E402


# ---------- Drafting ----------

class DraftRequest(BaseModel):
    template: str
    context: Dict[str, Any] = Field(default_factory=dict)
    use_ai: bool = False


@router.get("/drafting/templates")
def drafting_templates():
    from drafting import get_available_templates
    info = {
        "LEGAL_NOTICE": ("📨", "Legal notice"),
        "AFFIDAVIT": ("📜", "Sworn affidavit"),
        "CHARGESHEET": ("⚖️", "Police chargesheet"),
        "CONTRACT": ("📋", "Business contract"),
        "BAIL_APPLICATION": ("🔓", "Bail application"),
    }
    templates = get_available_templates()
    return {
        "templates": [
            {"id": t, "icon": info.get(t, ("📄", ""))[0], "label": info.get(t, (t, t))[1]}
            for t in templates
        ]
    }


@router.get("/drafting/templates/{template_id}/fields")
def drafting_fields(template_id: str):
    from drafting import get_template_fields
    return {"template": template_id, "fields": get_template_fields(template_id)}


@router.post("/drafting/generate")
def drafting_generate(req: DraftRequest, user: Dict = Depends(_current_user)):
    from drafting import generate_draft
    import uuid
    from app import run_query, _utc_iso
    try:
        draft = generate_draft(req.template, req.context, use_ai=req.use_ai)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    draft_id = str(uuid.uuid4())
    run_query(
        "INSERT INTO drafts (id, user_id, draft_type, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (draft_id, user["id"], req.template, draft, _utc_iso()),
    )
    return {"draft_id": draft_id, "content": draft, "template": req.template}


# ---------- Analytics ----------

@router.get("/analytics")
def analytics(user: Dict = Depends(_current_user)):
    from app import get_user_stats, get_knowledge_base_status, run_query
    uid = user["id"]
    stats = get_user_stats(uid)
    kb = get_knowledge_base_status(uid)
    daily = run_query(
        "SELECT DATE(created_at) as d, COUNT(*) FROM chat_history WHERE user_id = ? GROUP BY DATE(created_at) ORDER BY d DESC LIMIT 30",
        (uid,),
        fetch=True,
    ) or []
    modes = run_query(
        "SELECT mode, COUNT(*) FROM chat_history WHERE user_id = ? GROUP BY mode",
        (uid,),
        fetch=True,
    ) or []
    langs = run_query(
        "SELECT language, COUNT(*) FROM chat_history WHERE user_id = ? GROUP BY language",
        (uid,),
        fetch=True,
    ) or []
    return {
        "documents": stats.get("documents", 0),
        "queries": stats.get("queries", 0),
        "kb_status": kb.get("status"),
        "daily_activity": [{"date": r[0], "count": r[1]} for r in reversed(daily)],
        "by_mode": [{"mode": r[0], "count": r[1]} for r in modes],
        "by_language": [{"language": r[0], "count": r[1]} for r in langs],
    }


# ---------- Settings ----------

@router.get("/settings")
def settings(user: Dict = Depends(_current_user)):
    from llms import generator_status, web_search_status, reset_generator
    from ocr_engine import ocr_status
    gen = generator_status()
    ws = web_search_status()
    ocr = ocr_status()
    return {
        "user": user,
        "llm": gen,
        "web_search": ws,
        "ocr": ocr,
    }


class UpgradeRequest(BaseModel):
    plan: str


@router.post("/settings/upgrade")
def upgrade(req: UpgradeRequest, user: Dict = Depends(_current_user)):
    from backend.app.core.stripe_billing import stripe_enabled, upgrade_membership

    if req.plan not in ("Pro", "Legal Pro"):
        raise HTTPException(400, "Invalid plan")
    if stripe_enabled():
        raise HTTPException(
            400,
            "Use POST /api/v1/billing/subscribe for Stripe Checkout (legacy mock upgrade disabled)",
        )
    if not upgrade_membership(str(user["id"]), req.plan):
        raise HTTPException(500, "Could not update membership")
    return {"membership": req.plan, "success": True}


@router.get("/settings/payments")
def payments(user: Dict = Depends(_current_user)):
    from app import get_payment_history
    rows = get_payment_history(user["id"]) or []
    return {
        "payments": [
            {"plan": r[0], "amount": r[1], "status": r[2], "date": r[3], "expires": r[4]}
            for r in rows
        ]
    }


@router.post("/settings/llm-test")
def llm_test(user: Dict = Depends(_current_user)):
    from llms import get_generator, generator_status
    gen_status = generator_status()
    if not gen_status.get("available") and not gen_status.get("online"):
        raise HTTPException(503, "LLM not connected")
    try:
        reply = get_generator().generate(
            "Reply with the single word PONG.",
            temperature=0.0,
            max_tokens=16,
        )
        return {"reply": (reply or "")[:200]}
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@router.post("/settings/llm-recheck")
def llm_recheck(user: Dict = Depends(_current_user)):
    from llms import reset_generator, generator_status
    reset_generator()
    return generator_status()
