"""
Lightweight RAG retrieval evaluator - imports rag only (not app.py / Streamlit).

Usage:
  py -3 scripts/rag_eval.py
  py -3 scripts/rag_eval.py --index-dir faiss_indexes/user_<id>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import rag  # noqa: E402

GOLDEN_QUERIES = [
    "What is Section 57 CrPC about?",
    "What is Section 66C of the IT Act?",
    "Which case recognized the Right to Privacy?",
    "Difference between theft and robbery",
]


def _discover_user_index() -> Path | None:
    base = ROOT / "faiss_indexes"
    if not base.exists():
        return None
    candidates = sorted(
        [p for p in base.glob("user_*") if rag.index_exists(p)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _preview(text: str, n: int = 120) -> str:
    return (text or "").replace("\n", " ")[:n]


def run_eval(index_dir: Path, k: int = 5) -> int:
    print(f"Index: {index_dir}")
    print(f"Exists: {rag.index_exists(index_dir)}")
    print("-" * 72)

    failures = 0
    for query in GOLDEN_QUERIES:
        qtype = rag._detect_query_type(query)
        signals = rag._extract_query_signals(query)
        expanded = rag._expand_queries(query, qtype, signals)
        rows = rag.query_kb(query, k=k, index_dir=index_dir)
        diag = rag.get_last_query_diagnostics()
        err = rag.get_last_query_error()

        print(f"\nQ: {query}")
        print(f"  type: {qtype}")
        print(f"  signals: {signals}")
        print(f"  expanded: {expanded}")
        print(
            f"  valid: {diag.get('valid')} | confidence: {diag.get('confidence')} "
            f"| note: {diag.get('validation_note')}"
        )
        if err:
            print(f"  error: {err}")
            failures += 1

        if not rows:
            print("  top chunks: (none)")
            continue

        for i, row in enumerate(rows[:3], start=1):
            meta = row.get("metadata", {})
            print(
                f"  #{i} {meta.get('filename')}:{meta.get('chunk_index')} "
                f"final={row.get('final_score', 0):.3f} meta={row.get('metadata_score', 0):.3f} "
                f"rerank={row.get('rerank_score', 0):.3f}"
            )
            print(f"      {_preview(row.get('content', ''))}")

        if qtype == "exact_identifier" and signals.get("sections"):
            top_text = (rows[0].get("content") or "").lower()
            sec = signals["sections"][0]
            if not (f"section {sec}" in top_text or re.search(rf"\b{re.escape(sec)}\b", top_text)):
                print(f"  WARN: top chunk may not contain Section {sec}")
                failures += 1

    print("\n" + "-" * 72)
    print(f"Done. failure_signals={failures}")
    return 0 if failures == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval quality.")
    parser.add_argument("--index-dir", type=str, default="", help="Path to user FAISS index directory")
    parser.add_argument("-k", type=int, default=5, help="Top-k chunks to retrieve")
    args = parser.parse_args()

    if args.index_dir:
        index_dir = Path(args.index_dir)
    else:
        index_dir = _discover_user_index()
    if not index_dir or not rag.index_exists(index_dir):
        print("No FAISS index found. Pass --index-dir faiss_indexes/user_<id>")
        sys.exit(2)

    sys.exit(run_eval(index_dir.resolve(), k=args.k))


if __name__ == "__main__":
    main()
