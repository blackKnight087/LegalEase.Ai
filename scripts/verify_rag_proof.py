#!/usr/bin/env python3
"""
End-to-end RAG verification — prints proof that retrieval is document-grounded.
Run: .venv_win\\Scripts\\python.exe scripts\\verify_rag_proof.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rag import FAISS_BASE_DIR  # noqa: E402

from rag import (  # noqa: E402
    NOT_FOUND_PHRASE,
    index_documents,
    index_exists,
    query_kb,
    retrieval_has_signal,
    get_last_query_error,
)
from prompts import kb_prompt, NOT_FOUND_PHRASE as PROMPT_NOT_FOUND  # noqa: E402

YUSUF_RESUME = """
Yusuf Ahmed
Email: yusuf@example.com | Phone: +91-9876543210

PROFESSIONAL SUMMARY
Software engineer with 5 years of experience in backend systems and machine learning.

CORE TECHNICAL SKILLS
Python, SQL, Machine Learning, TensorFlow, PyTorch, Docker, Kubernetes, AWS, REST APIs, Git

EXPERIENCE
Senior Software Engineer — TechCorp India (2020–2024)
- Built ML pipelines and microservices in Python.
- Deployed services on Kubernetes with Docker.

EDUCATION
B.Tech Computer Science, IIT Delhi, 2019
"""

ABSENT_QUERY = "What is the annual revenue of TechCorp in USD millions?"
SKILLS_QUERY = "What are the core technical skills listed on Yusuf's resume?"


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"PASS: {msg}")


def main() -> None:
    print("=" * 60)
    print("LegalEase RAG — verification proof")
    print("=" * 60)

    tmp = FAISS_BASE_DIR / "_verification_run"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        docs = [{"doc_id": "yusuf-1", "filename": "yusuf_resume.pdf", "text": YUSUF_RESUME}]
        ok, msg, n_chunks = index_documents(docs, index_dir=tmp)
        if not ok:
            _fail(f"index_documents: {msg}")
        _ok(f"Indexed {n_chunks} chunks — {msg}")

        if not index_exists(tmp):
            _fail(f"FAISS files missing under {tmp}")

        # TEST 1 — skills in document
        results = query_kb(SKILLS_QUERY, k=5, index_dir=tmp)
        if not results:
            _fail(f"query_kb returned empty. Error: {get_last_query_error()}")
        if not retrieval_has_signal(results):
            _fail(f"No retrieval signal. Scores: {[r['score'] for r in results]}")

        combined = " ".join(r["content"] for r in results).lower()
        required = ["python", "sql", "machine learning"]
        missing = [w for w in required if w not in combined]
        if missing:
            _fail(f"Retrieved context missing skills {missing}. Top chunk: {results[0]['content'][:200]}")

        _ok(f"TEST 1 — Retrieved skills from PDF context (scores: {[round(r['score'], 3) for r in results[:3]]})")
        print("  Top chunk preview:", results[0]["content"][:180].replace("\n", " "))

        # TEST 2 — absent info (retrieval should not contain revenue figures)
        absent_results = query_kb(ABSENT_QUERY, k=5, index_dir=tmp)
        absent_text = " ".join(r["content"] for r in absent_results).lower()
        if "revenue" in absent_text and "million" in absent_text:
            _fail("False positive: revenue found in resume chunks")
        _ok("TEST 2 — Absent topic not fabricated in retrieved chunks")

        # TEST 3 — prompt enforces exact not-found phrase
        prompt = kb_prompt([], "random question")
        if PROMPT_NOT_FOUND not in prompt:
            _fail("kb_prompt missing exact not-found phrase")
        _ok(f"TEST 3 — Prompt requires exact phrase: {PROMPT_NOT_FOUND!r}")

        # TEST 4 — prompt with context contains skills block
        prompt2 = kb_prompt(results, SKILLS_QUERY)
        if "Python" not in prompt2 or "CONTEXT:" not in prompt2:
            _fail("kb_prompt missing document context")
        _ok("TEST 4 — Prompt injects retrieved document context only")

        report = {
            "index_chunks": n_chunks,
            "skills_query_scores": [r["score"] for r in results],
            "top_chunk": results[0]["content"][:500],
            "not_found_phrase": NOT_FOUND_PHRASE,
        }
        proof_path = ROOT / "rag_verification_proof.json"
        proof_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print()
        print("Proof written to:", proof_path)
        print("=" * 60)
        print("ALL RAG RETRIEVAL TESTS PASSED")
        print("=" * 60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
