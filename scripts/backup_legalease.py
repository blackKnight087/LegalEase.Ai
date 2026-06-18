#!/usr/bin/env python3
"""
Backup LegalEase data: SQLite DB, FAISS indexes, Data/ folder.

Usage:
  py scripts/backup_legalease.py --out backups/2026-05-28
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else ROOT / "backups" / stamp
    out.mkdir(parents=True, exist_ok=True)

    import os

    db = Path(os.getenv("LEGALEASE_DB_PATH", str(ROOT / "legalease.db")))
    if db.is_file():
        shutil.copy2(db, out / db.name)
        print(f"Copied {db}")

    faiss = Path(os.getenv("FAISS_BASE_DIR", str(ROOT / "faiss_indexes")))
    if faiss.is_dir():
        shutil.copytree(faiss, out / "faiss_indexes", dirs_exist_ok=True)
        print(f"Copied {faiss}")

    data = ROOT / "Data"
    if data.is_dir():
        shutil.copytree(data, out / "Data", dirs_exist_ok=True)
        print(f"Copied {data}")

    print(f"Backup complete: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
