"""
Practice billing workspace — matter profiles, expenses, collections, reports.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.billing_service import (
    billing_summary,
    list_time_entries,
    log_time_entry,
    polish_billing_narrative,
)
from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import execute_script
from backend.app.core.invoice_service import INVOICE_STATUSES, list_invoices
from backend.app.core.matter_repo import get_matter
from backend.app.core.saas_schema import ensure_saas_schema
from backend.app.core.trust_service import get_or_create_trust_account, list_trust_transactions

EXPENSE_TYPES = (
    "Court Filing Fees",
    "Travel",
    "Printing",
    "Photocopying",
    "Courier",
    "Stamp Duty",
    "Documentation",
    "Miscellaneous",
)

PAID_STATUSES = frozenset({"PAID", "PARTIALLY_PAID"})
COLLECTED_STATUSES = frozenset({"PAID", "PARTIALLY_PAID", "SENT", "VIEWED", "GENERATED", "ISSUED"})


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_billing_tables(conn) -> None:
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS billing_expenses (
            expense_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            lawyer_id TEXT NOT NULL,
            expense_date TEXT NOT NULL,
            expense_type TEXT DEFAULT 'Miscellaneous',
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            billable INTEGER DEFAULT 1,
            billed INTEGER DEFAULT 0,
            invoice_id TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS matter_billing_meta (
            matter_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            client_email TEXT DEFAULT '',
            client_phone TEXT DEFAULT '',
            client_address TEXT DEFAULT '',
            client_gst TEXT DEFAULT '',
            client_company TEXT DEFAULT '',
            matter_number TEXT DEFAULT '',
            assigned_lawyers TEXT DEFAULT '',
            payment_json TEXT DEFAULT '{}',
            updated_at TEXT NOT NULL
        );
        """
    )


def _get_meta(conn, user_id: str, matter_id: str) -> Dict[str, str]:
    row = conn.execute(
        "SELECT client_email, client_phone, client_address, client_gst, client_company, matter_number, assigned_lawyers, payment_json FROM matter_billing_meta WHERE matter_id=? AND user_id=?",
        (matter_id, str(user_id)),
    ).fetchone()
    if not row:
        return {}
    return {
        "client_email": row[0] or "",
        "client_phone": row[1] or "",
        "client_address": row[2] or "",
        "client_gst": row[3] or "",
        "client_company": row[4] or "",
        "matter_number": row[5] or "",
        "assigned_lawyers": row[6] or "",
        "payment_json": row[7] or "{}",
    }


def save_matter_billing_meta(user_id: str, matter_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    ensure_saas_schema()
    conn = connect_data_db()
    _ensure_billing_tables(conn)
    now = _utc()
    existing = conn.execute(
        "SELECT matter_id FROM matter_billing_meta WHERE matter_id=? AND user_id=?",
        (matter_id, str(user_id)),
    ).fetchone()
    vals = (
        fields.get("client_email", ""),
        fields.get("client_phone", ""),
        fields.get("client_address", ""),
        fields.get("client_gst", ""),
        fields.get("client_company", ""),
        fields.get("matter_number", ""),
        fields.get("assigned_lawyers", ""),
        json.dumps(fields.get("payment") or {}),
        now,
    )
    if existing:
        conn.execute(
            """
            UPDATE matter_billing_meta SET
                client_email=?, client_phone=?, client_address=?, client_gst=?,
                client_company=?, matter_number=?, assigned_lawyers=?, payment_json=?, updated_at=?
            WHERE matter_id=? AND user_id=?
            """,
            (*vals, matter_id, str(user_id)),
        )
    else:
        conn.execute(
            """
            INSERT INTO matter_billing_meta
            (matter_id, user_id, client_email, client_phone, client_address, client_gst,
             client_company, matter_number, assigned_lawyers, payment_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (matter_id, str(user_id), *vals),
        )
    conn.commit()
    conn.close()
    return matter_billing_profile(user_id, matter_id)


def matter_billing_profile(user_id: str, matter_id: str, *, username: str = "") -> Dict[str, Any]:
    matter = get_matter(user_id, matter_id)
    if not matter:
        return {"error": "Matter not found"}
    ensure_saas_schema()
    conn = connect_data_db()
    _ensure_billing_tables(conn)
    meta = _get_meta(conn, user_id, matter_id)
    conn.close()

    trust = get_or_create_trust_account(user_id, matter_id) or {}
    invoices = list_invoices(user_id, matter_id=matter_id, limit=200)
    total_billed = round(sum(float(i.get("total") or 0) for i in invoices), 2)
    total_collected = round(
        sum(
            float(i.get("total") or 0) - float(i.get("balance_due") or i.get("total") or 0)
            for i in invoices
            if (i.get("status") or "") in PAID_STATUSES
        ),
        2,
    )
    outstanding = round(
        sum(float(i.get("balance_due") or i.get("total") or 0) for i in invoices if (i.get("status") or "") not in ("PAID", "CANCELLED")),
        2,
    )
    entries = list_time_entries(user_id, matter_id=matter_id, limit=500)
    hours_logged = round(sum(float(e.get("units_logged") or 0) for e in entries), 2)
    unbilled = round(
        sum(float(e.get("line_total") or 0) for e in entries if e.get("invoice_status") == "UNBILLED"),
        2,
    )
    expenses = list_expenses(user_id, matter_id=matter_id)
    expense_total = round(sum(float(e.get("amount") or 0) for e in expenses), 2)

    lead = username or "Counsel"
    assigned = meta.get("assigned_lawyers") or lead

    return {
        "matter_id": matter_id,
        "client_name": matter.get("client_name") or "",
        "client_email": meta.get("client_email", ""),
        "client_phone": meta.get("client_phone", ""),
        "client_address": meta.get("client_address", ""),
        "client_gst": meta.get("client_gst", ""),
        "client_company": meta.get("client_company", ""),
        "matter_name": matter.get("matter_name") or "",
        "matter_number": meta.get("matter_number") or matter_id[:8].upper(),
        "case_number": matter.get("case_number") or "",
        "court_name": matter.get("venue") or "",
        "matter_type": matter.get("matter_type") or matter.get("practice_area") or "",
        "practice_area": matter.get("practice_area") or "",
        "assigned_lawyer": lead,
        "assigned_lawyers": assigned,
        "retainer_balance": trust.get("trust_balance", 0),
        "operating_balance": trust.get("operating_balance", 0),
        "outstanding_balance": outstanding,
        "total_billed": total_billed,
        "total_collected": total_collected,
        "hours_logged": hours_logged,
        "unbilled_amount": unbilled,
        "expense_total": expense_total,
        "invoice_count": len(invoices),
    }


def collections_dashboard(user_id: str) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    _ensure_billing_tables(conn)
    invoices = list_invoices(user_id, limit=500)
    conn.close()
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    prev_month_end = today.replace(day=1) - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1).isoformat()

    total_billed = round(sum(float(i.get("total") or 0) for i in invoices), 2)
    total_collected = round(
        sum(float(i.get("total") or 0) for i in invoices if (i.get("status") or "") in PAID_STATUSES),
        2,
    )
    outstanding = round(
        sum(float(i.get("balance_due") or i.get("total") or 0) for i in invoices if (i.get("status") or "") not in ("PAID", "CANCELLED")),
        2,
    )
    overdue = round(
        sum(
            float(i.get("balance_due") or i.get("total") or 0)
            for i in invoices
            if (i.get("status") or "") == "OVERDUE"
            or (
                (i.get("due_date") or "") < today.isoformat()
                and (i.get("status") or "") not in ("PAID", "CANCELLED", "DRAFT")
            )
        ),
        2,
    )
    current_month = round(
        sum(
            float(i.get("total") or 0)
            for i in invoices
            if (i.get("invoice_date") or i.get("created_at", ""))[:10] >= month_start
            and (i.get("status") or "") in COLLECTED_STATUSES
        ),
        2,
    )
    last_month = round(
        sum(
            float(i.get("total") or 0)
            for i in invoices
            if prev_month_start <= (i.get("invoice_date") or i.get("created_at", ""))[:10] <= prev_month_end.isoformat()
        ),
        2,
    )
    collection_rate = round((total_collected / total_billed * 100) if total_billed > 0 else 0, 1)
    base = billing_summary(user_id)
    return {
        **base,
        "total_billed": total_billed,
        "total_collected": total_collected,
        "outstanding_receivables": outstanding,
        "overdue_receivables": overdue,
        "current_month_revenue": current_month,
        "last_month_revenue": last_month,
        "collection_rate_pct": collection_rate,
    }


def matter_financial_summary(user_id: str, matter_id: str) -> Dict[str, Any]:
    profile = matter_billing_profile(user_id, matter_id)
    if profile.get("error"):
        return profile
    entries = list_time_entries(user_id, matter_id=matter_id, limit=500)
    expenses = list_expenses(user_id, matter_id=matter_id)
    billed = profile["total_billed"]
    collected = profile["total_collected"]
    expense_amt = profile["expense_total"]
    hours_cost = round(sum(float(e.get("line_total") or 0) for e in entries), 2)
    profitability = round(collected - expense_amt, 2)
    return {
        **profile,
        "matter_value": hours_cost + expense_amt,
        "amount_billed": billed,
        "amount_collected": collected,
        "expenses": expense_amt,
        "trust_balance": profile.get("retainer_balance", 0),
        "profitability": profitability,
    }


def list_expenses(user_id: str, *, matter_id: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    _ensure_billing_tables(conn)
    q = "SELECT expense_id, matter_id, expense_date, expense_type, description, amount, billable, billed, invoice_id, created_at FROM billing_expenses WHERE lawyer_id=?"
    params: List[Any] = [str(user_id)]
    if matter_id:
        q += " AND matter_id=?"
        params.append(matter_id)
    q += " ORDER BY expense_date DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        {
            "expense_id": r[0],
            "matter_id": r[1],
            "date": r[2],
            "expense_type": r[3],
            "description": r[4],
            "amount": round(float(r[5]), 2),
            "billable": bool(r[6]),
            "billed": bool(r[7]),
            "invoice_id": r[8] or "",
            "created_at": r[9],
        }
        for r in rows
    ]


def create_expense(
    user_id: str,
    *,
    matter_id: str,
    expense_date: str,
    expense_type: str,
    description: str,
    amount: float,
    billable: bool = True,
) -> Dict[str, Any]:
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    eid = str(uuid.uuid4())
    now = _utc()
    etype = expense_type if expense_type in EXPENSE_TYPES else "Miscellaneous"
    ensure_saas_schema()
    conn = connect_data_db()
    _ensure_billing_tables(conn)
    conn.execute(
        """
        INSERT INTO billing_expenses
        (expense_id, matter_id, lawyer_id, expense_date, expense_type, description, amount, billable, billed, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (eid, matter_id, str(user_id), expense_date or _utc()[:10], etype, description.strip(), abs(float(amount)), 1 if billable else 0, now, now),
    )
    conn.commit()
    conn.close()
    return {"expense_id": eid, "amount": round(abs(float(amount)), 2)}


def delete_expense(user_id: str, expense_id: str) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    _ensure_billing_tables(conn)
    conn.execute(
        "DELETE FROM billing_expenses WHERE expense_id=? AND lawyer_id=?",
        (expense_id, str(user_id)),
    )
    conn.commit()
    conn.close()
    return {"deleted": True}


def update_time_entry(
    user_id: str,
    record_id: str,
    *,
    raw_activity: Optional[str] = None,
    units_logged: Optional[float] = None,
    rate_per_unit: Optional[float] = None,
    narrative_description: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT matter_id, invoice_status, raw_activity, units_logged, rate_per_unit FROM financial_records WHERE record_id=? AND lawyer_id=?",
        (record_id, str(user_id)),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Entry not found"}
    if row[1] != "UNBILLED":
        conn.close()
        return {"error": "Cannot edit billed entry"}
    matter_id = row[0]
    raw = raw_activity if raw_activity is not None else row[2]
    units = units_logged if units_logged is not None else float(row[3])
    rate = rate_per_unit if rate_per_unit is not None else float(row[4])
    narrative = narrative_description
    if narrative is None and raw_activity is not None:
        matter = get_matter(user_id, matter_id) or {}
        ctx = f"{matter.get('practice_area', '')} {matter.get('matter_name', '')}"
        narrative = polish_billing_narrative(user_id, raw, units=units, matter_context=ctx)
    elif narrative is None:
        narrative = conn.execute(
            "SELECT narrative_description FROM financial_records WHERE record_id=?",
            (record_id,),
        ).fetchone()[0]
    now = _utc()
    conn.execute(
        """
        UPDATE financial_records SET raw_activity=?, units_logged=?, rate_per_unit=?,
            narrative_description=?, updated_at=?
        WHERE record_id=? AND lawyer_id=?
        """,
        (raw[:500], units, rate, narrative, now, record_id, str(user_id)),
    )
    conn.commit()
    conn.close()
    return {"record_id": record_id, "line_total": round(units * rate, 2)}


def delete_time_entry(user_id: str, record_id: str) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT invoice_status FROM financial_records WHERE record_id=? AND lawyer_id=?",
        (record_id, str(user_id)),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Entry not found"}
    if row[0] != "UNBILLED":
        conn.close()
        return {"error": "Cannot delete billed entry"}
    conn.execute("DELETE FROM financial_records WHERE record_id=? AND lawyer_id=?", (record_id, str(user_id)))
    conn.commit()
    conn.close()
    return {"deleted": True}


def duplicate_time_entry(user_id: str, record_id: str) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT matter_id, raw_activity, units_logged, rate_per_unit, billing_type
        FROM financial_records WHERE record_id=? AND lawyer_id=?
        """,
        (record_id, str(user_id)),
    ).fetchone()
    conn.close()
    if not row:
        return {"error": "Entry not found"}
    return log_time_entry(
        user_id,
        matter_id=row[0],
        raw_activity=row[1],
        units_logged=float(row[2]),
        rate_per_unit=float(row[3]),
        billing_type=row[4] or "HOURLY",
    )


def bulk_import_time_entries(user_id: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    created = []
    errors = []
    for i, e in enumerate(entries):
        out = log_time_entry(
            user_id,
            matter_id=e.get("matter_id", ""),
            raw_activity=e.get("raw_activity", e.get("description", "Legal services")),
            units_logged=float(e.get("units_logged", e.get("hours", 1))),
            rate_per_unit=float(e.get("rate_per_unit", e.get("rate", 1000))),
            billing_type=e.get("billing_type", "HOURLY"),
        )
        if out.get("error"):
            errors.append({"index": i, "error": out["error"]})
        else:
            created.append(out.get("record_id"))
    return {"created": len(created), "record_ids": created, "errors": errors}


def billing_workspace(user_id: str, matter_id: str, *, username: str = "") -> Dict[str, Any]:
    """Single payload for billing page load."""
    profile = matter_billing_profile(user_id, matter_id, username=username) if matter_id else {}
    return {
        "summary": collections_dashboard(user_id),
        "profile": profile,
        "entries": list_time_entries(user_id, matter_id=matter_id, limit=200) if matter_id else list_time_entries(user_id, limit=50),
        "expenses": list_expenses(user_id, matter_id=matter_id) if matter_id else [],
        "invoices": list_invoices(user_id, matter_id=matter_id, limit=50) if matter_id else list_invoices(user_id, limit=50),
        "matter_financials": matter_financial_summary(user_id, matter_id) if matter_id else {},
        "expense_types": list(EXPENSE_TYPES),
    }


def billing_reports(user_id: str, report: str = "summary") -> Dict[str, Any]:
    invoices = list_invoices(user_id, limit=500)
    entries = list_time_entries(user_id, limit=500)
    expenses = list_expenses(user_id, limit=500)
    if report == "revenue_by_matter":
        by_matter: Dict[str, float] = {}
        for inv in invoices:
            mid = inv.get("matter_id") or "unknown"
            by_matter[mid] = by_matter.get(mid, 0) + float(inv.get("total") or 0)
        return {"report": report, "rows": [{"matter_id": k, "revenue_inr": round(v, 2)} for k, v in sorted(by_matter.items(), key=lambda x: -x[1])]}
    if report == "outstanding":
        rows = [
            {
                "invoice_number": i.get("invoice_number"),
                "client_name": i.get("client_name"),
                "balance_due": i.get("balance_due", i.get("total")),
                "status": i.get("status"),
                "due_date": i.get("due_date"),
            }
            for i in invoices
            if (i.get("status") or "") not in ("PAID", "CANCELLED")
        ]
        return {"report": report, "rows": rows}
    if report == "expenses":
        return {"report": report, "rows": expenses}
    if report == "gst":
        rows = [
            {
                "invoice_number": i.get("invoice_number"),
                "tax_amount": i.get("tax_amount"),
                "total": i.get("total"),
                "invoice_date": i.get("invoice_date"),
            }
            for i in invoices
        ]
        return {"report": report, "rows": rows, "total_gst": round(sum(float(i.get("tax_amount") or 0) for i in invoices), 2)}
    if report == "collections":
        return {"report": report, **collections_dashboard(user_id)}
    if report == "trust_ledger":
        return {"report": report, "note": "Use trust transactions per matter from /trust API"}
    return {
        "report": "summary",
        "collections": collections_dashboard(user_id),
        "invoice_count": len(invoices),
        "time_entries": len(entries),
        "expense_count": len(expenses),
    }
