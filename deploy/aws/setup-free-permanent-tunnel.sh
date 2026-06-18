#!/usr/bin/env bash
# Configure named Cloudflare tunnel on EC2 → http://127.0.0.1:80 (nginx)
# Prereqs: cloudflared tunnel login + tunnel create (on laptop), scp ~/.cloudflared to EC2
set -euo pipefail

TUNNEL_NAME="${1:-legalease-aws}"
HOSTNAME="${2:-}"
TUNNEL_ID="${3:-}"

if [ -z "$HOSTNAME" ] || [ -z "$TUNNEL_ID" ]; then
  echo "Usage: $0 <tunnel-name> <hostname> <tunnel-id>"
  echo "Example: $0 legalease-aws legalease.mooo.com a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  echo ""
  echo "FreeDNS: CNAME $HOSTNAME -> ${TUNNEL_ID:-<TUNNEL_ID>}.cfargotunnel.com"
  exit 1
fi

CRED="/home/ubuntu/.cloudflared/${TUNNEL_ID}.json"
if [ ! -f "$CRED" ]; then
  echo "Missing $CRED — copy from laptop:"
  echo '  scp -i KEY -r $env:USERPROFILE\.cloudflared ubuntu@EC2:~/.cloudflared'
  exit 1
fi

sudo mkdir -p /etc/cloudflared
sudo tee /etc/cloudflared/config.yml >/dev/null <<EOF
tunnel: ${TUNNEL_NAME}
credentials-file: ${CRED}

ingress:
  - hostname: ${HOSTNAME}
    service: http://127.0.0.1:80
  - service: http_status:404
EOF

if command -v cloudflared >/dev/null 2>&1; then
  sudo cloudflared service install 2>/dev/null || true
  sudo systemctl enable cloudflared 2>/dev/null || true
  sudo systemctl restart cloudflared 2>/dev/null || sudo systemctl start cloudflared
fi

sudo systemctl stop cloudflared-legalease 2>/dev/null || true
sudo systemctl disable cloudflared-legalease 2>/dev/null || true

cd /opt/legalease
bash deploy/aws/ec2-go-live.sh "https://${HOSTNAME}"

echo ""
echo "============================================"
echo "  Free permanent link:"
echo "  https://${HOSTNAME}"
echo "============================================"
