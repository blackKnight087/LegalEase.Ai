"""PostgreSQL DDL for practice, CRM, billing, discovery, ops (Day 5 rest tables)."""
from __future__ import annotations

import logging

logger = logging.getLogger("legalease.pg_rest")

PG_REST_DDL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS suspended INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms_at TEXT DEFAULT ''",
    """
    CREATE TABLE IF NOT EXISTS knowledge_base_status (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        total_documents INTEGER NOT NULL,
        total_chunks INTEGER NOT NULL,
        last_updated TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        uploader_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        saved_path TEXT NOT NULL,
        pages INTEGER NOT NULL,
        uploaded_at TEXT NOT NULL,
        matter_id TEXT DEFAULT '',
        content_hash TEXT DEFAULT '',
        privileged INTEGER DEFAULT 0,
        doc_version INTEGER DEFAULT 1,
        index_status TEXT DEFAULT '',
        org_id TEXT DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documents_uploader ON documents(uploader_id)",
    "CREATE INDEX IF NOT EXISTS idx_documents_uploader_hash ON documents(uploader_id, content_hash)",
    """
    CREATE TABLE IF NOT EXISTS email_verify_tokens (
        token_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        verified_at TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_email_verify_user ON email_verify_tokens(user_id)",
    """
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        token_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        used_at TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_reset_user ON password_reset_tokens(user_id)",
    """
    CREATE TABLE IF NOT EXISTS user_onboarding (
        user_id TEXT PRIMARY KEY,
        dismissed INTEGER NOT NULL DEFAULT 0,
        completed_at TEXT DEFAULT '',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id TEXT PRIMARY KEY,
        user_id TEXT DEFAULT '',
        action TEXT NOT NULL,
        detail TEXT DEFAULT '',
        ip_address TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_events(user_id)",
    """
    CREATE TABLE IF NOT EXISTS ml_jobs (
        job_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        job_type TEXT NOT NULL,
        payload_json TEXT DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'QUEUED',
        progress INTEGER DEFAULT 0,
        result_json TEXT DEFAULT '',
        error_message TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ml_jobs_status ON ml_jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_ml_jobs_user ON ml_jobs(user_id)",
    """
    CREATE TABLE IF NOT EXISTS matter_notes (
        note_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        author_id TEXT NOT NULL,
        raw_content TEXT NOT NULL,
        anonymized_content TEXT DEFAULT '',
        timestamp TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_matter_notes_mid ON matter_notes(matter_id)",
    """
    CREATE TABLE IF NOT EXISTS document_templates (
        template_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT '',
        template_name TEXT NOT NULL,
        practice_area TEXT NOT NULL DEFAULT 'General',
        raw_markdown_structure TEXT NOT NULL,
        variable_json_map TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS clause_library (
        clause_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT '',
        clause_tag TEXT NOT NULL,
        practice_area TEXT NOT NULL DEFAULT 'General',
        clause_text_content TEXT NOT NULL,
        confidence_weight REAL DEFAULT 1.0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspace_drafts (
        draft_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        matter_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL,
        document_type TEXT NOT NULL DEFAULT 'custom',
        status TEXT NOT NULL DEFAULT 'draft',
        content TEXT NOT NULL DEFAULT '',
        parties_json TEXT NOT NULL DEFAULT '{}',
        jurisdiction TEXT NOT NULL DEFAULT '',
        objectives TEXT NOT NULL DEFAULT '',
        instructions TEXT NOT NULL DEFAULT '',
        pinned INTEGER NOT NULL DEFAULT 0,
        version_count INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_workspace_drafts_user ON workspace_drafts(user_id)",
    """
    CREATE TABLE IF NOT EXISTS workspace_draft_versions (
        version_id TEXT PRIMARY KEY,
        draft_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        version_number INTEGER NOT NULL,
        content TEXT NOT NULL,
        change_summary TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_workspace_versions_draft ON workspace_draft_versions(draft_id)",
    """
    CREATE TABLE IF NOT EXISTS workspace_draft_comments (
        comment_id TEXT PRIMARY KEY,
        draft_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        author_name TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_timeline (
        event_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        event_date TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        event_type TEXT DEFAULT 'general',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_hearings (
        hearing_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        hearing_date TEXT NOT NULL,
        court_name TEXT DEFAULT '',
        purpose TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'scheduled',
        created_at TEXT NOT NULL,
        judge TEXT DEFAULT '',
        arguments TEXT DEFAULT '',
        observations TEXT DEFAULT '',
        next_hearing_date TEXT DEFAULT '',
        summary TEXT DEFAULT '',
        prosecution_argument TEXT DEFAULT '',
        defense_argument TEXT DEFAULT '',
        document_source TEXT DEFAULT '',
        page_number TEXT DEFAULT '',
        source TEXT DEFAULT 'manual'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_tasks (
        task_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        title TEXT NOT NULL,
        due_date TEXT DEFAULT '',
        status TEXT DEFAULT 'open',
        assignee TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        task_source TEXT DEFAULT 'manual'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_deadlines (
        deadline_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        title TEXT NOT NULL,
        due_date TEXT NOT NULL,
        deadline_type TEXT DEFAULT 'filing',
        status TEXT DEFAULT 'pending',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_entities (
        entity_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        entity_type TEXT NOT NULL DEFAULT 'person',
        label TEXT NOT NULL,
        source_doc_id TEXT DEFAULT '',
        confidence REAL DEFAULT 0.8,
        metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_evidence (
        evidence_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'document',
        document_id TEXT DEFAULT '',
        title TEXT NOT NULL,
        tags TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        strength TEXT DEFAULT 'unknown',
        created_at TEXT NOT NULL,
        description TEXT DEFAULT '',
        source_document TEXT DEFAULT '',
        page_number TEXT DEFAULT '',
        importance TEXT DEFAULT '',
        person_related TEXT DEFAULT '',
        evidence_type TEXT DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_contradictions (
        contradiction_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        contradiction_type TEXT NOT NULL DEFAULT 'statement',
        topic TEXT NOT NULL,
        statement_a TEXT DEFAULT '',
        statement_b TEXT DEFAULT '',
        note TEXT DEFAULT '',
        confidence REAL DEFAULT 0.7,
        source_hint TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_intel_status (
        matter_id TEXT PRIMARY KEY,
        stage TEXT NOT NULL DEFAULT 'idle',
        message TEXT DEFAULT '',
        progress_json TEXT DEFAULT '{}',
        last_error TEXT DEFAULT '',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_members (
        member_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'viewer',
        created_at TEXT NOT NULL,
        UNIQUE(matter_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_timeline_suggestions (
        suggestion_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        event_date TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        source_doc_id TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_audit_log (
        log_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        detail TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_lexicon_cache (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        raw_sig TEXT NOT NULL,
        raw_sample TEXT NOT NULL,
        polished_narrative TEXT NOT NULL,
        hit_count INTEGER DEFAULT 1,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, raw_sig)
    )
    """,
    """
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
    )
    """,
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS invoice_number TEXT DEFAULT ''",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS payload_json TEXT DEFAULT '{}'",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS invoice_date TEXT DEFAULT ''",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS due_date TEXT DEFAULT ''",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS balance_due REAL DEFAULT 0",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS updated_at TEXT DEFAULT ''",
    "ALTER TABLE crm_leads ADD COLUMN IF NOT EXISTS org_id TEXT DEFAULT ''",
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crm_intent_corrections (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        raw_sig TEXT NOT NULL,
        original_intent TEXT,
        corrected_intent TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, raw_sig)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ediscovery_batches (
        batch_id TEXT PRIMARY KEY,
        matter_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        batch_title TEXT NOT NULL,
        total_documents_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
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
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS discovery_tag_weights (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        matter_id TEXT NOT NULL,
        tag TEXT NOT NULL,
        weight_delta REAL DEFAULT 0.0,
        hit_count INTEGER DEFAULT 1,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, matter_id, tag)
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trust_transactions (
        txn_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        ledger_type TEXT NOT NULL,
        txn_type TEXT NOT NULL,
        amount REAL NOT NULL,
        narrative TEXT NOT NULL,
        reference_id TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS client_portal_access (
        access_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        matter_id TEXT NOT NULL,
        client_email TEXT NOT NULL,
        access_token TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
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
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS legal_watchlist (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        matter_id TEXT DEFAULT '',
        watch_type TEXT NOT NULL,
        label TEXT NOT NULL,
        query TEXT NOT NULL,
        active INTEGER DEFAULT 1,
        last_checked TEXT,
        last_result TEXT,
        created_at TEXT
    )
    """,
]


def ensure_pg_rest_schema() -> None:
    from backend.app.core.database import get_database_url, is_postgres

    if not is_postgres():
        return
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError("psycopg2-binary required for PostgreSQL") from exc

    conn = psycopg2.connect(get_database_url())
    conn.autocommit = True
    cur = conn.cursor()
    for ddl in PG_REST_DDL:
        try:
            cur.execute(ddl)
        except Exception as exc:
            logger.warning("PG rest DDL skipped: %s — %s", ddl[:60], exc)
    for table, col, typ in (
        ("discovery_items", "file_type", "TEXT DEFAULT ''"),
        ("discovery_items", "file_hash", "TEXT DEFAULT ''"),
        ("discovery_items", "metadata_json", "TEXT DEFAULT '{}'"),
        ("discovery_items", "entities_json", "TEXT DEFAULT '{}'"),
        ("discovery_items", "timeline_json", "TEXT DEFAULT '[]'"),
        ("discovery_items", "statutes_json", "TEXT DEFAULT '[]'"),
        ("discovery_items", "privilege_json", "TEXT DEFAULT '{}'"),
        ("discovery_items", "risks_json", "TEXT DEFAULT '[]'"),
        ("discovery_items", "category", "TEXT DEFAULT ''"),
        ("discovery_items", "extraction_method", "TEXT DEFAULT ''"),
    ):
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")
        except Exception:
            pass
    cur.close()
    conn.close()
    logger.info("PostgreSQL rest schema ensured")
