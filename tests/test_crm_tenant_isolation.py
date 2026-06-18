"""CRM must not leak leads across users or orgs."""
from __future__ import annotations

import pytest

from backend.app.core.crm_service import create_lead, get_lead, list_leads
from backend.app.core.org_service import create_org_for_user
from backend.app.core.saas_schema import ensure_saas_schema


@pytest.fixture(autouse=True)
def _schema():
    ensure_saas_schema()


def test_crm_leads_isolated_between_users():
    org_a = create_org_for_user("crm-user-a", "alice")
    org_b = create_org_for_user("crm-user-b", "bob")
    assert org_a != org_b

    lead_a = create_lead(
        "crm-user-a",
        prospect_name="Alice Client",
        contact_email="alice@example.com",
        raw_intake_query="Vendor fraud in Kolkata under IPC cheating section.",
    )
    assert lead_a.get("lead_id")

    assert get_lead("crm-user-b", lead_a["lead_id"]) is None
    assert all(l["lead_id"] != lead_a["lead_id"] for l in list_leads("crm-user-b"))


def test_crm_orphan_empty_user_id_not_visible():
    from backend.app.core.crm_service import _migrate_crm_org_scope
    from backend.app.core.database import connect_data_db

    _migrate_crm_org_scope()
    conn = connect_data_db()
    try:
        conn.execute("DELETE FROM crm_leads WHERE lead_id = 'orphan-lead'")
        conn.execute(
            """
            INSERT INTO crm_leads
            (lead_id, user_id, org_id, prospect_name, contact_email, contact_phone,
             raw_intake_query, calculated_intent, extracted_params_json,
             pipeline_stage, assigned_attorney_id, follow_up_draft, created_at, updated_at)
            VALUES ('orphan-lead', '', '', 'Ghost', 'ghost@test.com', '', 'test query long enough', '', '{}',
                    'NEW_INTAKE', '', '', '2020-01-01', '2020-01-01')
            """
        )
        conn.commit()
    finally:
        conn.close()

    create_org_for_user("crm-user-c", "carol")
    assert get_lead("crm-user-c", "orphan-lead") is None
    assert not any(l["lead_id"] == "orphan-lead" for l in list_leads("crm-user-c"))
