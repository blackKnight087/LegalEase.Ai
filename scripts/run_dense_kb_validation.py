#!/usr/bin/env python3
"""
Validate KB against LegalEase_Dense_KB_Test_Document.pdf content.

Usage (from project root):
  py scripts/run_dense_kb_validation.py
  py scripts/run_dense_kb_validation.py --user-id YOUR_USER_UUID
  py scripts/run_dense_kb_validation.py --pdf "C:\\Users\\ASUS\\Downloads\\LegalEase_Dense_KB_Test_Document.pdf"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dense KB test document validation")
    parser.add_argument("--user-id", default="", help="LegalEase user UUID (optional)")
    parser.add_argument(
        "--pdf",
        default=str(Path.home() / "Downloads" / "LegalEase_Dense_KB_Test_Document.pdf"),
        help="Path to dense test PDF",
    )
    args = parser.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"PDF not found: {pdf}")
        print("Upload it via Documents, then re-index, or pass --pdf with the correct path.")
        return 1

    print(f"Dense KB test PDF: {pdf}")
    print(f"Size: {pdf.stat().st_size / (1024*1024):.2f} MB\n")

    from backend.app.core.dense_kb_test_queries import DENSE_KB_SMOKE_QUERIES  # benchmark PDF only
    from backend.app.core.kb_smoke_query_builder import build_smoke_queries_from_index

    uid = (args.user_id or "").strip()
    if not uid:
        try:
            import sqlite3

            db = ROOT / "legalease.db"
            if db.is_file():
                conn = sqlite3.connect(db)
                row = conn.execute(
                    "SELECT uploader_id, COUNT(*) FROM documents "
                    "WHERE filename LIKE '%Dense_KB%' OR filename LIKE '%Dense%KB%Test%' "
                    "GROUP BY uploader_id ORDER BY COUNT(*) DESC LIMIT 1"
                ).fetchone()
                conn.close()
                if row:
                    uid = str(row[0])
                    print(f"Detected user from DB: {uid} ({row[1]} dense doc row(s))\n")
        except Exception:
            pass

    if not uid:
        print("No --user-id and could not detect uploader from DB.")
        print("Upload the PDF in the app, then run:")
        print('  py scripts/run_dense_kb_validation.py --user-id "<your-user-uuid>"')
        return 1

    from app import resolve_rag_index_dir
    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
    from backend.app.core.kb_smoke_test import run_kb_smoke_test

    index_dir = resolve_rag_index_dir(uid)
    vectors = count_index_vectors(index_dir) if index_exists(index_dir) else 0
    print(f"Index: {index_dir}")
    print(f"Vectors: {vectors}\n")

    if vectors < 50:
        print(
            "WARNING: Vector count is low for this 60-page test PDF.\n"
            "Expected hundreds of chunks after re-index with statute-heading split.\n"
            "Go to Documents → Re-index all, then re-run this script.\n"
        )

    # Universal queries from index first; dense list is optional benchmark comparison
    universal = build_smoke_queries_from_index(index_dir)
    print(f"Universal smoke queries from your index ({len(universal)}):")
    for q in universal:
        print(f"  - {q['query']}")
    print()

    result = run_kb_smoke_test(uid, queries=universal)
    print("\n--- Optional benchmark (dense PDF checklist only) ---")
    bench = run_kb_smoke_test(uid, queries=DENSE_KB_SMOKE_QUERIES)
    print(f"Benchmark pass: {bench.get('ok')} ({bench.get('passed')}/{len(DENSE_KB_SMOKE_QUERIES)})")
    print(f"KB pass: {result.get('kb_pass')} | passed={result.get('passed')} failed={result.get('failed')}")
    print(f"Latency: {result.get('total_latency_ms')} ms\n")

    for q in result.get("queries") or []:
        mark = "PASS" if q.get("status") == "pass" else "FAIL"
        print(f"  [{mark}] {q.get('query')} — chunks={q.get('chunk_count')} mode={q.get('retrieval_mode', '')}")

    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
