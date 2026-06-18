#!/usr/bin/env bash
# Point DuckDNS at this EC2 instance and align LegalEase env for HTTP on port 80.
set -euo pipefail
cd /opt/legalease

DOMAIN="${DUCKDNS_DOMAIN:-legalease}"
HOSTNAME="${DUCKDNS_HOSTNAME:-legalease.duckdns.org}"
EC2_IP="$(curl -fsS http://checkip.amazonaws.com | tr -d '[:space:]')"
PUBLIC_BASE="${1:-http://${HOSTNAME}}"

echo "=== DuckDNS + LegalEase (EC2 IP: ${EC2_IP}) ==="

# Optional: update DuckDNS A record (set DUCKDNS_TOKEN in /opt/legalease/.env)
DUCKDNS_TOKEN=""
if [ -f .env ]; then
  DUCKDNS_TOKEN="$(grep '^DUCKDNS_TOKEN=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true)"
fi
if [ -n "${DUCKDNS_TOKEN:-}" ]; then
  echo "Updating DuckDNS domain ${DOMAIN} -> ${EC2_IP}"
  curl -fsS "https://www.duckdns.org/update?domains=${DOMAIN}&token=${DUCKDNS_TOKEN}&ip=${EC2_IP}" || true
  echo ""
else
  echo "WARN: DUCKDNS_TOKEN not in .env — set A record manually at https://www.duckdns.org to ${EC2_IP}"
fi

# HTTP until TLS is configured (nginx listens on :80 only)
PUBLIC_BASE="${PUBLIC_BASE%/}"
API_URL="${PUBLIC_BASE}/api"

sed -i "s|^PUBLIC_APP_URL=.*|PUBLIC_APP_URL=${PUBLIC_BASE}|" .env
sed -i "s|^NEXT_PUBLIC_APP_URL=.*|NEXT_PUBLIC_APP_URL=${PUBLIC_BASE}|" .env
sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${API_URL}|" .env
sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${PUBLIC_BASE}|" .env
sed -i 's|^FORCE_HTTPS=1|FORCE_HTTPS=0|' .env
grep -q '^FORCE_HTTPS=' .env || echo 'FORCE_HTTPS=0' >> .env

bash deploy/aws/fix-ec2-env.sh "${PUBLIC_BASE}"
bash deploy/aws/fix-postgres-password.sh 2>/dev/null || true

export NEXT_PUBLIC_API_URL="${API_URL}"
compose() {
  docker compose -f docker-compose.yml -f deploy/aws/docker-compose.override.yml "$@"
}
compose build web
compose up -d api web nginx

echo ""
echo "=== Verify on EC2 ==="
curl -fsS "http://127.0.0.1/api/v1/health/live" && echo ""
echo ""
echo "=== From your laptop (after AWS security group allows HTTP :80) ==="
echo "  curl http://${HOSTNAME}/api/v1/health/live"
echo "  Open: ${PUBLIC_BASE}"
echo ""
echo "If that times out, open inbound TCP 80 on the EC2 security group (see deploy/aws/OPEN_PORT_80.md)."
