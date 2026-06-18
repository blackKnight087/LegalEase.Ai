"""
Phases 2–4 enterprise SaaS schema — billing, CRM intake, e-discovery, research logging.
"""
from __future__ import annotations

import sqlite3

from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import use_postgres_legacy
from backend.app.core.practice_schema import ensure_practice_schema


def ensure_saas_schema() -> None:
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema
        from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

        ensure_pg_core_schema()
        ensure_pg_rest_schema()
        return
    ensure_practice_schema()
    conn = connect_data_db()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS financial_records (
            record_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            lawyer_id TEXT NOT NULL,
            billing_type TEXT NOT NULL,
            units_logged REAL NOT NULL,
            rate_per_unit REAL NOT NULL,
            narrative_description TEXT NOT NULL,
            raw_activity TEXT DEFAULT '',
            invoice_status TEXT DEFAULT 'UNBILLED',
            currency TEXT DEFAULT 'INR',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fin_matter ON financial_records(matter_id);
        CREATE INDEX IF NOT EXISTS idx_fin_lawyer ON financial_records(lawyer_id);

        CREATE TABLE IF NOT EXISTS financial_lexicon_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            raw_sig TEXT NOT NULL,
            raw_sample TEXT NOT NULL,
            polished_narrative TEXT NOT NULL,
            hit_count INTEGER DEFAULT 1,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, raw_sig)
        );

        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            lawyer_id TEXT NOT NULL,
            client_name TEXT DEFAULT '',
            line_items_json TEXT NOT NULL,
            subtotal REAL NOT NULL,
            tax_rate REAL DEFAULT 0.18,
            tax_amount REAL NOT NULL,
            total REAL NOT NULL,
            status TEXT DEFAULT 'DRAFT',
            created_at TEXT NOT NULL
        );

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
        CREATE INDEX IF NOT EXISTS idx_bexp_matter ON billing_expenses(matter_id);
        CREATE INDEX IF NOT EXISTS idx_bexp_lawyer ON billing_expenses(lawyer_id);

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

        CREATE TABLE IF NOT EXISTS crm_leads (
            lead_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            org_id TEXT DEFAULT '',
            prospect_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            contact_phone TEXT DEFAULT '',
            raw_intake_query TEXT NOT NULL,
            calculated_intent TEXT DEFAULT '',
            extracted_params_json TEXT DEFAULT '{}',
            pipeline_stage TEXT DEFAULT 'NEW_INTAKE',
            assigned_attorney_id TEXT DEFAULT '',
            follow_up_draft TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_crm_stage ON crm_leads(pipeline_stage);

        CREATE TABLE IF NOT EXISTS crm_intent_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            raw_sig TEXT NOT NULL,
            original_intent TEXT,
            corrected_intent TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, raw_sig)
        );

        CREATE TABLE IF NOT EXISTS ediscovery_batches (
            batch_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            batch_title TEXT NOT NULL,
            total_documents_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS discovery_items (
            item_id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            source_identifier TEXT NOT NULL,
            content_payload TEXT NOT NULL,
            assigned_tags TEXT DEFAULT '',
            relevance_score REAL DEFAULT 0.5,
            classification TEXT DEFAULT 'UNREVIEWED',
            rationale TEXT DEFAULT '',
            reviewed_status INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES ediscovery_batches(batch_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_disc_batch ON discovery_items(batch_id);

        CREATE TABLE IF NOT EXISTS discovery_tag_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            weight_delta REAL DEFAULT 0.0,
            hit_count INTEGER DEFAULT 1,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, matter_id, tag)
        );

        CREATE TABLE IF NOT EXISTS research_queries (
            query_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT DEFAULT '',
            raw_search_term TEXT NOT NULL,
            expanded_search_terms TEXT NOT NULL,
            selected_mode TEXT NOT NULL,
            retrieval_confidence REAL DEFAULT 0.0,
            feedback_signal INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_research_user ON research_queries(user_id);

        CREATE TABLE IF NOT EXISTS trust_accounts (
            account_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            client_name TEXT DEFAULT '',
            operating_balance REAL DEFAULT 0.0,
            trust_balance REAL DEFAULT 0.0,
            currency TEXT DEFAULT 'INR',
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, matter_id)
        );

        CREATE TABLE IF NOT EXISTS trust_transactions (
            txn_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            ledger_type TEXT NOT NULL,
            txn_type TEXT NOT NULL,
            amount REAL NOT NULL,
            narrative TEXT NOT NULL,
            reference_id TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES trust_accounts(account_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_trust_txn_acct ON trust_transactions(account_id);

        CREATE TABLE IF NOT EXISTS client_portal_access (
            access_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            client_email TEXT NOT NULL,
            access_token TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_portal_token ON client_portal_access(access_token);

        CREATE TABLE IF NOT EXISTS signing_requests (
            request_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT DEFAULT '',
            document_title TEXT NOT NULL,
            document_body TEXT NOT NULL,
            signer_name TEXT NOT NULL,
            signer_email TEXT NOT NULL,
            provider TEXT DEFAULT 'mock',
            external_id TEXT DEFAULT '',
            status TEXT DEFAULT 'PENDING',
            sign_url TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ediscovery_jobs (
            job_id TEXT PRIMARY KEY,
            batch_id TEXT DEFAULT '',
            user_id TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            batch_title TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT DEFAULT 'QUEUED',
            progress INTEGER DEFAULT 0,
            result_json TEXT DEFAULT '',
            error_message TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_edisc_job_status ON ediscovery_jobs(status);
        """
    )
    icols = {row[1] for row in c.execute("PRAGMA table_info(invoices)").fetchall()}
    for col, ddl in (
        ("invoice_number", "ALTER TABLE invoices ADD COLUMN invoice_number TEXT DEFAULT ''"),
        ("payload_json", "ALTER TABLE invoices ADD COLUMN payload_json TEXT DEFAULT '{}'"),
        ("invoice_date", "ALTER TABLE invoices ADD COLUMN invoice_date TEXT DEFAULT ''"),
        ("due_date", "ALTER TABLE invoices ADD COLUMN due_date TEXT DEFAULT ''"),
        ("balance_due", "ALTER TABLE invoices ADD COLUMN balance_due REAL DEFAULT 0"),
        ("updated_at", "ALTER TABLE invoices ADD COLUMN updated_at TEXT DEFAULT ''"),
    ):
        if col not in icols:
            c.execute(ddl)
    dcols = {row[1] for row in c.execute("PRAGMA table_info(discovery_items)").fetchall()}
    for col, ddl in (
        ("file_type", "ALTER TABLE discovery_items ADD COLUMN file_type TEXT DEFAULT ''"),
        ("file_hash", "ALTER TABLE discovery_items ADD COLUMN file_hash TEXT DEFAULT ''"),
        ("metadata_json", "ALTER TABLE discovery_items ADD COLUMN metadata_json TEXT DEFAULT '{}'"),
        ("entities_json", "ALTER TABLE discovery_items ADD COLUMN entities_json TEXT DEFAULT '{}'"),
        ("timeline_json", "ALTER TABLE discovery_items ADD COLUMN timeline_json TEXT DEFAULT '[]'"),
        ("statutes_json", "ALTER TABLE discovery_items ADD COLUMN statutes_json TEXT DEFAULT '[]'"),
        ("privilege_json", "ALTER TABLE discovery_items ADD COLUMN privilege_json TEXT DEFAULT '{}'"),
        ("risks_json", "ALTER TABLE discovery_items ADD COLUMN risks_json TEXT DEFAULT '[]'"),
        ("category", "ALTER TABLE discovery_items ADD COLUMN category TEXT DEFAULT ''"),
        ("extraction_method", "ALTER TABLE discovery_items ADD COLUMN extraction_method TEXT DEFAULT ''"),
    ):
        if col not in dcols:
            c.execute(ddl)
    conn.commit()
    conn.close()
