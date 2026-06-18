#!/usr/bin/env bash
set -euo pipefail
cd /opt/legalease
PW=$(grep '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2- | tr -d '\r')
if [ -z "$PW" ]; then
  echo "POSTGRES_PASSWORD missing in .env"
  exit 1
fi
docker exec legalease-postgres-1 psql -U legalease -d legalease -v ON_ERROR_STOP=1 \
  -c "ALTER USER legalease WITH PASSWORD '${PW}';"
echo "Postgres password synced to .env"
docker compose -f docker-compose.yml -f deploy/aws/docker-compose.override.yml up -d api web
sleep 20
docker compose -f docker-compose.yml -f deploy/aws/docker-compose.override.yml ps
