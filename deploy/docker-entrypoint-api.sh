#!/bin/sh
set -e
cd /app
# Laptop overrides must never run in Docker/EC2 (breaks Postgres user search / Firm Chat).
rm -f /app/.env.local /app/web/.env.local 2>/dev/null || true
mkdir -p /data/hf_cache /data/Data 2>/dev/null || true
if [ -n "${LEGALEEASE_HF_CACHE}" ]; then
  mkdir -p "${LEGALEEASE_HF_CACHE}" 2>/dev/null || true
fi
if [ -n "${DATABASE_URL}" ] && echo "${DATABASE_URL}" | grep -q '^postgresql'; then
  echo "Running Alembic migrations..."
  alembic upgrade head || echo "Alembic upgrade skipped or failed"
fi
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-2}"
