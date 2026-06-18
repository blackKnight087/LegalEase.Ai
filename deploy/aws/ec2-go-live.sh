#!/usr/bin/env bash
# One-shot: production env, Cloudflare public URL (if port 80 blocked), rebuild, health check.
set -euo pipefail
cd /opt/legalease
rm -f .env.local web/.env.local 2>/dev/null || true

PUBLIC_BASE="${1:-}"
EC2_IP="$(curl -fsS http://checkip.amazonaws.com | tr -d '[:space:]')"

echo "=== LegalEase EC2 go-live (IP: ${EC2_IP}) ==="

# Core production env
sed -i 's|^SAAS_USE_POSTGRES_LEGACY=0|SAAS_USE_POSTGRES_LEGACY=1|' .env
grep -q '^SAAS_AUTO_POSTGRES_LEGACY=' .env || echo 'SAAS_AUTO_POSTGRES_LEGACY=1' >> .env
grep -q '^SAAS_PRODUCTION=' .env || echo 'SAAS_PRODUCTION=1' >> .env
for kv in STT_ENABLED=1 STT_DEVICE=cpu STT_COMPUTE_TYPE=int8 STT_FALLBACK_BROWSER=1; do
  key="${kv%%=*}"
  grep -q "^${key}=" .env && sed -i "s|^${key}=.*|${kv}|" .env || echo "${kv}" >> .env
done
bash deploy/aws/apply-ec2-tier.sh
eval "$(cat /tmp/legalease-compose.env)"

compose() {
  docker compose ${LEGALEASE_COMPOSE_FILES} "$@"
}

# Ensure stack is up before tunnel
compose up -d --build 2>&1 | tail -20

if [ -z "$PUBLIC_BASE" ]; then
  if curl -fsS -m 3 "http://${EC2_IP}/api/v1/health/live" >/dev/null 2>&1; then
    PUBLIC_BASE="http://${EC2_IP}"
    echo "Direct HTTP on ${EC2_IP} is reachable."
  else
    echo "Port 80 not reachable from internet — starting Cloudflare quick tunnel..."
    if ! command -v cloudflared >/dev/null 2>&1; then
      curl -fsSL -o /tmp/cloudflared.deb \
        https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
      sudo dpkg -i /tmp/cloudflared.deb
    fi
    sudo pkill cloudflared 2>/dev/null || true
    sleep 2
    : > /tmp/cloudflared.log
    nohup cloudflared tunnel --url "http://127.0.0.1:80" >>/tmp/cloudflared.log 2>&1 &
    URL=""
    for _ in $(seq 1 45); do
      URL="$(grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -1 || true)"
      [ -n "$URL" ] && break
      sleep 1
    done
    if [ -z "$URL" ]; then
      echo "ERROR: Cloudflare tunnel did not start. See /tmp/cloudflared.log"
      echo "Open AWS security group port 80, then re-run: bash deploy/aws/ec2-go-live.sh http://${EC2_IP}"
      exit 1
    fi
    PUBLIC_BASE="$URL"
    echo "Tunnel URL: ${PUBLIC_BASE}"
    sudo tee /etc/systemd/system/cloudflared-legalease.service >/dev/null <<EOF
[Unit]
Description=Cloudflare tunnel for LegalEase
After=network-online.target docker.service

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --url http://127.0.0.1:80
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now cloudflared-legalease.service 2>/dev/null || true
  fi
fi

PUBLIC_BASE="${PUBLIC_BASE%/}"
API_URL="${PUBLIC_BASE}/api"
TUNNEL_HOST="${PUBLIC_BASE#https://}"
TUNNEL_HOST="${TUNNEL_HOST#http://}"
TUNNEL_HOST="${TUNNEL_HOST%%/*}"

sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${PUBLIC_BASE}|" .env
sed -i "s|^PUBLIC_APP_URL=.*|PUBLIC_APP_URL=${PUBLIC_BASE}|" .env
sed -i "s|^# NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${API_URL}|" .env
sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${API_URL}|" .env
grep -q "^NEXT_PUBLIC_API_URL=${API_URL}" .env || echo "NEXT_PUBLIC_API_URL=${API_URL}" >> .env

export NEXT_PUBLIC_API_URL="${API_URL}"
export NEXT_PUBLIC_TUNNEL_HOST="${TUNNEL_HOST}"

echo "=== Rebuild api + web (API URL: ${API_URL}) ==="
compose build api web
compose up -d api web nginx

echo "=== Waiting for health ==="
for _ in $(seq 1 60); do
  if curl -fsS -m 5 "${PUBLIC_BASE}/api/v1/health/live" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

compose ps
echo ""
echo "============================================"
echo "  LegalEase is live:"
echo "  ${PUBLIC_BASE}"
echo "============================================"
curl -fsS "${PUBLIC_BASE}/api/v1/health/live" && echo ""
