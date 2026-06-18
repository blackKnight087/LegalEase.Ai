#!/usr/bin/env python3
"""Quick project health check — KB paths, deps, and debug log summary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    failures: list[str] = []
    print("LegalEase project health check\n")

    # Embeddings
    try:
        from llms import get_embeddings_status

        st = get_embeddings_status()
        ready = bool(st.get("ready"))
        print(f"  Embeddings: {'READY' if ready else 'NOT READY'} model={st.get('model', '?')[:50]}")
        if not ready:
            failures.append("embeddings_not_ready")
    except Exception as exc:
        print(f"  Embeddings: ERROR {exc}")
        failures.append("embeddings_error")

    # KB orchestrator (user index if present)
    uid = "94703e96-51fb-493e-a3c6-6fd2b1521c0c"
    idx = ROOT / "faiss_indexes" / f"user_{uid}" / "_unlinked"
    if idx.exists():
        from backend.app.services.legal_orchestrator_v2 import run_legal_orchestrator_v2

        for q in (
            "Difference between IPC 299 and IPC 300",
            "Explain IPC Section 307",
            "307 punishment",
        ):
            ans, _, meta = run_legal_orchestrator_v2(uid, q)
            ok = bool(ans) and meta.get("found") is not False
            boiler = "rigorously test" in (ans or "").lower()
            print(f"  KB [{q[:40]}]: {'OK' if ok else 'FAIL'} boilerplate={boiler}")
            if not ok:
                failures.append(f"kb_fail:{q[:30]}")
            if boiler:
                failures.append(f"kb_boilerplate:{q[:30]}")
    else:
        print(f"  KB index: skip (no index at {idx})")

    # LLM finetune deps
    try:
        from backend.app.core.llm_finetuning import _local_gpu_available, _training_deps_ok

        deps, err = _training_deps_ok()
        gpu = _local_gpu_available()
        print(f"  LLM finetune deps: {'OK' if deps else err}")
        print(f"  CUDA GPU: {'yes' if gpu else 'no (training skipped on CPU)'}")
    except Exception as exc:
        print(f"  LLM finetune: {exc}")

    log_path = ROOT / "debug-c6a094.log"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        print(f"\n  Debug log: {len(lines)} entries in debug-c6a094.log")
        for line in lines[-5:]:
            try:
                o = json.loads(line)
                print(f"    - {o.get('hypothesisId')} {o.get('message')} {str(o.get('data', {}))[:80]}")
            except Exception:
                pass

    print()
    if failures:
        print("FAILED:", ", ".join(failures))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
