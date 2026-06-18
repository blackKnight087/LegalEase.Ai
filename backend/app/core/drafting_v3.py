"""Drafting Studio V3 — matter variables, templates, insights, workflow, search, packs."""
from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.drafting_workspace import (
    DOCUMENT_TYPES,
    WORKFLOW_STATUSES,
    get_document,
    get_version_content,
    list_documents,
    update_document,
)
from backend.app.core.practice_schema import ensure_practice_schema

V3_WORKFLOW_STATUSES = (
    "draft",
    "in_review",
    "partner_review",
    "needs_revision",
    "approved",
    "ready_to_file",
    "filed",
    "executed",
    "archived",
)

_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "draft": ["in_review", "archived"],
    "in_review": ["partner_review", "needs_revision", "archived"],
    "partner_review": ["approved", "needs_revision", "archived"],
    "needs_revision": ["in_review", "archived"],
    "approved": ["ready_to_file", "archived"],
    "ready_to_file": ["filed", "archived"],
    "filed": ["executed", "archived"],
    "executed": ["archived"],
    "archived": [],
}

VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}|\{(\w+)\}")


def ensure_workspace_v3_schema() -> None:
    ensure_practice_schema()
    conn = connect_data_db()
    for stmt in (
        "ALTER TABLE workspace_drafts ADD COLUMN content_format TEXT NOT NULL DEFAULT 'markdown'",
        "ALTER TABLE workspace_draft_versions ADD COLUMN content_format TEXT NOT NULL DEFAULT 'markdown'",
        "ALTER TABLE workspace_draft_comments ADD COLUMN resolved INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE workspace_draft_comments ADD COLUMN mentions_json TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE workspace_draft_comments ADD COLUMN assignee TEXT NOT NULL DEFAULT ''",
        """
        CREATE TABLE IF NOT EXISTS workspace_draft_audit (
            audit_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_workspace_audit_draft ON workspace_draft_audit(draft_id)",
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()
    conn.close()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(user_id: str, draft_id: str, action: str, detail: str = "") -> None:
    ensure_workspace_v3_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO workspace_draft_audit (audit_id, draft_id, user_id, action, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), draft_id, str(user_id), action, detail[:2000], _utc()),
    )
    conn.commit()
    conn.close()


def matter_variables(user_id: str, matter_id: str) -> Dict[str, str]:
    """Map matter fields to template placeholders."""
    from backend.app.core.matter_repo import get_matter

    m = get_matter(user_id, matter_id) if matter_id else None
    if not m:
        return {
            "ClientName": "",
            "MatterNumber": "",
            "MatterName": "",
            "CourtName": "",
            "CaseNumber": "",
            "OpposingParty": "",
            "Lawyer": "",
            "Address": "",
            "Venue": "",
            "PracticeArea": "",
        }
    addr = ""
    try:
        from backend.app.core.practice_billing_service import get_matter_billing_profile

        prof = get_matter_billing_profile(user_id, matter_id)
        if prof:
            addr = str(prof.get("client_address") or "")
    except Exception:
        pass
    return {
        "ClientName": str(m.get("client_name") or ""),
        "MatterNumber": str(m.get("matter_id") or "")[:8],
        "MatterName": str(m.get("matter_name") or ""),
        "CourtName": str(m.get("venue") or ""),
        "CaseNumber": str(m.get("case_number") or ""),
        "OpposingParty": str(m.get("opposing_party") or ""),
        "Lawyer": "",
        "Address": addr,
        "Venue": str(m.get("venue") or ""),
        "PracticeArea": str(m.get("practice_area") or ""),
        "FilingDate": str(m.get("filing_date") or ""),
        "NextHearingDate": str(m.get("next_hearing_date") or ""),
        "client_name": str(m.get("client_name") or ""),
        "matter_name": str(m.get("matter_name") or ""),
        "case_number": str(m.get("case_number") or ""),
        "court": str(m.get("venue") or ""),
    }


def apply_variables(text: str, variables: Dict[str, str]) -> str:
    out = text or ""

    def repl(m: re.Match) -> str:
        key = m.group(1) or m.group(2) or ""
        return variables.get(key) or variables.get(key.lower()) or m.group(0)

    return VAR_PATTERN.sub(repl, out)


def autofill_document(user_id: str, draft_id: str) -> Optional[Dict[str, Any]]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return None
    mid = doc.get("matter_id") or ""
    if not mid:
        return {"error": "Link a matter first", "variables": {}}
    vars_ = matter_variables(user_id, mid)
    new_content = apply_variables(doc.get("content") or "", vars_)
    parties = dict(doc.get("parties") or {})
    parties.update({k: v for k, v in vars_.items() if v and k[0].islower()})
    updated = update_document(
        user_id,
        draft_id,
        content=new_content,
        parties=parties,
        change_summary="Matter autofill",
    )
    _audit(user_id, draft_id, "autofill", f"matter={mid}")
    return {"document": updated, "variables": vars_}


def list_v3_templates(user_id: str) -> List[Dict[str, Any]]:
    from backend.app.core.clause_repo import list_templates

    ensure_practice_schema()
    builtin = [
        {"template_id": t["id"], "template_name": t["label"], "practice_area": t["category"], "source": "builtin"}
        for t in BUILTIN_TEMPLATES
    ]
    firm = [
        {**t, "source": "firm"}
        for t in list_templates(user_id)
    ]
    return builtin + firm


def render_v3_template(
    user_id: str,
    template_id: str,
    *,
    matter_id: str = "",
    extra_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    vars_ = dict(extra_vars or {})
    if matter_id:
        vars_.update(matter_variables(user_id, matter_id))
    builtin = next((t for t in BUILTIN_TEMPLATES if t["id"] == template_id), None)
    if builtin:
        rendered = apply_variables(builtin["body"], vars_)
        return {"rendered": rendered, "template_name": builtin["label"], "variables_used": vars_}
    from backend.app.core.clause_repo import render_template

    out = render_template(user_id, template_id, {k.lower(): v for k, v in vars_.items()})
    if out.get("error"):
        return out
    return {
        "rendered": out.get("rendered") or "",
        "template_name": out.get("template_name"),
        "variables_used": vars_,
        "missing_variables": out.get("missing_variables"),
    }


def document_insights(
    user_id: str,
    content: str,
    *,
    document_type: str = "contract",
    status: str = "draft",
    version_count: int = 1,
) -> Dict[str, Any]:
    from backend.app.core.drafting_clause_intel import analyze_document, clause_recommendations_v3

    plain = html_to_plain(content)
    analysis = analyze_document(plain, document_type=document_type)
    recs = clause_recommendations_v3(user_id, plain)
    words = len(plain.split())
    clauses = len(re.findall(r"\b(?:section|clause|article)\s+\d+", plain, re.I))
    sig_required = 0 if re.search(r"\bsignature|execut|witness\b", plain, re.I) else 1
    return {
        "word_count": words,
        "clause_count": clauses,
        "risk_score": analysis.get("clause_risk_score"),
        "review_status": status,
        "version_count": version_count,
        "missing_sections": [m["clause"] for m in analysis.get("missing_clauses") or []],
        "formatting_issues": analysis.get("formatting_issues") or [],
        "required_signatures": sig_required,
        "clause_recommendations": len(recs.get("recommendations") or []),
    }


def transition_status(user_id: str, draft_id: str, new_status: str) -> Dict[str, Any]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    cur = doc.get("status") or "draft"
    ns = (new_status or "").strip()
    if ns not in V3_WORKFLOW_STATUSES:
        return {"error": f"Invalid status: {ns}"}
    allowed = _STATUS_TRANSITIONS.get(cur, [])
    if ns != cur and ns not in allowed:
        return {"error": f"Cannot move from {cur} to {ns}", "allowed": allowed}
    if ns == "filed" and cur not in ("ready_to_file", "approved"):
        return {"error": "Document must be approved or ready to file before filing"}
    updated = update_document(user_id, draft_id, status=ns, change_summary=f"Status → {ns}")
    _audit(user_id, draft_id, "status_change", f"{cur} → {ns}")
    return {"document": updated, "previous_status": cur}


def workspace_search(user_id: str, q: str, *, limit: int = 50) -> Dict[str, Any]:
    ensure_workspace_v3_schema()
    ql = f"%{q.strip()}%"
    if not q.strip():
        return {"documents": [], "clauses": [], "templates": [], "comments": []}
    docs = list_documents(user_id, q=q, limit=limit)
    from backend.app.core.clause_repo import list_clauses, list_templates

    clauses = [c for c in list_clauses(user_id) if ql[1:-1].lower() in (c.get("clause_text_content") or "").lower() or ql[1:-1].lower() in (c.get("clause_tag") or "").lower()][:20]
    templates = [t for t in list_templates(user_id) if ql[1:-1].lower() in (t.get("template_name") or "").lower()][:20]
    conn = connect_data_db()
    comments = []
    rows = conn.execute(
        """
        SELECT c.comment_id, c.draft_id, c.body, c.author_name, d.title
        FROM workspace_draft_comments c
        JOIN workspace_drafts d ON d.draft_id = c.draft_id
        WHERE d.user_id = ? AND c.body LIKE ?
        LIMIT ?
        """,
        (str(user_id), ql, min(limit, 30)),
    ).fetchall()
    conn.close()
    for r in rows:
        comments.append({"comment_id": r[0], "draft_id": r[1], "body": r[2], "author_name": r[3], "document_title": r[4]})
    return {"documents": docs, "clauses": clauses, "templates": templates, "comments": comments}


def compare_versions_v3(user_id: str, draft_id: str, version_a: int, version_b: int) -> Dict[str, Any]:
    from backend.app.core.drafting_clause_intel import analyze_document
    from backend.app.core.drafting_workspace import compare_versions
    from document_services.redline_engine import generate_diff_html

    base = compare_versions(user_id, draft_id, version_a, version_b)
    if base.get("error"):
        return base
    a = get_version_content(user_id, draft_id, version_a) or ""
    b = get_version_content(user_id, draft_id, version_b) or ""
    ra = analyze_document(html_to_plain(a))
    rb = analyze_document(html_to_plain(b))
    return {
        **base,
        "side_by_side_html": _side_by_side_html(a, b),
        "risk_delta": int(rb.get("clause_risk_score", 0)) - int(ra.get("clause_risk_score", 0)),
        "clause_changes": _clause_change_summary(a, b),
    }


def _side_by_side_html(left: str, right: str) -> str:
    import html as html_mod

    l_lines = html_to_plain(left).splitlines()
    r_lines = html_to_plain(right).splitlines()
    rows = []
    for i in range(max(len(l_lines), len(r_lines))):
        lv = html_mod.escape(l_lines[i] if i < len(l_lines) else "")
        rv = html_mod.escape(r_lines[i] if i < len(r_lines) else "")
        cls = "diff-same" if lv == rv else "diff-changed"
        rows.append(
            f'<tr class="{cls}"><td class="diff-left">{lv or "&nbsp;"}</td>'
            f'<td class="diff-right">{rv or "&nbsp;"}</td></tr>'
        )
    return (
        '<table class="side-by-side-compare"><thead><tr>'
        '<th>Version A</th><th>Version B</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def _clause_change_summary(a: str, b: str) -> List[str]:
    tags = ("confidentiality", "indemnity", "termination", "arbitration", "jurisdiction")
    changes = []
    pa = html_to_plain(a).lower()
    pb = html_to_plain(b).lower()
    for t in tags:
        in_a = t in pa
        in_b = t in pb
        if in_a != in_b:
            changes.append(f"{t}: {'added' if in_b else 'removed'}")
    return changes


def html_to_plain(text: str) -> str:
    t = text or ""
    if "<" not in t:
        return t
    t = re.sub(r"</t[dh]>", " ", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p>", "\n", t, flags=re.I)
    t = re.sub(r"</h[1-6]>", "\n\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def export_document_v3(
    user_id: str,
    draft_id: str,
    fmt: str = "pdf",
    *,
    watermark: str = "",
    firm_name: str = "LegalEase",
    signature_blocks: bool = False,
) -> Tuple[bytes, str, str]:
    from backend.app.core.drafting_export_v3 import export_legal_document

    doc = get_document(user_id, draft_id)
    if not doc:
        raise ValueError("Document not found")
    body = doc.get("content") or ""
    if signature_blocks and "IN WITNESS" not in body.upper():
        from backend.app.core.drafting_document_format import EXECUTION_BLOCK_HTML

        body += EXECUTION_BLOCK_HTML
    return export_legal_document(
        body,
        title=doc.get("title") or "Document",
        fmt=fmt,
        watermark=watermark,
        firm_name=firm_name,
        content_format=doc.get("content_format") or ("html" if "<p" in body else "markdown"),
    )


def create_document_pack(
    user_id: str,
    draft_ids: List[str],
    *,
    pack_format: str = "zip",
) -> Tuple[bytes, str, str]:
    ensure_workspace_v3_schema()
    pdfs: List[Tuple[str, bytes]] = []
    for did in draft_ids:
        try:
            data, fname, _ = export_document_v3(user_id, did, "pdf")
            pdfs.append((fname, data))
        except Exception:
            continue
    if not pdfs:
        raise ValueError("No documents to pack")
    if pack_format == "pdf" and len(pdfs) == 1:
        return pdfs[0][1], pdfs[0][0], "application/pdf"
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, data in pdfs:
            zf.writestr(fname, data)
    buf.seek(0)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    return buf.read(), f"document_pack_{ts}.zip", "application/zip"


def list_audit_trail(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_workspace_v3_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT audit_id, user_id, action, detail, created_at
        FROM workspace_draft_audit WHERE draft_id = ?
        ORDER BY created_at DESC LIMIT 100
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {"audit_id": r[0], "user_id": r[1], "action": r[2], "detail": r[3], "created_at": r[4]}
        for r in rows
    ]


def resolve_comment(user_id: str, draft_id: str, comment_id: str, resolved: bool = True) -> Dict[str, Any]:
    if not get_document(user_id, draft_id):
        return {"error": "Document not found"}
    ensure_workspace_v3_schema()
    conn = connect_data_db()
    conn.execute(
        "UPDATE workspace_draft_comments SET resolved = ? WHERE comment_id = ? AND draft_id = ?",
        (1 if resolved else 0, comment_id, draft_id),
    )
    conn.commit()
    conn.close()
    _audit(user_id, draft_id, "comment_resolve", comment_id)
    return {"ok": True}


def copilot_command(user_id: str, draft_id: str, command: str, selection: str = "", instruction: str = "") -> Dict[str, Any]:
    from backend.app.core.drafting_workspace import _polish_draft

    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    text = (selection or doc.get("content") or "")[:12000]
    cmd = (command or "").strip().lower()
    prompts = {
        "draft_clause": f"Draft a single formal legal clause for Indian law. Context: {instruction}\n\nDocument excerpt:\n{text[:4000]}",
        "rewrite_formal": f"Rewrite in formal Indian legal language:\n{text[:8000]}",
        "shorten": f"Shorten while preserving legal meaning:\n{text[:8000]}",
        "expand": f"Expand with professional legal detail:\n{text[:6000]}",
        "summarize": f"Summarize concisely:\n{text[:8000]}",
        "explain_clause": f"Explain this clause in plain English:\n{text[:4000]}",
        "affidavit_section": f"Draft affidavit section (Indian format):\n{instruction}\n\n{text[:4000]}",
        "notice_section": f"Draft legal notice section:\n{instruction}\n\n{text[:4000]}",
        "petition_section": f"Draft petition section for Indian courts:\n{instruction}\n\n{text[:4000]}",
        "precedent_language": f"Suggest precedent-style language (do not invent case citations):\n{instruction}\n\n{text[:4000]}",
        "execution_block": (
            "Output ONLY valid HTML (no markdown). Create an EXECUTION section with "
            "IN WITNESS WHEREOF text and two HTML tables: parties (Party A, Party B) "
            "and witnesses (Witness 1, Witness 2) with columns Name, Signature, Date."
        ),
        "signature_block": (
            "Output ONLY valid HTML signature blocks for Party A, Party B, Witness 1, Witness 2. "
            "Use <h3> for each party label and <p> lines for Name, Signature, Date. No markdown tables."
        ),
        "chat": f"{instruction}\n\nDocument excerpt:\n{text[:8000]}",
    }
    if cmd == "execution_block":
        from backend.app.core.drafting_document_format import EXECUTION_BLOCK_HTML

        return {"result": EXECUTION_BLOCK_HTML, "command": cmd, "sources": []}
    if cmd == "signature_block":
        from backend.app.core.drafting_document_format import SIGNATURE_BLOCK_HTML

        return {"result": SIGNATURE_BLOCK_HTML, "command": cmd, "sources": []}
    prompt = prompts.get(cmd, f"{instruction}\n\n{text[:8000]}")
    result = _polish_draft(user_id, prompt, doc.get("title") or "Document", instruction)
    if cmd == "chat" or "|" in (result or ""):
        from backend.app.core.drafting_document_format import markdown_to_html

        result = markdown_to_html(result or "")
    sources: List[str] = []
    if cmd in ("precedent_language", "draft_clause"):
        try:
            from backend.app.core.drafting_clause_intel import enrich_with_clause_refs

            snippet, src = enrich_with_clause_refs(user_id, "", doc.get("jurisdiction") or "")
            if src:
                sources = src
        except Exception:
            pass
    return {"result": result, "command": cmd, "sources": sources}


_PETITION_TMPL = """# PETITION

**IN THE COURT OF** {{CourtName}}

**Case No.** {{CaseNumber}}

**Between:**
{{ClientName}} ... Petitioner
**And**
{{OpposingParty}} ... Respondent

## Facts
{{Facts}}

## Grounds
1. 
2. 

## Prayer
It is therefore prayed that this Hon'ble Court may be pleased to:

## Verification
I verify that the contents of this petition are true to my knowledge.

**Place:** {{Venue}}
**Date:** ________

**(Signature of Petitioner)**
"""

_AFFIDAVIT_TMPL = """# AFFIDAVIT

I, **{{ClientName}}**, residing at {{Address}}, do hereby solemnly affirm and state as under:

1. 
2. 

**DEPONENT**

**VERIFICATION**

I, the above-named deponent, verify that the contents of this affidavit are true to my knowledge.

Verified at {{Venue}} on ________.

**(Signature)**
"""

_NOTICE_TMPL = """# LEGAL NOTICE

**To,**
{{OpposingParty}}

Under instructions from my client **{{ClientName}}**, I hereby serve upon you the following notice:

## Facts
{{Facts}}

## Demand
You are called upon to comply within 15 (fifteen) days failing which legal proceedings shall be initiated.

**Place:** {{Venue}}
**Date:** ________

**Advocate for {{ClientName}}**
"""

_BAIL_TMPL = """# APPLICATION FOR BAIL
**(Under Section 439 of the Code of Criminal Procedure, 1973)**

**IN THE COURT OF** {{CourtName}}

**Criminal Misc. Application No.** {{CaseNumber}}

**Applicant:** {{ClientName}}

**Versus** State of ________ — Respondent

## Grounds
1. That the Applicant is innocent and has been falsely implicated; investigation is complete / custody is not required.
2. That the Applicant resides at {{Address}}, {{Venue}}, and is not a flight risk.
3. That the Applicant undertakes to abide by all conditions and appear on every date.

## Prayer
It is prayed that this Hon'ble Court enlarge the Applicant on bail on such terms as deemed fit.

**Place:** {{Venue}}
**Date:** ________

**Through Counsel for the Applicant**
"""

_AGREEMENT_TMPL = """# AGREEMENT

**{{MatterName}}**

This Agreement is made at {{Venue}} on ________ 2026 between **{{ClientName}}** (Party A) and **{{OpposingParty}}** (Party B).

## 1. Scope
Party B shall perform agreed services with reasonable skill and care. Party A shall cooperate and pay fees within fifteen (15) days of valid invoice.

## 2. Confidentiality
Each Party shall protect non-public information for three (3) years after termination.

## 3. Termination
Either Party may terminate on thirty (30) days' notice or for uncured material breach.

## 4. Indemnity
Each Party indemnifies the other for losses arising from its breach or negligence.

## 5. Dispute resolution
Disputes shall be resolved by arbitration under the Arbitration and Conciliation Act, 1996, seated at {{Venue}}. Courts at {{Venue}} have jurisdiction for interim relief.

## 6. Governing law
Laws of India.

## Execution
IN WITNESS WHEREOF the parties have executed this Agreement.

**Party A** — Name / Signature / Date
**Party B** — Name / Signature / Date
"""

_NDA_TMPL = """# NON-DISCLOSURE AGREEMENT

This Agreement is entered into at {{Venue}} on ________ between:

**Disclosing Party:** {{ClientName}}
**Receiving Party:** {{OpposingParty}}

## Confidential Information
## Obligations
## Term
## Governing Law
Courts at {{CourtName}} shall have exclusive jurisdiction.

## Execution
"""

_EMPLOYMENT_TMPL = """# EMPLOYMENT AGREEMENT

**Employer:** {{ClientName}}
**Employee:** {{OpposingParty}}

## Position and duties
## Compensation
## Confidentiality
## Termination
## Governing law — {{Venue}}

## Execution
"""

_WRITTEN_STMT_TMPL = """# WRITTEN STATEMENT

**Court:** {{CourtName}}
**Case No.** {{CaseNumber}}

**Defendant:** {{ClientName}}

## Preliminary objections
## Para-wise reply
## Additional pleadings

**Verified at** {{Venue}}
"""

_REPLY_TMPL = """# REPLY

**Court:** {{CourtName}}
**Case No.** {{CaseNumber}}

**Re:** Reply on behalf of {{ClientName}}

## Reply to allegations
## Prayer

**Place:** {{Venue}}
"""

BUILTIN_TEMPLATES: List[Dict[str, Any]] = [
    {"id": "agreement", "label": "Agreement", "category": "Commercial", "body": _AGREEMENT_TMPL},
    {"id": "petition", "label": "Petition", "category": "Litigation", "body": _PETITION_TMPL},
    {"id": "affidavit", "label": "Affidavit", "category": "Litigation", "body": _AFFIDAVIT_TMPL},
    {"id": "legal_notice", "label": "Legal Notice", "category": "Litigation", "body": _NOTICE_TMPL},
    {"id": "bail_application", "label": "Bail Application", "category": "Criminal", "body": _BAIL_TMPL},
    {"id": "nda", "label": "NDA", "category": "Commercial", "body": _NDA_TMPL},
    {"id": "employment_contract", "label": "Employment Contract", "category": "Employment", "body": _EMPLOYMENT_TMPL},
    {"id": "written_statement", "label": "Written Statement", "category": "Litigation", "body": _WRITTEN_STMT_TMPL},
    {"id": "reply", "label": "Reply", "category": "Litigation", "body": _REPLY_TMPL},
]
