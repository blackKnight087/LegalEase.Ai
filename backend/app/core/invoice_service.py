"""
Professional invoice wizard — prefill, totals, draft/finalize, PDF export.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FIRM_DISPLAY_NAME = "LegalEase.Ai"

from backend.app.core.billing_service import list_time_entries, polish_billing_narrative
from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import get_matter
from backend.app.core.saas_schema import ensure_saas_schema
from backend.app.core.sql_compat import ensure_columns
from backend.app.core.trust_service import get_or_create_trust_account

INVOICE_STATUSES = frozenset(
    {
        "DRAFT",
        "GENERATED",
        "ISSUED",  # legacy
        "SENT",
        "VIEWED",
        "PARTIALLY_PAID",
        "PAID",
        "OVERDUE",
        "CANCELLED",
    }
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    return date.today().isoformat()


def _due_default(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _ensure_invoice_columns(conn) -> None:
    ensure_columns(
        conn,
        "invoices",
        (
            ("invoice_number", "TEXT DEFAULT ''", "ALTER TABLE invoices ADD COLUMN invoice_number TEXT DEFAULT ''"),
            ("payload_json", "TEXT DEFAULT '{}'", "ALTER TABLE invoices ADD COLUMN payload_json TEXT DEFAULT '{}'"),
            ("invoice_date", "TEXT DEFAULT ''", "ALTER TABLE invoices ADD COLUMN invoice_date TEXT DEFAULT ''"),
            ("due_date", "TEXT DEFAULT ''", "ALTER TABLE invoices ADD COLUMN due_date TEXT DEFAULT ''"),
            ("balance_due", "REAL DEFAULT 0", "ALTER TABLE invoices ADD COLUMN balance_due REAL DEFAULT 0"),
            ("updated_at", "TEXT DEFAULT ''", "ALTER TABLE invoices ADD COLUMN updated_at TEXT DEFAULT ''"),
        ),
    )


def _next_invoice_number(user_id: str) -> str:
    year = date.today().year
    prefix = f"LE-{year}-"
    conn = connect_data_db()
    _ensure_invoice_columns(conn)
    rows = conn.execute(
        """
        SELECT invoice_number FROM invoices
        WHERE lawyer_id = ? AND invoice_number LIKE ?
        ORDER BY invoice_number DESC LIMIT 1
        """,
        (str(user_id), f"{prefix}%"),
    ).fetchall()
    conn.close()
    seq = 1
    if rows and rows[0][0]:
        m = re.search(r"-(\d+)$", rows[0][0])
        if m:
            seq = int(m.group(1)) + 1
    return f"{prefix}{seq:04d}"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _logo_path() -> Optional[Path]:
    """Prefer PNG for reliable fpdf embedding; fall back to SVG."""
    root = _project_root()
    for candidate in (
        root / "backend" / "assets" / "legalease-logo.png",
        root / "web" / "public" / "legalease-logo.png",
        root / "backend" / "assets" / "legalease-logo.svg",
        root / "web" / "public" / "legalease-logo.svg",
        root / "frontend" / "public" / "scales-logo.svg",
    ):
        if candidate.is_file():
            return candidate
    return None


def _normalize_payment_block(payment: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Always brand invoices as LegalEase.Ai on PDFs and new drafts."""
    base = _default_payment_block()
    if payment:
        for key, val in payment.items():
            if key in base and val is not None:
                base[key] = str(val)
    raw = (base.get("firm_name") or "").strip()
    if not raw or "chambers" in raw.lower() or raw.lower().startswith("legalease"):
        base["firm_name"] = FIRM_DISPLAY_NAME
    return base


def _pdf_draw_brand_header(pdf: Any) -> float:
    """Navy header with product logo + LegalEase.Ai — returns Y below header."""
    header_h = 32.0
    pdf.set_fill_color(30, 58, 95)
    pdf.rect(0, 0, 210, header_h, style="F")

    logo_x, logo_y, logo_w = 12.0, 7.0, 18.0
    logo = _logo_path()
    if logo:
        try:
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(logo_x - 1, logo_y - 1, logo_w + 2, logo_w + 2, style="F")
            pdf.image(str(logo), x=logo_x, y=logo_y, w=logo_w, h=logo_w)
        except Exception:
            logo = None

    text_x = 34.0 if logo else 14.0
    pdf.set_font("Helvetica", "B", 17)
    pdf.set_xy(text_x, 9)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(pdf.get_string_width("LegalEase"), 9, "LegalEase", new_x="RIGHT", new_y="TOP")
    pdf.set_text_color(212, 175, 55)
    pdf.cell(pdf.get_string_width(".Ai"), 9, ".Ai", new_x="RIGHT", new_y="TOP")
    pdf.set_text_color(220, 228, 240)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(text_x, 19)
    pdf.cell(0, 5, "Professional Legal Services Invoice")
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(15, header_h + 2)
    return header_h + 2


def _default_payment_block() -> Dict[str, str]:
    return {
        "firm_name": FIRM_DISPLAY_NAME,
        "bank": "",
        "account_holder": "",
        "account_number": "",
        "ifsc": "",
        "upi": "",
        "payment_link": "",
    }


def _build_narrative(user_id: str, matter: Dict[str, Any], services: List[Dict[str, Any]]) -> str:
    mname = matter.get("matter_name") or "the matter"
    client = matter.get("client_name") or "the client"
    practice = matter.get("practice_area") or "legal"
    lines = [f"Professional legal services rendered for {client} in {mname} ({practice})."]
    if services:
        total_hrs = sum(float(s.get("hours") or 0) for s in services)
        if total_hrs > 0:
            lines.append(f"Counsel time recorded: {total_hrs:.2f} billable hours across {len(services)} line(s).")
    lines.append("Fees are subject to applicable GST and firm terms of engagement.")
    return " ".join(lines)


def build_invoice_prefill(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Matter, trust, unbilled entries as service lines, auto invoice number."""
    ensure_saas_schema()
    matter = get_matter(user_id, matter_id)
    if not matter:
        return {"error": "Matter not found"}

    entries = list_time_entries(user_id, matter_id=matter_id, invoice_status="UNBILLED")
    services: List[Dict[str, Any]] = []
    record_ids: List[str] = []
    for e in entries:
        svc_date = (e.get("created_at") or "")[:10] or _today_iso()
        services.append(
            {
                "record_id": e["record_id"],
                "date": svc_date,
                "description": e.get("narrative_description") or e.get("raw_activity") or "Legal services",
                "hours": float(e.get("units_logged") or 0),
                "rate": float(e.get("rate_per_unit") or 0),
                "amount": round(float(e.get("line_total") or 0), 2),
            }
        )
        record_ids.append(e["record_id"])

    trust = get_or_create_trust_account(user_id, matter_id)
    trust_bal = float(trust.get("trust_balance") or 0) if not trust.get("error") else 0.0

    payload: Dict[str, Any] = {
        "client": {
            "name": matter.get("client_name") or "",
            "email": "",
            "phone": "",
            "address": "",
            "gst": "",
            "company": "",
        },
        "matter": {
            "matter_id": matter_id,
            "matter_name": matter.get("matter_name") or "",
            "matter_number": matter_id[:8].upper(),
            "case_number": matter.get("case_number") or "",
            "court": matter.get("venue") or "",
            "matter_type": matter.get("matter_type") or matter.get("practice_area") or "",
            "lead_lawyer": "",
            "assigned_lawyers": [],
            "practice_area": matter.get("practice_area") or "",
        },
        "billing": {
            "invoice_number": _next_invoice_number(user_id),
            "invoice_date": _today_iso(),
            "due_date": _due_default(30),
            "currency": "INR",
            "billing_type": "Hourly",
        },
        "services": services,
        "expenses": [],
        "taxes": {
            "gst_percent": 18.0,
            "cgst": 0.0,
            "sgst": 0.0,
            "igst": 0.0,
            "tax_exempt": False,
            "intra_state": True,
        },
        "retainer": {
            "current_retainer": round(trust_bal, 2),
            "apply_amount": 0.0,
            "remaining": round(trust_bal, 2),
            "outstanding": 0.0,
        },
        "payment": _default_payment_block(),
        "notes": _build_narrative(user_id, matter, services),
        "record_ids": record_ids,
    }
    totals = compute_totals(payload)
    payload["totals"] = totals
    return {"payload": payload, "matter_id": matter_id}


def compute_totals(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Services + expenses, GST split, retainer apply, balance_due."""
    services = payload.get("services") or []
    expenses = payload.get("expenses") or []
    taxes = payload.get("taxes") or {}
    retainer = payload.get("retainer") or {}

    services_subtotal = round(
        sum(float(s.get("amount") or float(s.get("hours") or 0) * float(s.get("rate") or 0)) for s in services),
        2,
    )
    expenses_subtotal = round(sum(float(e.get("amount") or 0) for e in expenses), 2)
    subtotal = round(services_subtotal + expenses_subtotal, 2)

    tax_exempt = bool(taxes.get("tax_exempt"))
    gst_percent = float(taxes.get("gst_percent") or 18.0)
    intra_state = bool(taxes.get("intra_state", True))

    taxable_amount = services_subtotal
    if not tax_exempt:
        taxable_amount += round(
            sum(float(e.get("amount") or 0) for e in expenses if e.get("taxable", True)),
            2,
        )

    cgst = sgst = igst = 0.0
    tax_amount = 0.0
    if not tax_exempt and taxable_amount > 0:
        tax_amount = round(taxable_amount * gst_percent / 100.0, 2)
        if intra_state:
            half = round(tax_amount / 2.0, 2)
            cgst = half
            sgst = round(tax_amount - half, 2)
        else:
            igst = tax_amount

    grand_total = round(subtotal + tax_amount, 2)
    apply_amount = min(float(retainer.get("apply_amount") or 0), float(retainer.get("current_retainer") or 0))
    apply_amount = min(apply_amount, grand_total)
    apply_amount = round(max(0.0, apply_amount), 2)
    balance_due = round(grand_total - apply_amount, 2)
    remaining_retainer = round(float(retainer.get("current_retainer") or 0) - apply_amount, 2)

    return {
        "services_subtotal": services_subtotal,
        "expenses_subtotal": expenses_subtotal,
        "subtotal": subtotal,
        "taxable_amount": round(taxable_amount, 2),
        "gst_percent": gst_percent,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "tax_amount": tax_amount,
        "grand_total": grand_total,
        "retainer_applied": apply_amount,
        "remaining_retainer": remaining_retainer,
        "balance_due": balance_due,
    }


def _row_to_invoice(row: tuple, payload: Dict[str, Any]) -> Dict[str, Any]:
    totals = payload.get("totals") or compute_totals(payload)
    return {
        "invoice_id": row[0],
        "matter_id": row[1],
        "lawyer_id": row[2],
        "client_name": row[3] or payload.get("client", {}).get("name", ""),
        "invoice_number": row[11] if len(row) > 11 else payload.get("billing", {}).get("invoice_number", ""),
        "subtotal": row[5],
        "tax_rate": row[6],
        "tax_amount": row[7],
        "total": row[8],
        "balance_due": row[15] if len(row) > 15 else totals.get("balance_due", row[8]),
        "status": row[9],
        "invoice_date": row[13] if len(row) > 13 else payload.get("billing", {}).get("invoice_date", ""),
        "due_date": row[14] if len(row) > 14 else payload.get("billing", {}).get("due_date", ""),
        "created_at": row[10],
        "updated_at": row[16] if len(row) > 16 else row[10],
        "payload": payload,
        "totals": totals,
        "line_items": json.loads(row[4]) if row[4] else payload.get("services", []),
    }


def _fetch_invoice_row(conn, user_id: str, invoice_id: str):
    _ensure_invoice_columns(conn)
    return conn.execute(
        """
        SELECT invoice_id, matter_id, lawyer_id, client_name, line_items_json,
               subtotal, tax_rate, tax_amount, total, status, created_at,
               invoice_number, payload_json, invoice_date, due_date, balance_due, updated_at
        FROM invoices WHERE invoice_id = ? AND lawyer_id = ?
        """,
        (invoice_id, str(user_id)),
    ).fetchone()


def get_invoice(user_id: str, invoice_id: str) -> Optional[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    row = _fetch_invoice_row(conn, user_id, invoice_id)
    conn.close()
    if not row:
        return None
    payload_raw = row[12] if len(row) > 12 else "{}"
    try:
        payload = json.loads(payload_raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not payload:
        payload = {
            "client": {"name": row[3]},
            "services": json.loads(row[4]) if row[4] else [],
            "billing": {"invoice_number": row[11] if len(row) > 11 else ""},
        }
    return _row_to_invoice(row, payload)


def list_invoices(
    user_id: str,
    *,
    matter_id: str = "",
    status: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    _ensure_invoice_columns(conn)
    q = """
        SELECT invoice_id, matter_id, lawyer_id, client_name, line_items_json,
               subtotal, tax_rate, tax_amount, total, status, created_at,
               invoice_number, payload_json, invoice_date, due_date, balance_due, updated_at
        FROM invoices WHERE lawyer_id = ?
    """
    params: List[Any] = [str(user_id)]
    if matter_id:
        q += " AND matter_id = ?"
        params.append(matter_id)
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row[12] or "{}")
        except json.JSONDecodeError:
            payload = {}
        out.append(_row_to_invoice(row, payload))
    return out


def save_invoice(
    user_id: str,
    payload: Dict[str, Any],
    *,
    invoice_id: Optional[str] = None,
    status: str = "DRAFT",
) -> Dict[str, Any]:
    ensure_saas_schema()
    if status not in INVOICE_STATUSES:
        return {"error": f"Invalid status: {status}"}

    matter_id = (payload.get("matter") or {}).get("matter_id") or payload.get("matter_id") or ""
    if not matter_id or not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}

    totals = compute_totals(payload)
    payload["totals"] = totals
    payload["payment"] = _normalize_payment_block(payload.get("payment"))

    client_name = (payload.get("client") or {}).get("name") or "Client"
    billing = payload.get("billing") or {}
    invoice_number = billing.get("invoice_number") or _next_invoice_number(user_id)
    billing["invoice_number"] = invoice_number
    payload["billing"] = billing

    services = payload.get("services") or []
    line_items = [
        {
            "record_id": s.get("record_id", ""),
            "description": s.get("description", ""),
            "units": s.get("hours", 0),
            "rate": s.get("rate", 0),
            "amount": s.get("amount", 0),
            "date": s.get("date", ""),
        }
        for s in services
    ]

    tax_rate = float((payload.get("taxes") or {}).get("gst_percent") or 18) / 100.0
    now = _utc()

    conn = connect_data_db()
    _ensure_invoice_columns(conn)

    if invoice_id:
        existing = _fetch_invoice_row(conn, user_id, invoice_id)
        if not existing:
            conn.close()
            return {"error": "Invoice not found"}
        conn.execute(
            """
            UPDATE invoices SET
                matter_id = ?, client_name = ?, line_items_json = ?,
                subtotal = ?, tax_rate = ?, tax_amount = ?, total = ?,
                status = ?, invoice_number = ?, payload_json = ?,
                invoice_date = ?, due_date = ?, balance_due = ?, updated_at = ?
            WHERE invoice_id = ? AND lawyer_id = ?
            """,
            (
                matter_id,
                client_name,
                json.dumps(line_items),
                totals["subtotal"],
                tax_rate,
                totals["tax_amount"],
                totals["grand_total"],
                status,
                invoice_number,
                json.dumps(payload),
                billing.get("invoice_date", _today_iso()),
                billing.get("due_date", _due_default()),
                totals["balance_due"],
                now,
                invoice_id,
                str(user_id),
            ),
        )
        iid = invoice_id
    else:
        iid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO invoices
            (invoice_id, matter_id, lawyer_id, client_name, line_items_json,
             subtotal, tax_rate, tax_amount, total, status, created_at,
             invoice_number, payload_json, invoice_date, due_date, balance_due, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                iid,
                matter_id,
                str(user_id),
                client_name,
                json.dumps(line_items),
                totals["subtotal"],
                tax_rate,
                totals["tax_amount"],
                totals["grand_total"],
                status,
                now,
                invoice_number,
                json.dumps(payload),
                billing.get("invoice_date", _today_iso()),
                billing.get("due_date", _due_default()),
                totals["balance_due"],
                now,
            ),
        )
    conn.commit()
    conn.close()
    saved = get_invoice(user_id, iid)
    return saved or {"invoice_id": iid, "status": status, "payload": payload, "totals": totals}


def finalize_invoice(user_id: str, invoice_id: str, *, mark_billed: bool = True) -> Dict[str, Any]:
    inv = get_invoice(user_id, invoice_id)
    if not inv:
        return {"error": "Invoice not found"}
    if inv["status"] not in ("DRAFT",):
        return {"error": f"Cannot finalize invoice in status {inv['status']}"}

    payload = inv.get("payload") or {}
    out = save_invoice(user_id, payload, invoice_id=invoice_id, status="GENERATED")
    if out.get("error"):
        return out

    if mark_billed:
        record_ids = payload.get("record_ids") or [
            s.get("record_id") for s in (payload.get("services") or []) if s.get("record_id")
        ]
        if record_ids:
            now = _utc()
            conn = connect_data_db()
            for rid in record_ids:
                conn.execute(
                    """
                    UPDATE financial_records SET invoice_status = 'BILLED', updated_at = ?
                    WHERE record_id = ? AND lawyer_id = ?
                    """,
                    (now, rid, str(user_id)),
                )
            conn.commit()
            conn.close()
    return out


def update_invoice_status(user_id: str, invoice_id: str, status: str) -> Dict[str, Any]:
    if status not in INVOICE_STATUSES:
        return {"error": f"Invalid status: {status}"}
    ensure_saas_schema()
    conn = connect_data_db()
    _ensure_invoice_columns(conn)
    row = _fetch_invoice_row(conn, user_id, invoice_id)
    if not row:
        conn.close()
        return {"error": "Invoice not found"}
    now = _utc()
    conn.execute(
        "UPDATE invoices SET status = ?, updated_at = ? WHERE invoice_id = ? AND lawyer_id = ?",
        (status, now, invoice_id, str(user_id)),
    )
    conn.commit()
    conn.close()
    return get_invoice(user_id, invoice_id) or {"error": "Invoice not found"}


def _sanitize_pdf_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u2192", "->").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u20b9", "Rs.")
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _inr(amount: float) -> str:
    return f"Rs. {amount:,.2f}"


def render_invoice_pdf(user_id: str, invoice_id: str) -> Tuple[bytes, str]:
    """fpdf2 professional A4 layout; returns (pdf_bytes, filename)."""
    inv = get_invoice(user_id, invoice_id)
    if not inv:
        raise ValueError("Invoice not found")

    from fpdf import FPDF

    payload = inv.get("payload") or {}
    client = payload.get("client") or {}
    matter = payload.get("matter") or {}
    billing = payload.get("billing") or {}
    payment = _normalize_payment_block(payload.get("payment"))
    payload["payment"] = payment
    taxes = payload.get("taxes") or {}
    totals = inv.get("totals") or compute_totals(payload)
    services = payload.get("services") or []
    expenses = payload.get("expenses") or []
    notes = payload.get("notes") or ""

    inv_no = billing.get("invoice_number") or inv.get("invoice_number") or invoice_id[:8]
    filename = f"Invoice_{inv_no.replace('/', '-')}.pdf"

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    _pdf_draw_brand_header(pdf)

    # Invoice meta
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(95, 7, "BILL TO", new_x="RIGHT", new_y="TOP")
    pdf.cell(95, 7, "INVOICE DETAILS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(95, 5, _sanitize_pdf_text(client.get("name") or inv.get("client_name") or ""))
    pdf.cell(95, 5, f"Invoice #: {_sanitize_pdf_text(inv_no)}", new_x="LMARGIN", new_y="NEXT")
    if client.get("company"):
        pdf.cell(95, 5, _sanitize_pdf_text(client["company"]))
        pdf.cell(95, 5, f"Date: {billing.get('invoice_date', '')}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(95, 5, "")
        pdf.cell(95, 5, f"Date: {billing.get('invoice_date', '')}", new_x="LMARGIN", new_y="NEXT")
    if client.get("email"):
        pdf.cell(95, 5, _sanitize_pdf_text(client["email"]))
        pdf.cell(95, 5, f"Due: {billing.get('due_date', '')}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(95, 5, "")
        pdf.cell(95, 5, f"Due: {billing.get('due_date', '')}", new_x="LMARGIN", new_y="NEXT")
    if client.get("address"):
        pdf.multi_cell(95, 5, _sanitize_pdf_text(client["address"]))
    pdf.ln(4)

    # Matter block
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "MATTER", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    matter_lines = [
        f"Case: {_sanitize_pdf_text(matter.get('matter_name') or '')}",
        f"Case No.: {_sanitize_pdf_text(matter.get('case_number') or '')}",
        f"Court: {_sanitize_pdf_text(matter.get('court') or '')}",
        f"Practice Area: {_sanitize_pdf_text(matter.get('practice_area') or '')}",
    ]
    for line in matter_lines:
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Services table
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(236, 253, 245)
    col_w = [22, 68, 18, 22, 22, 28]
    headers = ["Date", "Description", "Hrs", "Rate", "Amount", "Total"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for svc in services:
        desc = _sanitize_pdf_text((svc.get("description") or "")[:80])
        hrs = float(svc.get("hours") or 0)
        rate = float(svc.get("rate") or 0)
        amt = float(svc.get("amount") or hrs * rate)
        pdf.cell(col_w[0], 6, _sanitize_pdf_text(str(svc.get("date") or "")[:10]), border=1)
        pdf.cell(col_w[1], 6, desc, border=1)
        pdf.cell(col_w[2], 6, f"{hrs:.2f}", border=1, align="R")
        pdf.cell(col_w[3], 6, _inr(rate), border=1, align="R")
        pdf.cell(col_w[4], 6, _inr(amt), border=1, align="R")
        pdf.cell(col_w[5], 6, _inr(amt), border=1, align="R")
        pdf.ln()

    if expenses:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "EXPENSES", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        exp_w = [120, 30, 30]
        for h, w in zip(["Description", "Taxable", "Amount"], exp_w):
            pdf.cell(w, 6, h, border=1, fill=True)
        pdf.ln()
        for exp in expenses:
            pdf.cell(exp_w[0], 6, _sanitize_pdf_text((exp.get("description") or "")[:60]), border=1)
            pdf.cell(exp_w[1], 6, "Yes" if exp.get("taxable", True) else "No", border=1)
            pdf.cell(exp_w[2], 6, _inr(float(exp.get("amount") or 0)), border=1, align="R")
            pdf.ln()

    pdf.ln(4)
    # Totals
    pdf.set_font("Helvetica", "", 9)
    right_x = 130
    pdf.set_x(right_x)
    pdf.cell(35, 6, "Subtotal:", align="R")
    pdf.cell(35, 6, _inr(totals["subtotal"]), align="R", new_x="LMARGIN", new_y="NEXT")
    if not taxes.get("tax_exempt"):
        if taxes.get("intra_state", True):
            pdf.set_x(right_x)
            pdf.cell(35, 6, f"CGST ({totals['gst_percent']/2:.1f}%):", align="R")
            pdf.cell(35, 6, _inr(totals["cgst"]), align="R", new_x="LMARGIN", new_y="NEXT")
            pdf.set_x(right_x)
            pdf.cell(35, 6, f"SGST ({totals['gst_percent']/2:.1f}%):", align="R")
            pdf.cell(35, 6, _inr(totals["sgst"]), align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_x(right_x)
            pdf.cell(35, 6, f"IGST ({totals['gst_percent']:.1f}%):", align="R")
            pdf.cell(35, 6, _inr(totals["igst"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_x(right_x)
    pdf.cell(35, 7, "Grand Total:", align="R")
    pdf.cell(35, 7, _inr(totals["grand_total"]), align="R", new_x="LMARGIN", new_y="NEXT")
    retainer_applied = totals.get("retainer_applied") or 0
    if retainer_applied > 0:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(right_x)
        pdf.cell(35, 6, "Retainer Applied:", align="R")
        pdf.cell(35, 6, f"- {_inr(retainer_applied)}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(right_x)
    pdf.cell(35, 8, "Balance Due:", align="R")
    pdf.cell(35, 8, _inr(totals["balance_due"]), align="R", new_x="LMARGIN", new_y="NEXT")

    # Payment instructions
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "PAYMENT INSTRUCTIONS", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pay_lines = []
    if payment.get("bank"):
        pay_lines.append(f"Bank: {_sanitize_pdf_text(payment['bank'])}")
    if payment.get("account_holder"):
        pay_lines.append(f"Account Holder: {_sanitize_pdf_text(payment['account_holder'])}")
    if payment.get("account_number"):
        pay_lines.append(f"A/c No.: {_sanitize_pdf_text(payment['account_number'])}")
    if payment.get("ifsc"):
        pay_lines.append(f"IFSC: {_sanitize_pdf_text(payment['ifsc'])}")
    if payment.get("upi"):
        pay_lines.append(f"UPI: {_sanitize_pdf_text(payment['upi'])}")
    if payment.get("payment_link"):
        pay_lines.append(f"Pay online: {_sanitize_pdf_text(payment['payment_link'])}")
    if not pay_lines:
        pay_lines.append("Please remit payment within the due date per firm engagement terms.")
    for pl in pay_lines:
        pdf.cell(0, 5, pl, new_x="LMARGIN", new_y="NEXT")

    # Notes
    if notes:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "NOTES", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _sanitize_pdf_text(notes))

    # T&C + signature
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(
        0,
        4,
        _sanitize_pdf_text(
            "Terms: Payment is due within 30 days unless otherwise agreed. "
            "Late payments may attract interest at 18% p.a. All disputes subject to local jurisdiction. "
            "GST as applicable under Indian law."
        ),
    )
    pdf.ln(10)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(90, 6, "Authorised Signatory", new_x="RIGHT", new_y="TOP")
    pdf.cell(90, 6, f"Status: {inv.get('status', '')}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(12)
    pdf.cell(90, 6, "_________________________")

    out = pdf.output()
    return bytes(out), filename
