"""PostgreSQL DDL for legacy core tables (mirrors SQLite schemas)."""
from __future__ import annotations

import logging

PG_CORE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash BYTEA NOT NULL,
        membership TEXT NOT NULL DEFAULT 'Free',
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organizations (
        org_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        plan TEXT NOT NULL DEFAULT 'Free',
        seat_limit INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS org_members (
        id SERIAL PRIMARY KEY,
        org_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        created_at TEXT NOT NULL,
        UNIQUE(org_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS org_invites (
        invite_id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        email TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        token TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        id SERIAL PRIMARY KEY,
        user_id TEXT UNIQUE NOT NULL,
        stripe_customer_id TEXT DEFAULT '',
        stripe_subscription_id TEXT DEFAULT '',
        plan TEXT NOT NULL DEFAULT 'Free',
        status TEXT NOT NULL DEFAULT 'inactive',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_history (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT 'English',
        mode TEXT NOT NULL DEFAULT 'knowledge_base',
        created_at TEXT NOT NULL,
        thread_id TEXT,
        matter_id TEXT DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_thread ON chat_history(thread_id)",
    """
    CREATE TABLE IF NOT EXISTS matters (
        matter_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        org_id TEXT DEFAULT '',
        matter_name TEXT NOT NULL,
        case_number TEXT DEFAULT '',
        practice_area TEXT NOT NULL DEFAULT 'General',
        status_tier TEXT DEFAULT 'ACTIVE',
        client_name TEXT DEFAULT '',
        opposing_party TEXT DEFAULT '',
        venue TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        matter_type TEXT DEFAULT '',
        police_station TEXT DEFAULT '',
        fir_number TEXT DEFAULT '',
        filing_date TEXT DEFAULT '',
        next_hearing_date TEXT DEFAULT '',
        priority TEXT DEFAULT 'Medium',
        description TEXT DEFAULT '',
        is_archived INTEGER DEFAULT 0,
        archived_at TEXT DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_matters_user ON matters(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_matters_org ON matters(org_id)",
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        persona TEXT DEFAULT 'warm',
        practice_area TEXT DEFAULT '',
        preferred_language TEXT DEFAULT 'English',
        communication_notes TEXT DEFAULT '',
        memory_enabled INTEGER DEFAULT 1,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_facts (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        fact_key TEXT NOT NULL,
        fact_value TEXT NOT NULL,
        source TEXT DEFAULT 'manual',
        confidence REAL DEFAULT 1.0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_facts_uid ON user_facts(user_id)",
    """
    CREATE TABLE IF NOT EXISTS thread_summaries (
        thread_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        summary TEXT NOT NULL,
        topics TEXT DEFAULT '[]',
        last_query TEXT DEFAULT '',
        turn_count INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS adaptive_interactions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        mode TEXT NOT NULL,
        query TEXT NOT NULL,
        query_norm TEXT NOT NULL,
        answer_preview TEXT,
        intent TEXT,
        found_in_kb INTEGER DEFAULT 0,
        best_score REAL DEFAULT 0,
        chunk_keys TEXT,
        chat_id TEXT,
        thread_id TEXT,
        implicit_signal TEXT,
        scope_key TEXT DEFAULT 'global',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS adaptive_feedback (
        id TEXT PRIMARY KEY,
        interaction_id TEXT,
        user_id TEXT NOT NULL,
        signal TEXT NOT NULL,
        value REAL DEFAULT 1,
        comment TEXT,
        scope_key TEXT DEFAULT 'global',
        tags_json TEXT DEFAULT '[]',
        metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS adaptive_query_patterns (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        mode TEXT NOT NULL,
        query_norm TEXT NOT NULL,
        successful_expansion TEXT NOT NULL,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        last_used TEXT
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_aqp_user_mode_q
    ON adaptive_query_patterns(COALESCE(user_id, ''), mode, query_norm)
    """,
    """
    CREATE TABLE IF NOT EXISTS adaptive_chunk_boosts (
        chunk_key TEXT NOT NULL,
        user_id TEXT NOT NULL DEFAULT '',
        mode TEXT NOT NULL DEFAULT 'knowledge_base',
        boost_score REAL DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (chunk_key, user_id, mode)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS adaptive_mode_stats (
        user_id TEXT NOT NULL,
        mode TEXT NOT NULL,
        total_turns INTEGER DEFAULT 0,
        positive_signals INTEGER DEFAULT 0,
        negative_signals INTEGER DEFAULT 0,
        not_found_count INTEGER DEFAULT 0,
        avg_best_score REAL DEFAULT 0,
        threshold_delta REAL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, mode)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gemini_usage_daily (
        user_id TEXT NOT NULL,
        day TEXT NOT NULL,
        call_count INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, day)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS logs (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        action TEXT NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_answer_memory (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT '',
        query_norm TEXT NOT NULL,
        query TEXT NOT NULL,
        answer TEXT NOT NULL,
        source TEXT DEFAULT 'kb_success',
        confidence REAL DEFAULT 0.85,
        hit_count INTEGER DEFAULT 0,
        chunk_keys TEXT DEFAULT '[]',
        topics TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_kb_answer_mem_uid_qn ON kb_answer_memory(user_id, query_norm)",
    """
    CREATE TABLE IF NOT EXISTS kb_rescue_events (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT '',
        query TEXT NOT NULL,
        rescue_layer TEXT NOT NULL,
        success INTEGER DEFAULT 0,
        detail TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS human_labels (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        interaction_id TEXT,
        signal TEXT NOT NULL,
        reward REAL DEFAULT 0,
        rlaif_json TEXT DEFAULT '{}',
        mode TEXT DEFAULT 'knowledge_base',
        query TEXT,
        answer_preview TEXT,
        comment TEXT,
        tags_json TEXT DEFAULT '[]',
        metadata_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS preference_pairs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        query TEXT NOT NULL,
        chosen_answer TEXT NOT NULL,
        rejected_answer TEXT NOT NULL,
        chosen_interaction_id TEXT,
        rejected_interaction_id TEXT,
        reward_delta REAL DEFAULT 1.0,
        source TEXT DEFAULT 'human',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learning_signal_events (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        signal TEXT NOT NULL,
        interaction_id TEXT,
        chat_id TEXT,
        mode TEXT DEFAULT 'knowledge_base',
        query TEXT,
        answer_preview TEXT,
        metadata_json TEXT DEFAULT '{}',
        reward REAL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS regenerate_chains (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        original_interaction_id TEXT NOT NULL,
        replacement_interaction_id TEXT,
        query TEXT,
        original_answer TEXT,
        replacement_answer TEXT,
        outcome TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        resolved_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS edit_preference_pairs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        interaction_id TEXT,
        query TEXT,
        original_answer TEXT NOT NULL,
        edited_answer TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_human_labels_uid ON human_labels(user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_pref_pairs_uid ON preference_pairs(user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_signal_events_uid ON learning_signal_events(user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_regen_chains_uid ON regenerate_chains(user_id, created_at DESC)",
]


def _backfill_matter_org_ids(cur) -> None:
    cur.execute(
        """
        SELECT matter_id, user_id FROM matters
        WHERE COALESCE(org_id, '') = ''
        """
    )
    rows = cur.fetchall()
    for matter_id, user_id in rows:
        cur.execute(
            """
            SELECT om.org_id FROM org_members om
            WHERE om.user_id = %s
            ORDER BY CASE om.role WHEN 'owner' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (str(user_id),),
        )
        org_row = cur.fetchone()
        if org_row and org_row[0]:
            cur.execute(
                "UPDATE matters SET org_id = %s WHERE matter_id = %s",
                (str(org_row[0]), str(matter_id)),
            )


def ensure_pg_core_schema() -> None:
    """Create core legacy tables on PostgreSQL when DATABASE_URL is set."""
    from backend.app.core.database import get_database_url, is_postgres

    if not is_postgres():
        return
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError("psycopg2-binary required for PostgreSQL") from exc

    conn = psycopg2.connect(get_database_url())
    cur = conn.cursor()
    for ddl in PG_CORE_DDL:
        cur.execute(ddl)
    for col, typ in (
        ("custom_domain", "TEXT DEFAULT ''"),
        ("logo_url", "TEXT DEFAULT ''"),
        ("primary_color", "TEXT DEFAULT '#1e3a5f'"),
        ("support_email", "TEXT DEFAULT ''"),
    ):
        try:
            cur.execute(
                f"ALTER TABLE organizations ADD COLUMN IF NOT EXISTS {col} {typ}"
            )
        except Exception:
            pass
    for table, col, typ in (
        ("adaptive_feedback", "tags_json", "TEXT DEFAULT '[]'"),
        ("adaptive_feedback", "metadata_json", "TEXT DEFAULT '{}'"),
        ("human_labels", "tags_json", "TEXT DEFAULT '[]'"),
        ("human_labels", "metadata_json", "TEXT DEFAULT '{}'"),
        ("adaptive_mode_stats", "not_found_count", "INTEGER DEFAULT 0"),
        ("adaptive_mode_stats", "threshold_delta", "REAL DEFAULT 0"),
    ):
        try:
            cur.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}"
            )
        except Exception:
            pass
    try:
        _backfill_matter_org_ids(cur)
    except Exception as exc:
        logging.getLogger("legalease.pg").warning("Matter org backfill: %s", exc)
    conn.commit()
    cur.close()
    conn.close()
    logging.getLogger("legalease.pg").info("PostgreSQL core schema ensured")


def postgres_core_ready() -> bool:
    """True when DATABASE_URL is Postgres and core tables exist."""
    from backend.app.core.database import is_postgres

    if not is_postgres():
        return False
    try:
        import psycopg2

        from backend.app.core.database import get_database_url

        conn = psycopg2.connect(get_database_url())
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'users' LIMIT 1"
        )
        ok = cur.fetchone() is not None
        cur.close()
        conn.close()
        return ok
    except Exception:
        return False
