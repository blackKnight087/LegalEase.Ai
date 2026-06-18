#!/usr/bin/env python3
"""KB pipeline smoke test — run without live FAISS/LLM. Exit 0 = pass."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kb_query_types import QueryType, detect_query_type, extract_entities, needs_document_wide_scan
from kb_rag_decision import evaluate_retrieval
from kb_validate import validate_answer


def _sample_chunks():
    return [
        {"content": "IPC Section 300 — Murder.", "final_score": 0.8, "entity": "300"},
        {"content": "IPC Section 307 — Attempt to Murder.", "final_score": 0.75, "entity": "307"},
        {"content": "IPC Section 299 — Culpable Homicide.", "final_score": 0.7},
        {"content": "IT Act Section 66C — Identity Theft.", "final_score": 0.65},
    ]


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise SystemExit(1)


def main() -> None:
    print("LegalEase KB smoke test\n")
    chunks = _sample_chunks()

    # Comparison entities
    ent = extract_entities("section 300 and 307 difference")
    check("comparison entities", ent["entities"] == ["300", "307"], str(ent))

    # Document scan intent
    qt = detect_query_type("Summarize all criminal offences discussed")
    check("summary/list scan", needs_document_wide_scan(qt, "Summarize all criminal offences discussed"))

    # Retrieval gate
    found, _, dec, _ = evaluate_retrieval(
        "300 vs 307",
        chunks[:2],
        entities=["300", "307"],
        query_type="comparison",
    )
    check("comparison FOUND gate", found and dec == "FOUND")

    # Validation
    answer = (
        "# IPC 300 vs IPC 307\n\n"
        "| Aspect | IPC 300 | IPC 307 |\n|---|---|---|\n"
        "## Key Difference\nIPC 300 is murder. IPC 307 is attempt."
    )
    ok, reason = validate_answer(
        answer,
        "Difference 300 and 307",
        chunks[:2],
        QueryType.COMPARISON,
        profile_sections=["300", "307"],
    )
    check("comparison validation", ok, reason)

    from kb_document_scan import extract_all_offences_from_chunks

    offences = extract_all_offences_from_chunks(chunks)
    check("offence extraction count", len(offences) >= 3, f"found {len(offences)}")

    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    main()
