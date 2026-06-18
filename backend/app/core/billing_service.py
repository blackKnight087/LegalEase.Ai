"""
Phase 2 — Time tracking, professional billing narratives, invoices (Indian practice).
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import get_matter
from backend.app.core.saas_schema import ensure_saas_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sig(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", (text or "").lower()).encode()).hexdigest()[:24]


# Statute-aware billing narrative templates (audit-style)
_NARRATIVE_PATTERNS = [
    (
        re.compile(r"\b(?:section|sec\.?)\s*(\d{1,4}[a-z]?)\b", re.I),
        lambda m, hrs: (
            f"Devoted {hrs:.2f} hours to statutory analysis and case-law review "
            f"concerning Section {m.group(1).upper()} of the applicable penal/statutory code."
        ),
    ),
    (
        re.compile(r"\bbail\b", re.I),
        lambda _m, hrs: (
            f"Spent {hrs:.2f} hours evaluating bail eligibility, preparing submissions, "
            f"and reviewing restrictions under the BNSS/CrPC framework."
        ),
    ),
    (
        re.compile(r"\b(?:contract|breach|vendor)\b", re.I),
        lambda _m, hrs: (
            f"Allocated {hrs:.2f} hours to contract breach analysis, correspondence review, "
            f"and remedies under the Indian Contract Act, 1872."
        ),
    ),
    (
        re.compile(r"\b(?:research|precedent|judgment)\b", re.I),
        lambda _m, hrs: (
            f"Conducted {hrs:.2f} hours of legal research including precedent mapping "
            f"and preparation of strategic memoranda."
        ),
    ),
    (
        re.compile(r"\b(?:hearing|court|argument)\b", re.I),
        lambda _m, hrs: (
            f"Attended court proceedings and related preparation for {hrs:.2f} hours, "
            f"including drafting of oral submissions and case diary review."
        ),
    ),
]


def _hours_str(units: float) -> str:
    return f"{units:.2f}"


def polish_billing_narrative(
    user_id: str,
    raw_activity: str,
    *,
    units: float = 1.0,
    matter_context: str = "",
) -> str:
    """Convert raw activity log into professional invoice narrative."""
    ensure_saas_schema()
    raw = (raw_activity or "").strip()
    if not raw:
        return "Professional legal services rendered as per retainer."

    sig = _sig(raw)
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT polished_narrative FROM financial_lexicon_cache
        WHERE user_id = ? AND raw_sig = ?
        """,
        (str(user_id), sig),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE financial_lexicon_cache SET hit_count = hit_count + 1, updated_at = ?
            WHERE user_id = ? AND raw_sig = ?
            """,
            (_utc(), str(user_id), sig),
        )
        conn.commit()
        conn.close()
        return row[0]

    hrs = max(0.25, float(units))
    narrative = None
    blob = f"{raw} {matter_context}"
    for pat, fn in _NARRATIVE_PATTERNS:
        m = pat.search(blob)
        if m:
            narrative = fn(m, hrs)
            break
    if not narrative:
        narrative = (
            f"Professional legal services: {raw[:120]}. "
            f"Time recorded: {hrs:.2f} hours at counsel rates."
        )
    narrative = narrative[0].upper() + narrative[1:] if narrative else narrative
    conn.execute(
        """
        INSERT INTO financial_lexicon_cache (user_id, raw_sig, raw_sample, polished_narrative, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, raw_sig) DO UPDATE SET
            polished_narrative = excluded.polished_narrative,
            hit_count = financial_lexicon_cache.hit_count + 1,
            updated_at = excluded.updated_at
        """,
        (str(user_id), sig, raw[:400], narrative, _utc()),
    )
    conn.commit()
    conn.close()
    return narrative


def record_lexicon_correction(
    user_id: str,
    raw_activity: str,
    polished: str,
) -> Dict[str, Any]:
    """Lawyer-edited narrative — strongest learning signal for billing."""
    ensure_saas_schema()
    sig = _sig(raw_activity)
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO financial_lexicon_cache (user_id, raw_sig, raw_sample, polished_narrative, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, raw_sig) DO UPDATE SET
            polished_narrative = excluded.polished_narrative,
            hit_count = financial_lexicon_cache.hit_count + 2,
            updated_at = excluded.updated_at
        """,
        (str(user_id), sig, raw_activity[:400], polished.strip(), _utc()),
    )
    conn.commit()
    conn.close()
    return {"recorded": True, "raw_sig": sig}


def log_time_entry(
    user_id: str,
    *,
    matter_id: str,
    raw_activity: str,
    units_logged: float,
    rate_per_unit: float,
    billing_type: str = "HOURLY",
) -> Dict[str, Any]:
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    matter = get_matter(user_id, matter_id) or {}
    ctx = f"{matter.get('practice_area', '')} {matter.get('matter_name', '')}"
    narrative = polish_billing_narrative(
        user_id, raw_activity, units=units_logged, matter_context=ctx
    )
    rid = str(uuid.uuid4())
    now = _utc()
    amount = round(units_logged * rate_per_unit, 2)
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO financial_records
        (record_id, matter_id, lawyer_id, billing_type, units_logged, rate_per_unit,
         narrative_description, raw_activity, invoice_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'UNBILLED', ?, ?)
        """,
        (
            rid,
            matter_id,
            str(user_id),
            billing_type.upper(),
            units_logged,
            rate_per_unit,
            narrative,
            raw_activity[:500],
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "record_id": rid,
        "matter_id": matter_id,
        "narrative_description": narrative,
        "amount": amount,
        "units_logged": units_logged,
        "rate_per_unit": rate_per_unit,
    }


def list_time_entries(
    user_id: str,
    *,
    matter_id: str = "",
    invoice_status: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    q = """
        SELECT r.record_id, r.matter_id, r.billing_type, r.units_logged, r.rate_per_unit,
               r.narrative_description, r.raw_activity, r.invoice_status, r.created_at,
               m.matter_name
        FROM financial_records r
        LEFT JOIN matters m ON m.matter_id = r.matter_id
        WHERE r.lawyer_id = ?
    """
    params: List[Any] = [str(user_id)]
    if matter_id:
        q += " AND r.matter_id = ?"
        params.append(matter_id)
    if invoice_status:
        q += " AND r.invoice_status = ?"
        params.append(invoice_status)
    q += " ORDER BY r.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        {
            "record_id": r[0],
            "matter_id": r[1],
            "billing_type": r[2],
            "units_logged": r[3],
            "rate_per_unit": r[4],
            "narrative_description": r[5],
            "raw_activity": r[6],
            "invoice_status": r[7],
            "created_at": r[8],
            "matter_name": r[9] or "",
            "line_total": round(float(r[3]) * float(r[4]), 2),
        }
        for r in rows
    ]


def generate_invoice(
    user_id: str,
    matter_id: str,
    *,
    client_name: str = "",
    tax_rate: float = 0.18,
    record_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    entries = list_time_entries(user_id, matter_id=matter_id, invoice_status="UNBILLED")
    if record_ids:
        ids = set(record_ids)
        entries = [e for e in entries if e["record_id"] in ids]
    if not entries:
        return {"error": "No unbilled entries for this matter"}

    matter = get_matter(user_id, matter_id) or {}
    client = client_name or matter.get("client_name") or "Client"
    line_items = []
    subtotal = 0.0
    for e in entries:
        subtotal += e["line_total"]
        line_items.append(
            {
                "record_id": e["record_id"],
                "description": e["narrative_description"],
                "units": e["units_logged"],
                "rate": e["rate_per_unit"],
                "amount": e["line_total"],
            }
        )
    tax_amount = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax_amount, 2)
    iid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO invoices
        (invoice_id, matter_id, lawyer_id, client_name, line_items_json,
         subtotal, tax_rate, tax_amount, total, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ISSUED', ?)
        """,
        (
            iid,
            matter_id,
            str(user_id),
            client,
            json.dumps(line_items),
            subtotal,
            tax_rate,
            tax_amount,
            total,
            now,
        ),
    )
    for e in entries:
        conn.execute(
            """
            UPDATE financial_records SET invoice_status = 'BILLED', updated_at = ?
            WHERE record_id = ? AND lawyer_id = ?
            """,
            (now, e["record_id"], str(user_id)),
        )
    conn.commit()
    conn.close()
    return {
        "invoice_id": iid,
        "matter_id": matter_id,
        "client_name": client,
        "line_items": line_items,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "currency": "INR",
        "status": "ISSUED",
    }


def billing_summary(user_id: str) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    unbilled = conn.execute(
        """
        SELECT COALESCE(SUM(units_logged * rate_per_unit), 0), COUNT(*)
        FROM financial_records WHERE lawyer_id = ? AND invoice_status = 'UNBILLED'
        """,
        (str(user_id),),
    ).fetchone()
    billed = conn.execute(
        """
        SELECT COALESCE(SUM(total), 0), COUNT(*)
        FROM invoices WHERE lawyer_id = ?
        """,
        (str(user_id),),
    ).fetchone()
    conn.close()
    return {
        "unbilled_amount_inr": round(float(unbilled[0]), 2),
        "unbilled_entries": int(unbilled[1]),
        "invoiced_total_inr": round(float(billed[0]), 2),
        "invoice_count": int(billed[1]),
    }
