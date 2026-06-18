#!/usr/bin/env bash
# Apply memory-tier compose overlays and production env defaults.
set -euo pipefail
cd /opt/legalease

TIER="$(bash deploy/aws/detect-ec2-tier.sh)"
echo "=== EC2 memory tier: ${TIER} ==="

COMPOSE_FILES="-f docker-compose.yml -f deploy/aws/docker-compose.override.yml"
if [ "$TIER" != "low" ]; then
  COMPOSE_FILES="${COMPOSE_FILES} -f deploy/aws/docker-compose.highmem.yml"
fi
if [ -f deploy/nginx/ssl/cert.pem ] && [ -f deploy/nginx/ssl/key.pem ]; then
  COMPOSE_FILES="${COMPOSE_FILES} -f deploy/aws/docker-compose.https.yml"
fi
export LEGALEASE_COMPOSE_FILES="${COMPOSE_FILES}"

# Production hygiene
for kv in \
  "KB_RETRIEVAL_DEBUG=0" \
  "CORS_ALLOW_LOCALHOST_REGEX=0" \
  "OLLAMA_AUTO_START=0" \
  "OLLAMA_AUTO_CREATE=0" \
  "IMPROVEMENT_AUTO=0" \
  "COACH_AUTO_SCHEDULE=0" \
  "SAAS_ALLOW_FREE_HYBRID=1" \
  "SAAS_ALL_FEATURES_FREE=1"; do
  key="${kv%%=*}"
  grep -q "^${key}=" .env 2>/dev/null && sed -i "s|^${key}=.*|${kv}|" .env || echo "${kv}" >> .env
done

# LLM: Gemini on low-RAM; Ollama only when explicitly enabled AND enough RAM
if grep -q '^USE_OLLAMA_EC2=1' .env 2>/dev/null && [ "$TIER" != "low" ]; then
  echo "Using Ollama (USE_OLLAMA_EC2=1)"
  for kv in \
    "LLM_BACKEND=ollama" \
    "CLOUD_GEMINI_KB=0" \
    "OLLAMA_URL=http://host.docker.internal:11434" \
    "OLLAMA_NUM_GPU=0"; do
    key="${kv%%=*}"
    sed -i "s|^${key}=.*|${kv}|" .env 2>/dev/null || echo "${kv}" >> .env
  done
else
  sed -i 's|^LLM_BACKEND=ollama|LLM_BACKEND=gemini|g' .env
  grep -q '^CLOUD_GEMINI_KB=' .env || echo 'CLOUD_GEMINI_KB=1' >> .env
  sed -i 's|^CLOUD_GEMINI_KB=0|CLOUD_GEMINI_KB=1|' .env 2>/dev/null || true
fi

if [ "$TIER" = "high" ]; then
  grep -q '^ML_USE_QUEUE=' .env || echo 'ML_USE_QUEUE=1' >> .env
  sed -i 's|^ML_USE_QUEUE=0|ML_USE_QUEUE=1|' .env 2>/dev/null || true
  sed -i 's|^LOW_RESOURCE_MODE=1|LOW_RESOURCE_MODE=0|' .env 2>/dev/null || true
  sed -i 's|^STT_MODEL=tiny|STT_MODEL=small|' .env 2>/dev/null || true
elif [ "$TIER" = "medium" ]; then
  grep -q '^ML_USE_QUEUE=' .env || echo 'ML_USE_QUEUE=1' >> .env
  sed -i 's|^LOW_RESOURCE_MODE=1|LOW_RESOURCE_MODE=0|' .env 2>/dev/null || true
else
  grep -q '^ML_USE_QUEUE=' .env || echo 'ML_USE_QUEUE=0' >> .env
  grep -q '^LOW_RESOURCE_MODE=' .env || echo 'LOW_RESOURCE_MODE=1' >> .env
fi

printf 'LEGALEASE_COMPOSE_FILES="%s"\n' "${COMPOSE_FILES}" > /tmp/legalease-compose.env
echo "LEGALEASE_COMPOSE_FILES=${COMPOSE_FILES}"
