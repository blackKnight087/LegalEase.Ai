#!/usr/bin/env bash
set -euo pipefail
cd /opt/legalease
# Laptop .env.local on the server forces SQLite and hides Postgres users (Firm Chat search breaks).
rm -f .env.local web/.env.local 2>/dev/null || true
BASE="${1:-}"
if [ -z "$BASE" ]; then
  BASE="http://18.61.68.82"
elif [[ "$BASE" != http* ]]; then
  BASE="http://${BASE}"
fi
BASE="${BASE%/}"
API_URL="${BASE}/api"

sed -i "s|^SAAS_USE_POSTGRES_LEGACY=0|SAAS_USE_POSTGRES_LEGACY=1|" .env
bash deploy/aws/apply-ec2-tier.sh
eval "$(cat /tmp/legalease-compose.env)"
# Laptop/hybrid .env uses localhost — Docker stack needs service hostnames
sed -i 's|@localhost:5432|@postgres:5432|g' .env
sed -i 's|redis://127.0.0.1:|redis://redis:|g' .env
grep -q '^CLOUD_GEMINI_KB=' .env || echo 'CLOUD_GEMINI_KB=1' >> .env
grep -q '^REDIS_URL=' .env || echo 'REDIS_URL=redis://redis:6379/0' >> .env
sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${BASE}|" .env
sed -i "s|^PUBLIC_APP_URL=.*|PUBLIC_APP_URL=${BASE}|" .env
sed -i "s|^# NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${API_URL}|" .env
sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${API_URL}|" .env
grep -q "^NEXT_PUBLIC_API_URL=${API_URL}" .env || echo "NEXT_PUBLIC_API_URL=${API_URL}" >> .env

# EC2 has no GPU — CPU speech-to-text (tiny model fits 8GB VM)
for kv in \
  "STT_ENABLED=1" \
  "STT_ENGINE=faster_whisper" \
  "STT_MODEL=tiny" \
  "STT_DEVICE=cpu" \
  "STT_COMPUTE_TYPE=int8" \
  "STT_FALLBACK_BROWSER=1" \
  "STT_PRELOAD=0"; do
  key="${kv%%=*}"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${kv}|" .env
  else
    echo "${kv}" >> .env
  fi
done

echo "=== effective env (grep) ==="
grep -E "^(NEXT_PUBLIC|CORS|PUBLIC_APP|LLM_BACKEND|SAAS_USE_POSTGRES)" .env

export NEXT_PUBLIC_API_URL="${API_URL}"
docker compose ${LEGALEASE_COMPOSE_FILES} build api web
docker compose ${LEGALEASE_COMPOSE_FILES} up -d api web nginx
docker compose ${LEGALEASE_COMPOSE_FILES} ps
