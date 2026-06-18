#!/usr/bin/env bash
# Install Ollama on EC2 host and create legalease-tuned (requires 16GB+ RAM).
set -euo pipefail
cd /opt/legalease

MEM_GB="$(awk '/^Mem:/{print int($2/1024)}' /proc/meminfo)"
if [ "$MEM_GB" -lt 16 ]; then
  echo "ERROR: Ollama legalease-tuned (llama3.1:8b) needs at least 16GB RAM."
  echo "       This instance has ~${MEM_GB}GB. Upgrade to t3.xlarge (16GB) or larger."
  echo "       Until then, keep LLM_BACKEND=gemini (current AWS default)."
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "=== Installing Ollama ==="
  curl -fsSL https://ollama.com/install.sh | sh
fi

sudo systemctl enable ollama 2>/dev/null || true
sudo systemctl start ollama 2>/dev/null || true
sleep 2

echo "=== Pulling base model (llama3.1:8b) — may take several minutes ==="
ollama pull llama3.1:8b

MODELFILE="deploy/aws/Modelfile.legalease"
if [ ! -f "$MODELFILE" ]; then
  echo "ERROR: Missing $MODELFILE"
  exit 1
fi

echo "=== Creating legalease-tuned ==="
ollama create legalease-tuned -f "$MODELFILE" || ollama create legalease-tuned -f "$MODELFILE" --force 2>/dev/null || true

# Wire API container to host Ollama
for kv in \
  "USE_OLLAMA_EC2=1" \
  "LLM_BACKEND=ollama" \
  "CLOUD_GEMINI_KB=0" \
  "OLLAMA_URL=http://host.docker.internal:11434" \
  "OLLAMA_BASE_URL=http://host.docker.internal:11434" \
  "OLLAMA_MODEL=legalease-tuned" \
  "OLLAMA_NUM_GPU=0" \
  "OLLAMA_NUM_THREAD=4" \
  "OLLAMA_AUTO_START=0" \
  "OLLAMA_AUTO_CREATE=0" \
  "IMPROVEMENT_AUTO=0" \
  "COACH_AUTO_SCHEDULE=0"; do
  key="${kv%%=*}"
  grep -q "^${key}=" .env && sed -i "s|^${key}=.*|${kv}|" .env || echo "${kv}" >> .env
done

echo "=== Ollama ready ==="
ollama list
echo ""
echo "Restart API: docker compose ... up -d api"
echo "Test: curl http://127.0.0.1:11434/api/tags"
