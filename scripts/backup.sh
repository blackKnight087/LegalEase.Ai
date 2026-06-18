#!/usr/bin/env sh
# Backup LegalEase: SQLite (if used), Postgres dump, FAISS, Data/
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="${1:-$(date -u +%Y%m%d-%H%M%S)}"
OUT="${ROOT}/backups/${STAMP}"
mkdir -p "$OUT"

echo "Backup to $OUT"

# SQLite legacy file
DB="${LEGALEASE_DB_PATH:-$ROOT/legalease.db}"
if [ -f "$DB" ]; then
  cp "$DB" "$OUT/"
  echo "Copied SQLite: $DB"
fi

# PostgreSQL (when DATABASE_URL set)
if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q '^postgresql'; then
  if command -v pg_dump >/dev/null 2>&1; then
    pg_dump "$DATABASE_URL" -Fc -f "$OUT/postgres.dump" && echo "Postgres dump: $OUT/postgres.dump"
  else
    echo "pg_dump not found — skip Postgres backup"
  fi
fi

FAISS="${FAISS_BASE_DIR:-$ROOT/faiss_indexes}"
if [ -d "$FAISS" ]; then
  cp -r "$FAISS" "$OUT/faiss_indexes"
  echo "Copied FAISS"
fi

if [ -d "$ROOT/Data" ]; then
  cp -r "$ROOT/Data" "$OUT/Data"
  echo "Copied Data/"
fi

echo "Done: $OUT"
