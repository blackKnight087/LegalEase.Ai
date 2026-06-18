"""
Phase 1 practice-management schema — matters, notes, templates, clause library.
Hooks into legalease.db (SQLite) alongside user_memory / adaptive_learning.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.core.database import connect_data_db
from backend.app.core.legacy_db import use_postgres_legacy


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate_documents_matter_id(c: sqlite3.Cursor) -> None:
    exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents' LIMIT 1"
    ).fetchone()
    if not exists:
        return
    cols = [row[1] for row in c.execute("PRAGMA table_info(documents)").fetchall()]
    if "matter_id" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN matter_id TEXT DEFAULT ''")


def _migrate_documents_content_hash(c: sqlite3.Cursor) -> None:
    exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents' LIMIT 1"
    ).fetchone()
    if not exists:
        return
    cols = [row[1] for row in c.execute("PRAGMA table_info(documents)").fetchall()]
    if "content_hash" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT DEFAULT ''")
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_uploader_hash "
        "ON documents(uploader_id, content_hash)"
    )


def _migrate_documents_org_id(c: sqlite3.Cursor) -> None:
    exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents' LIMIT 1"
    ).fetchone()
    if not exists:
        return
    cols = [row[1] for row in c.execute("PRAGMA table_info(documents)").fetchall()]
    for col, ddl in (
        ("org_id", "ALTER TABLE documents ADD COLUMN org_id TEXT DEFAULT ''"),
        ("privileged", "ALTER TABLE documents ADD COLUMN privileged INTEGER DEFAULT 0"),
        ("doc_version", "ALTER TABLE documents ADD COLUMN doc_version INTEGER DEFAULT 1"),
        ("index_status", "ALTER TABLE documents ADD COLUMN index_status TEXT DEFAULT ''"),
    ):
        if col not in cols:
            c.execute(ddl)


def _migrate_matters_extended(c: sqlite3.Cursor) -> None:
    """Expand matters + workflow tables for case workspace OS."""
    existing_tables = {
        row[0]
        for row in c.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    mcols = {row[1] for row in c.execute("PRAGMA table_info(matters)").fetchall()}
    for col, ddl in (
        ("matter_type", "ALTER TABLE matters ADD COLUMN matter_type TEXT DEFAULT 'General Research'"),
        ("police_station", "ALTER TABLE matters ADD COLUMN police_station TEXT DEFAULT ''"),
        ("fir_number", "ALTER TABLE matters ADD COLUMN fir_number TEXT DEFAULT ''"),
        ("filing_date", "ALTER TABLE matters ADD COLUMN filing_date TEXT DEFAULT ''"),
        ("next_hearing_date", "ALTER TABLE matters ADD COLUMN next_hearing_date TEXT DEFAULT ''"),
        ("priority", "ALTER TABLE matters ADD COLUMN priority TEXT DEFAULT 'Medium'"),
        ("description", "ALTER TABLE matters ADD COLUMN description TEXT DEFAULT ''"),
        ("is_archived", "ALTER TABLE matters ADD COLUMN is_archived INTEGER DEFAULT 0"),
        ("archived_at", "ALTER TABLE matters ADD COLUMN archived_at TEXT DEFAULT ''"),
    ):
        if col not in mcols:
            c.execute(ddl)

    if "matter_hearings" in existing_tables:
        hcols = {row[1] for row in c.execute("PRAGMA table_info(matter_hearings)").fetchall()}
        for col, ddl in (
            ("judge", "ALTER TABLE matter_hearings ADD COLUMN judge TEXT DEFAULT ''"),
            ("arguments", "ALTER TABLE matter_hearings ADD COLUMN arguments TEXT DEFAULT ''"),
            ("observations", "ALTER TABLE matter_hearings ADD COLUMN observations TEXT DEFAULT ''"),
            ("next_hearing_date", "ALTER TABLE matter_hearings ADD COLUMN next_hearing_date TEXT DEFAULT ''"),
            ("summary", "ALTER TABLE matter_hearings ADD COLUMN summary TEXT DEFAULT ''"),
            (
                "prosecution_argument",
                "ALTER TABLE matter_hearings ADD COLUMN prosecution_argument TEXT DEFAULT ''",
            ),
            (
                "defense_argument",
                "ALTER TABLE matter_hearings ADD COLUMN defense_argument TEXT DEFAULT ''",
            ),
            (
                "document_source",
                "ALTER TABLE matter_hearings ADD COLUMN document_source TEXT DEFAULT ''",
            ),
            ("page_number", "ALTER TABLE matter_hearings ADD COLUMN page_number TEXT DEFAULT ''"),
            ("source", "ALTER TABLE matter_hearings ADD COLUMN source TEXT DEFAULT 'manual'"),
        ):
            if col not in hcols:
                c.execute(ddl)

    if "matter_evidence" in existing_tables:
        ecols = {row[1] for row in c.execute("PRAGMA table_info(matter_evidence)").fetchall()}
        for col, ddl in (
            ("description", "ALTER TABLE matter_evidence ADD COLUMN description TEXT DEFAULT ''"),
            (
                "source_document",
                "ALTER TABLE matter_evidence ADD COLUMN source_document TEXT DEFAULT ''",
            ),
            ("page_number", "ALTER TABLE matter_evidence ADD COLUMN page_number TEXT DEFAULT ''"),
            ("importance", "ALTER TABLE matter_evidence ADD COLUMN importance TEXT DEFAULT ''"),
            (
                "person_related",
                "ALTER TABLE matter_evidence ADD COLUMN person_related TEXT DEFAULT ''",
            ),
            ("evidence_type", "ALTER TABLE matter_evidence ADD COLUMN evidence_type TEXT DEFAULT ''"),
        ):
            if col not in ecols:
                c.execute(ddl)

    if "matter_tasks" in existing_tables:
        tcols = {row[1] for row in c.execute("PRAGMA table_info(matter_tasks)").fetchall()}
        if "task_source" not in tcols:
            c.execute(
                "ALTER TABLE matter_tasks ADD COLUMN task_source TEXT DEFAULT 'manual'"
            )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS matter_entities (
            entity_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            entity_type TEXT NOT NULL DEFAULT 'person',
            label TEXT NOT NULL,
            source_doc_id TEXT DEFAULT '',
            confidence REAL DEFAULT 0.8,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_matter_entities_mid ON matter_entities(matter_id)"
    )
    c.execute(
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
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_matter_evidence_mid ON matter_evidence(matter_id)"
    )
    c.execute(
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
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_matter_contradictions_mid ON matter_contradictions(matter_id)"
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS matter_intel_status (
            matter_id TEXT PRIMARY KEY,
            stage TEXT NOT NULL DEFAULT 'idle',
            message TEXT DEFAULT '',
            progress_json TEXT DEFAULT '{}',
            last_error TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS matter_members (
            member_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_matter_members_unique "
        "ON matter_members(matter_id, user_id)"
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS matter_timeline_suggestions (
            suggestion_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            event_date TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            source_doc_id TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_matter_tl_suggest_mid ON matter_timeline_suggestions(matter_id)"
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS matter_audit_log (
            log_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        )
        """
    )
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_matter_audit_mid ON matter_audit_log(matter_id)"
    )

    dcols = {row[1] for row in c.execute("PRAGMA table_info(documents)").fetchall()}
    for col, ddl in (
        ("privileged", "ALTER TABLE documents ADD COLUMN privileged INTEGER DEFAULT 0"),
        ("doc_version", "ALTER TABLE documents ADD COLUMN doc_version INTEGER DEFAULT 1"),
        ("index_status", "ALTER TABLE documents ADD COLUMN index_status TEXT DEFAULT ''"),
    ):
        if col not in dcols:
            c.execute(ddl)


def ensure_practice_schema() -> None:
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema
        from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

        ensure_pg_core_schema()
        ensure_pg_rest_schema()
        return
    conn = connect_data_db()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS matters (
            matter_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_name TEXT NOT NULL,
            case_number TEXT DEFAULT '',
            practice_area TEXT NOT NULL DEFAULT 'General',
            status_tier TEXT DEFAULT 'ACTIVE',
            client_name TEXT DEFAULT '',
            opposing_party TEXT DEFAULT '',
            venue TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_matters_user ON matters(user_id);

        CREATE TABLE IF NOT EXISTS matter_notes (
            note_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            author_id TEXT NOT NULL,
            raw_content TEXT NOT NULL,
            anonymized_content TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_notes_mid ON matter_notes(matter_id);

        CREATE TABLE IF NOT EXISTS document_templates (
            template_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            template_name TEXT NOT NULL,
            practice_area TEXT NOT NULL DEFAULT 'General',
            raw_markdown_structure TEXT NOT NULL,
            variable_json_map TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_doc_templates_user ON document_templates(user_id);

        CREATE TABLE IF NOT EXISTS clause_library (
            clause_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            clause_tag TEXT NOT NULL,
            practice_area TEXT NOT NULL DEFAULT 'General',
            clause_text_content TEXT NOT NULL,
            confidence_weight REAL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_clause_tag ON clause_library(clause_tag);

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
        );
        CREATE INDEX IF NOT EXISTS idx_workspace_drafts_user ON workspace_drafts(user_id);
        CREATE INDEX IF NOT EXISTS idx_workspace_drafts_status ON workspace_drafts(status);
        CREATE INDEX IF NOT EXISTS idx_workspace_drafts_matter ON workspace_drafts(matter_id);

        CREATE TABLE IF NOT EXISTS workspace_draft_versions (
            version_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            content TEXT NOT NULL,
            change_summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_workspace_versions_draft ON workspace_draft_versions(draft_id);

        CREATE TABLE IF NOT EXISTS workspace_draft_comments (
            comment_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            author_name TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_workspace_comments_draft ON workspace_draft_comments(draft_id);

        CREATE TABLE IF NOT EXISTS matter_timeline (
            event_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            event_date TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            event_type TEXT DEFAULT 'general',
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_timeline_mid ON matter_timeline(matter_id);

        CREATE TABLE IF NOT EXISTS matter_hearings (
            hearing_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            hearing_date TEXT NOT NULL,
            court_name TEXT DEFAULT '',
            purpose TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            status TEXT DEFAULT 'scheduled',
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_hearings_mid ON matter_hearings(matter_id);

        CREATE TABLE IF NOT EXISTS matter_tasks (
            task_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            assignee TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_tasks_mid ON matter_tasks(matter_id);

        CREATE TABLE IF NOT EXISTS matter_deadlines (
            deadline_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            deadline_type TEXT DEFAULT 'filing',
            status TEXT DEFAULT 'pending',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_matter_deadlines_mid ON matter_deadlines(matter_id);
        """
    )
    try:
        _migrate_documents_matter_id(c)
        _migrate_documents_content_hash(c)
        _migrate_matters_extended(c)
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
    remove_fir_templates()


def remove_fir_templates() -> int:
    """Remove legacy FIR drafting templates from DB (feature discontinued)."""
    conn = connect_data_db()
    cur = conn.execute(
        """
        DELETE FROM document_templates
        WHERE LOWER(template_name) = 'fir'
           OR LOWER(template_name) LIKE '%first information report%'
           OR raw_markdown_structure LIKE '%FIRST INFORMATION REPORT%'
        """
    )
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted


def seed_builtin_templates_if_empty() -> int:
    """Seed from drafting.TEMPLATES when no global templates exist."""
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT COUNT(*) FROM document_templates WHERE user_id = ''"
    ).fetchone()
    if row and row[0] > 0:
        conn.close()
        return 0
    try:
        from drafting import TEMPLATES
    except ImportError:
        conn.close()
        return 0

    import re
    import uuid

    area_map = {
        "LEGAL_NOTICE": "Civil",
        "BAIL_APPLICATION": "Criminal",
        "RENT_AGREEMENT": "Property",
        "NDA": "Corporate",
        "AFFIDAVIT": "Civil",
    }
    now = _utc()
    inserted = 0
    for key, body in TEMPLATES.items():
        vars_found = sorted(set(re.findall(r"\{(\w+)\}", body)))
        tid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO document_templates
            (template_id, user_id, template_name, practice_area,
             raw_markdown_structure, variable_json_map, created_at, updated_at)
            VALUES (?, '', ?, ?, ?, ?, ?, ?)
            """,
            (
                tid,
                key.replace("_", " ").title(),
                area_map.get(key, "General"),
                body.strip(),
                json.dumps(vars_found),
                now,
                now,
            ),
        )
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


def seed_default_clauses_if_empty() -> int:
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT COUNT(*) FROM clause_library WHERE user_id = ''"
    ).fetchone()
    if row and row[0] > 0:
        conn.close()
        return 0
    import uuid

    defaults: List[Dict[str, Any]] = [
        {
            "tag": "CONFIDENTIALITY",
            "area": "Corporate",
            "text": (
                "The Receiving Party shall keep all Confidential Information strictly confidential "
                "and use it only for the Purpose defined in this Agreement."
            ),
        },
        {
            "tag": "TERMINATION",
            "area": "Corporate",
            "text": (
                "Either Party may terminate this Agreement with thirty (30) days' written notice. "
                "Obligations of confidentiality survive termination."
            ),
        },
        {
            "tag": "FORCE_MAJEURE",
            "area": "General",
            "text": (
                "Neither Party shall be liable for delay or failure caused by events beyond reasonable "
                "control, including acts of God, war, epidemic, or government order."
            ),
        },
        {
            "tag": "ARBITRATION",
            "area": "General",
            "text": (
                "Disputes shall be resolved by arbitration under the Arbitration and Conciliation Act, 1996 "
                "at {VENUE}, with proceedings in English."
            ),
        },
        {
            "tag": "INDEMNITY_MUTUAL",
            "area": "Corporate",
            "text": (
                "Each Party shall indemnify and hold harmless the other from claims "
                "arising out of its breach of this Agreement, subject to the liability cap herein."
            ),
        },
        {
            "tag": "LIMITATION_CAP",
            "area": "Corporate",
            "text": (
                "Total aggregate liability under this Agreement shall not exceed the fees paid "
                "in the twelve (12) months preceding the claim."
            ),
        },
        {
            "tag": "GOVERNING_LAW_INDIA",
            "area": "General",
            "text": "This Agreement shall be governed by the laws of India; courts at {VENUE} shall have exclusive jurisdiction.",
        },
    ]
    now = _utc()
    for d in defaults:
        conn.execute(
            """
            INSERT INTO clause_library
            (clause_id, user_id, clause_tag, practice_area, clause_text_content,
             confidence_weight, created_at, updated_at)
            VALUES (?, '', ?, ?, ?, 1.0, ?, ?)
            """,
            (str(uuid.uuid4()), d["tag"], d["area"], d["text"], now, now),
        )
    conn.commit()
    conn.close()
    return len(defaults)
