#!/usr/bin/env bash
# Let's Encrypt HTTPS for legalease.duckdns.org on EC2
set -euo pipefail
cd /opt/legalease

HOST="${DUCKDNS_HOSTNAME:-legalease.duckdns.org}"
EMAIL="${CERTBOT_EMAIL:-}"
PUBLIC_BASE="https://${HOST}"

COMPOSE_BASE=(docker compose -f docker-compose.yml -f deploy/aws/docker-compose.override.yml)
COMPOSE_HTTPS=(docker compose -f docker-compose.yml -f deploy/aws/docker-compose.override.yml -f deploy/aws/docker-compose.https.yml)

echo "=== HTTPS setup for ${HOST} ==="

if ! command -v certbot >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq certbot
fi

echo "Stopping nginx briefly for certificate challenge..."
"${COMPOSE_BASE[@]}" stop nginx

CERT_ARGS=(certonly --standalone -d "${HOST}" --agree-tos --non-interactive --preferred-challenges http)
if [ -n "${EMAIL}" ]; then
  CERT_ARGS+=(-m "${EMAIL}")
else
  CERT_ARGS+=(--register-unsafely-without-email)
fi
sudo certbot "${CERT_ARGS[@]}"

sudo mkdir -p deploy/nginx/ssl
sudo cp "/etc/letsencrypt/live/${HOST}/fullchain.pem" deploy/nginx/ssl/cert.pem
sudo cp "/etc/letsencrypt/live/${HOST}/privkey.pem" deploy/nginx/ssl/key.pem
sudo chown ubuntu:ubuntu deploy/nginx/ssl/*.pem
chmod 600 deploy/nginx/ssl/key.pem

# Env + rebuild web for https API URL
sed -i "s|^PUBLIC_APP_URL=.*|PUBLIC_APP_URL=${PUBLIC_BASE}|" .env
sed -i "s|^NEXT_PUBLIC_APP_URL=.*|NEXT_PUBLIC_APP_URL=${PUBLIC_BASE}|" .env
sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${PUBLIC_BASE}/api|" .env
sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${PUBLIC_BASE}|" .env
sed -i 's|^FORCE_HTTPS=0|FORCE_HTTPS=1|' .env
grep -q '^FORCE_HTTPS=' .env || echo 'FORCE_HTTPS=1' >> .env

bash deploy/aws/fix-ec2-env.sh "${PUBLIC_BASE}" 2>/dev/null || true

export NEXT_PUBLIC_API_URL="${PUBLIC_BASE}/api"
"${COMPOSE_BASE[@]}" build web
"${COMPOSE_HTTPS[@]}" up -d nginx api web

sleep 5
curl -fsSk "https://127.0.0.1/api/v1/health/live" -H "Host: ${HOST}" && echo ""
echo ""
echo "Open: ${PUBLIC_BASE}"
echo "AWS security group: allow inbound TCP 443 (HTTPS) if not already."
