"""
Legal Conversion Engine — deterministic IPC↔BNS mapping from official JSON only.
No LLM inference.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import execute_script, insert_or_replace

NOT_FOUND_MSG = "Official mapping not found. Manual legal verification required."
DATASET_VERSION = "2026.06.04-legal-tools-v2"
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "legal_conversion"
if not (DATA_DIR / "ipc_bns_official.json").is_file():
    alt = ROOT / "Data" / "legal_conversion"
    if (alt / "ipc_bns_official.json").is_file():
        DATA_DIR = alt
IPC_BNS_FILE = DATA_DIR / "ipc_bns_official.json"
CRPC_BNSS_FILE = DATA_DIR / "crpc_bnss_official.json"
DEFAULT_PAIR = "ipc_bns"

PAIR_CONFIG: Dict[str, Dict[str, str]] = {
    "ipc_bns": {
        "old_act": "IPC",
        "new_act": "BNS",
        "old_act_full": "Indian Penal Code, 1860",
        "new_act_full": "Bharatiya Nyaya Sanhita, 2023",
        "source_file": "ipc_bns_official.json",
    },
    "crpc_bnss": {
        "old_act": "CrPC",
        "new_act": "BNSS",
        "old_act_full": "Code of Criminal Procedure, 1973",
        "new_act_full": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "source_file": "crpc_bnss_official.json",
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_section_key(raw: str, *, act: str = "") -> str:
    s = (raw or "").strip()
    for prefix in (
        r"^(?:IPC|I\.P\.C\.?|BNS|Bharatiya\s+Nyaya)\s*",
        r"^(?:Section|Sec\.?|S\.?)\s*",
    ):
        s = re.sub(prefix, "", s, flags=re.I).strip()
    s = s.replace(" ", "")
    m = re.match(r"^(\d+)([A-Za-z]?(?:\(\d+\))?)", s, re.I)
    if m:
        return m.group(1) + (m.group(2).upper() if m.group(2) else "")
    return s


def _is_unmapped_target(sec: str, title: str = "") -> bool:
    s = (sec or "").strip()
    t = (title or "").lower()
    if s in ("—", "-", "", "N/A", "NA", "null", "None"):
        return True
    if "no corresponding" in t or "decriminalised" in t or "not retained" in t:
        return True
    if s.lower() == "omitted" or t.strip() == "omitted":
        return True
    return False


def derive_mapping_type(old_section: str, new_section: str, new_title: str = "") -> str:
    if _is_unmapped_target(new_section, new_title):
        return "No corresponding provision"
    o = normalize_section_key(old_section)
    n = normalize_section_key(new_section)
    if o == n:
        return "Direct mapping (same section number)"
    return "Direct mapping (renumbered)"


def derive_status(old_title: str, row_status: Optional[str] = None) -> str:
    if row_status:
        return str(row_status)
    if "[omitted" in (old_title or "").lower():
        return "Omitted"
    return "Active"


def ensure_legal_conversion_schema(force_reseed: bool = False) -> None:
    conn = connect_data_db()
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS legal_conversion_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS legal_section_mappings (
            pair_type TEXT NOT NULL,
            old_section TEXT NOT NULL,
            new_section TEXT NOT NULL,
            old_act TEXT,
            new_act TEXT,
            old_title TEXT,
            new_title TEXT,
            status TEXT,
            mapping_type TEXT,
            notes TEXT,
            punishment TEXT,
            cognizable TEXT,
            bailable TEXT,
            court_type TEXT,
            source_file TEXT,
            dataset_version TEXT,
            PRIMARY KEY (pair_type, old_section, new_section)
        );
        CREATE INDEX IF NOT EXISTS idx_lcm_old ON legal_section_mappings(pair_type, old_section);
        CREATE INDEX IF NOT EXISTS idx_lcm_new ON legal_section_mappings(pair_type, new_section);
        CREATE TABLE IF NOT EXISTS legal_conversion_audit (
            audit_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            pair_type TEXT,
            action TEXT NOT NULL,
            query TEXT,
            result_summary TEXT,
            dataset_version TEXT,
            matter_id TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    row = conn.execute(
        "SELECT meta_value FROM legal_conversion_meta WHERE meta_key = 'dataset_version'"
    ).fetchone()
    stored = row[0] if row else None
    count = conn.execute("SELECT COUNT(*) FROM legal_section_mappings").fetchone()[0]
    if force_reseed or stored != DATASET_VERSION or count == 0:
        conn.execute("DELETE FROM legal_section_mappings")
        _seed_all_pairs(conn)
        insert_or_replace(
            conn,
            "INSERT OR REPLACE INTO legal_conversion_meta (meta_key, meta_value) VALUES ('dataset_version', ?)",
            """
            INSERT INTO legal_conversion_meta (meta_key, meta_value) VALUES ('dataset_version', ?)
            ON CONFLICT (meta_key) DO UPDATE SET meta_value = EXCLUDED.meta_value
            """,
            (DATASET_VERSION,),
        )
        conn.commit()
    conn.close()


def _insert_row(
    conn,
    *,
    pair_type: str,
    old_section: str,
    new_section: str,
    old_act: str,
    new_act: str,
    old_title: str,
    new_title: str,
    status: str,
    mapping_type: str,
    notes: str,
    punishment: Optional[str],
    cognizable: Any,
    bailable: Any,
    court_type: Optional[str],
    source_file: str,
) -> None:
    insert_or_replace(
        conn,
        """
        INSERT OR REPLACE INTO legal_section_mappings (
            pair_type, old_section, new_section, old_act, new_act,
            old_title, new_title, status, mapping_type, notes,
            punishment, cognizable, bailable, court_type, source_file, dataset_version
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        """
        INSERT INTO legal_section_mappings (
            pair_type, old_section, new_section, old_act, new_act,
            old_title, new_title, status, mapping_type, notes,
            punishment, cognizable, bailable, court_type, source_file, dataset_version
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT (pair_type, old_section, new_section) DO UPDATE SET
            old_act = EXCLUDED.old_act,
            new_act = EXCLUDED.new_act,
            old_title = EXCLUDED.old_title,
            new_title = EXCLUDED.new_title,
            status = EXCLUDED.status,
            mapping_type = EXCLUDED.mapping_type,
            notes = EXCLUDED.notes,
            punishment = EXCLUDED.punishment,
            cognizable = EXCLUDED.cognizable,
            bailable = EXCLUDED.bailable,
            court_type = EXCLUDED.court_type,
            source_file = EXCLUDED.source_file,
            dataset_version = EXCLUDED.dataset_version
        """,
        (
            pair_type,
            old_section,
            new_section if not _is_unmapped_target(new_section, new_title) else "",
            old_act,
            new_act,
            old_title,
            new_title,
            status,
            mapping_type,
            notes,
            punishment,
            _fmt_bool_field(cognizable),
            _fmt_bool_field(bailable),
            court_type,
            source_file,
            DATASET_VERSION,
        ),
    )


def _fmt_bool_field(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return str(v)


def _seed_all_pairs(conn) -> None:
    if IPC_BNS_FILE.is_file():
        rows = json.loads(IPC_BNS_FILE.read_text(encoding="utf-8"))
        cfg = PAIR_CONFIG["ipc_bns"]
        for r in rows:
            old = str(r.get("ipc_section", "")).strip()
            new = str(r.get("bns_section", "")).strip()
            old_title = r.get("ipc_title") or ""
            new_title = r.get("bns_title") or ""
            mt = derive_mapping_type(old, new, new_title)
            _insert_row(
                conn,
                pair_type="ipc_bns",
                old_section=normalize_section_key(old),
                new_section=normalize_section_key(new) if not _is_unmapped_target(new, new_title) else "",
                old_act=cfg["old_act"],
                new_act=cfg["new_act"],
                old_title=old_title,
                new_title=new_title,
                status=derive_status(old_title),
                mapping_type=mt,
                notes="",
                punishment=r.get("punishment"),
                cognizable=r.get("cognizable"),
                bailable=r.get("bailable"),
                court_type=r.get("court_type"),
                source_file=cfg["source_file"],
            )
    if CRPC_BNSS_FILE.is_file():
        rows = json.loads(CRPC_BNSS_FILE.read_text(encoding="utf-8"))
        cfg = PAIR_CONFIG["crpc_bnss"]
        for r in rows:
            if (r.get("act") or "").strip().lower() not in ("crpc", "code of criminal procedure"):
                continue
            old = str(r.get("section_number", "")).strip()
            new = str(r.get("bns_section", "")).strip()
            old_title = r.get("section_title") or r.get("crpc_title") or ""
            new_title = r.get("bns_title") or ""
            mt = derive_mapping_type(old, new, new_title)
            _insert_row(
                conn,
                pair_type="crpc_bnss",
                old_section=normalize_section_key(old),
                new_section=normalize_section_key(new) if not _is_unmapped_target(new, new_title) else "",
                old_act=cfg["old_act"],
                new_act=cfg["new_act"],
                old_title=old_title,
                new_title=new_title,
                status=derive_status(old_title, r.get("status")),
                mapping_type=mt,
                notes="",
                punishment=r.get("punishment"),
                cognizable=r.get("cognizable"),
                bailable=r.get("bailable"),
                court_type=r.get("court_type"),
                source_file=cfg["source_file"],
            )


def _resolve_pair(pair_type: str) -> str:
    return pair_type if pair_type in PAIR_CONFIG else DEFAULT_PAIR


def _pair_cfg(pair_type: str) -> Dict[str, str]:
    return PAIR_CONFIG[_resolve_pair(pair_type)]


def _format_response(
    pair_type: str,
    *,
    direction: str,
    rows: List[Tuple],
    query_section: str,
) -> Dict[str, Any]:
    cfg = _pair_cfg(pair_type)
    if not rows:
        is_forward = direction == "forward"
        old_act = cfg["old_act"] if is_forward else cfg["new_act"]
        return {
            "status": "not_found",
            "found": False,
            "pair_type": pair_type,
            "direction": direction,
            "query_section": query_section,
            "message": NOT_FOUND_MSG,
            "dataset_version": DATASET_VERSION,
            "confidence": 0,
            "source": "Official mapping dataset",
            f"{old_act.lower()}_section_label": f"{old_act} Section {query_section}",
        }

    primary = rows[0]
    cols = [
        "pair_type", "old_section", "new_section", "old_act", "new_act",
        "old_title", "new_title", "status", "mapping_type", "notes",
        "punishment", "cognizable", "bailable", "court_type", "source_file", "dataset_version",
    ]
    rec = dict(zip(cols, primary))

    equivalents: List[Dict[str, Any]] = []
    for row in rows:
        r = dict(zip(cols, row))
        if direction == "forward":
            if not _is_unmapped_target(r["new_section"], r["new_title"]):
                equivalents.append(
                    {
                        "section": r["new_section"],
                        "title": r["new_title"],
                        "act": cfg["new_act"],
                        "punishment": r.get("punishment"),
                        "cognizable": r.get("cognizable"),
                        "bailable": r.get("bailable"),
                        "court_type": r.get("court_type"),
                    }
                )
        else:
            equivalents.append(
                {
                    "section": r["old_section"],
                    "title": r["old_title"],
                    "act": cfg["old_act"],
                }
            )

    mapped = bool(equivalents) or _is_unmapped_target(rec["new_section"], rec["new_title"])
    out: Dict[str, Any] = {
        "status": "mapped" if mapped else "not_found",
        "found": mapped,
        "pair_type": pair_type,
        "direction": direction,
        "query_section": query_section,
        "old_act": cfg["old_act"],
        "new_act": cfg["new_act"],
        "old_act_full": cfg["old_act_full"],
        "new_act_full": cfg["new_act_full"],
        "old_section": rec["old_section"],
        "new_section": rec["new_section"] or None,
        "old_title": rec["old_title"],
        "new_title": rec["new_title"],
        "old_section_label": f"{cfg['old_act']} Section {rec['old_section']}",
        "new_section_label": (
            f"{cfg['new_act']} Section {rec['new_section']}"
            if rec["new_section"]
            else None
        ),
        "status_label": rec["status"],
        "mapping_type": rec["mapping_type"],
        "notes": rec["notes"] or "",
        "punishment": rec["punishment"],
        "cognizable": rec["cognizable"],
        "bailable": rec["bailable"],
        "court_type": rec["court_type"],
        "equivalents": equivalents,
        "alternate_mappings": equivalents[1:] if len(equivalents) > 1 else [],
        "message": None if mapped else NOT_FOUND_MSG,
        "dataset_version": DATASET_VERSION,
        "source_file": rec["source_file"],
        "source": "Official mapping dataset (deterministic lookup)",
        "confidence": 100 if mapped else 0,
        "deterministic": True,
        "ai_mapping": False,
    }
    return out


def convert_section(
    pair_type: str,
    section: str,
    *,
    direction: str = "forward",
    user_id: str = "",
    matter_id: str = "",
) -> Dict[str, Any]:
    pair_type = _resolve_pair(pair_type)
    ensure_legal_conversion_schema()
    key = normalize_section_key(section)
    conn = connect_data_db()

    if direction == "forward":
        rows = conn.execute(
            """
            SELECT * FROM legal_section_mappings
            WHERE pair_type = ? AND old_section = ?
            ORDER BY new_section
            """,
            (pair_type, key),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM legal_section_mappings
            WHERE pair_type = ? AND new_section = ? AND new_section != ''
            ORDER BY old_section
            """,
            (pair_type, key),
        ).fetchall()
    conn.close()

    out = _format_response(pair_type, direction=direction, rows=rows, query_section=key)
    if user_id:
        audit_log(
            user_id,
            "convert",
            pair_type=pair_type,
            query=f"{direction}:{key}",
            result_summary="found" if out.get("found") else "not_found",
            matter_id=matter_id,
        )
    return out


def search_mappings(
    pair_type: str,
    q: str,
    *,
    limit: int = 25,
) -> Dict[str, Any]:
    pair_type = _resolve_pair(pair_type)
    ensure_legal_conversion_schema()
    ql = (q or "").strip()
    if not ql:
        return {"results": [], "count": 0, "dataset_version": DATASET_VERSION, "pair_type": pair_type}

    conn = connect_data_db()
    results: List[Dict[str, Any]] = []
    key = normalize_section_key(ql)
    cfg = _pair_cfg(pair_type)

    if re.match(r"^\d+[A-Z]?(?:\(\d+\))?$", key, re.I):
        for direction, col in (("forward", "old_section"), ("reverse", "new_section")):
            rows = conn.execute(
                f"SELECT * FROM legal_section_mappings WHERE pair_type = ? AND {col} = ? LIMIT ?",
                (pair_type, key, limit),
            ).fetchall()
            for row in rows:
                r = convert_section(pair_type, key, direction=direction)
                if r.get("found") and r not in results:
                    results.append(r)

    if not results:
        like = f"%{ql.lower()}%"
        rows = conn.execute(
            """
            SELECT DISTINCT old_section FROM legal_section_mappings
            WHERE pair_type = ? AND (
                LOWER(old_section) LIKE ? OR LOWER(new_section) LIKE ?
                OR LOWER(old_title) LIKE ? OR LOWER(new_title) LIKE ?
            )
            LIMIT ?
            """,
            (pair_type, like, like, like, like, limit),
        ).fetchall()
        for (old_sec,) in rows:
            r = convert_section(pair_type, old_sec, direction="forward")
            if r.get("found"):
                results.append(r)

    conn.close()
    return {
        "results": results[:limit],
        "count": len(results[:limit]),
        "dataset_version": DATASET_VERSION,
        "pair_type": pair_type,
    }


def dataset_meta() -> Dict[str, Any]:
    ensure_legal_conversion_schema()
    conn = connect_data_db()
    pairs: List[Dict[str, Any]] = []
    for pair_id, cfg in PAIR_CONFIG.items():
        n = conn.execute(
            "SELECT COUNT(*) FROM legal_section_mappings WHERE pair_type = ?",
            (pair_id,),
        ).fetchone()[0]
        pairs.append(
            {
                "pair_type": pair_id,
                "old_act": cfg["old_act"],
                "new_act": cfg["new_act"],
                "old_act_full": cfg["old_act_full"],
                "new_act_full": cfg["new_act_full"],
                "record_count": n,
                "source_file": cfg.get("source_file"),
                "available": n > 0,
            }
        )
    total = conn.execute("SELECT COUNT(*) FROM legal_section_mappings").fetchone()[0]
    conn.close()
    return {
        "dataset_version": DATASET_VERSION,
        "record_count": total,
        "pairs": pairs,
        "source": "Official uploaded mapping JSON (ipc_bns_official.json)",
        "deterministic": True,
        "ai_mapping": False,
        "last_updated": "2026-06-04",
    }


def audit_log(
    user_id: str,
    action: str,
    *,
    pair_type: str = "",
    query: str = "",
    result_summary: str = "",
    matter_id: str = "",
) -> str:
    ensure_legal_conversion_schema()
    aid = str(uuid.uuid4())
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO legal_conversion_audit
        (audit_id, user_id, pair_type, action, query, result_summary, dataset_version, matter_id, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (aid, str(user_id), pair_type, action, query[:2000], result_summary[:4000], DATASET_VERSION, matter_id or "", _utc()),
    )
    conn.commit()
    conn.close()
    return aid


def to_ipc_bns_v3_shape(result: Dict[str, Any]) -> Dict[str, Any]:
    """Backward-compatible shape for ipc_bns_engine_v3 consumers."""
    if not result.get("found"):
        return {
            "status": result.get("status", "not_found"),
            "found": False,
            "ipc_key": result.get("old_section") or result.get("query_section"),
            "bns_key": result.get("new_section"),
            "ipc_section": result.get("old_section_label"),
            "bns_section": result.get("new_section_label"),
            "message": result.get("message", NOT_FOUND_MSG),
            "dataset_version": DATASET_VERSION,
            "confidence": 0,
        }
    return {
        "status": "mapped",
        "found": True,
        "ipc_key": result.get("old_section"),
        "bns_key": result.get("new_section"),
        "ipc_section": result.get("old_section_label"),
        "bns_section": result.get("new_section_label"),
        "offence_title": result.get("old_title"),
        "short_description": result.get("new_title"),
        "punishment": result.get("punishment"),
        "cognizable": result.get("cognizable"),
        "bailable": result.get("bailable"),
        "court_jurisdiction": result.get("court_type"),
        "mapping_status": result.get("mapping_type"),
        "change_notes": result.get("notes"),
        "source": result.get("source"),
        "official_source": result.get("source_file"),
        "dataset_version": DATASET_VERSION,
        "confidence": 100,
        "mapping_type": result.get("mapping_type"),
        "status_label": result.get("status_label"),
        "equivalents": result.get("equivalents"),
        "alternate_mappings": result.get("alternate_mappings"),
    }
