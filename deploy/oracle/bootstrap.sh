#!/usr/bin/env bash
# LegalEase — Oracle Cloud Always Free VM bootstrap (Ubuntu 22.04 ARM).
# Run as root or with sudo on a fresh VM.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
APP_DIR="/opt/legalease"

echo "==> LegalEase Oracle bootstrap"

apt-get update -qq
apt-get install -y -qq curl git ufw openssl ca-certificates gnupg lsb-release

# Docker
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable docker
  systemctl start docker
fi

# Ollama (host — API containers reach via host.docker.internal)
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
systemctl enable ollama || true
systemctl start ollama || true

# Firewall
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

mkdir -p "$APP_DIR"/{Data,faiss_indexes,Data/hf_cache,deploy/nginx/ssl}
chown -R ubuntu:ubuntu "$APP_DIR" 2>/dev/null || true

# Add ubuntu user to docker group
if id ubuntu >/dev/null 2>&1; then
  usermod -aG docker ubuntu
fi

echo ""
echo "Bootstrap complete."
echo "  App directory: $APP_DIR"
echo "  Next: upload/clone LegalEase into $APP_DIR"
echo "  Copy: deploy/oracle/.env.production.example -> $APP_DIR/.env"
echo "  Then: cd $APP_DIR && docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.override.yml up -d --build"
echo "  Ollama: ollama pull qwen2.5:7b  (or create legalease-tuned from Modelfile)"
echo "  Docs: docs/DEPLOY_ORACLE_FREE.md"
