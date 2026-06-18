#!/usr/bin/env python3
"""One-shot: warm embeddings + re-index all users with documents but no FAISS vectors."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "legacy_saas"))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
os.environ.setdefault("LOW_RESOURCE_MODE", "1")
os.environ.setdefault("LEGALEEASE_HF_CACHE", str(ROOT / "Data" / "hf_cache"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

from backend.app.core.embedding_manager import get_manager
from legalease_auth import run_query


def main() -> int:
    print("1/3 Warming embeddings...")
    mgr = get_manager()
    mgr.start_background_load()
    if not mgr.wait_until_ready(timeout_sec=float(os.getenv("EMBEDDING_MODEL_LOAD_TIMEOUT_SEC", "240"))):
        print("FAILED:", mgr.get_status())
        return 1
    print("   Embeddings ready:", mgr.get_status().get("model"))

    rows = run_query(
        "SELECT DISTINCT uploader_id FROM documents WHERE uploader_id IS NOT NULL",
        fetch=True,
    ) or []
    if not rows:
        print("No documents in database.")
        return 0

    from app import build_faiss_index
    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
    from backend.app.core.kb_status_sync import sync_kb_status_from_faiss
    from backend.app.core.matter_index import resolve_rag_index_dir

    ok_count = 0
    for (uid,) in rows:
        uid = str(uid)
        index_dir = resolve_rag_index_dir(uid, None)
        vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
        doc_row = run_query(
            "SELECT COUNT(*) FROM documents WHERE uploader_id = ?",
            (uid,),
            fetch=True,
        )
        doc_count = int(doc_row[0][0]) if doc_row else 0
        if doc_count == 0:
            continue
        if vectors > 0:
            print(f"2/3 User {uid[:8]}... already has {vectors} vectors - syncing status only")
            sync_kb_status_from_faiss(uid)
            ok_count += 1
            continue
        print(f"2/3 Re-indexing user {uid[:8]}... ({doc_count} doc(s))")
        ok, msg = build_faiss_index(uid, use_ocr=False, incremental=False)
        vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
        sync_kb_status_from_faiss(uid)
        print(f"   ok={ok} vectors={vectors} {str(msg)[:120]}")
        if ok and vectors > 0:
            ok_count += 1

    print(f"3/3 Done. {ok_count}/{len(rows)} user scope(s) have searchable KB.")
    return 0 if ok_count > 0 or not rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
