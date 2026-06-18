#!/usr/bin/env bash
# Print EC2 memory tier: low (<12GB), medium (12-23GB), high (24GB+)
set -euo pipefail
MEM_MB="$(awk '/^Mem:/{print $2}' /proc/meminfo)"
MEM_GB=$((MEM_MB / 1024))
if [ "$MEM_GB" -ge 24 ]; then
  echo "high"
elif [ "$MEM_GB" -ge 12 ]; then
  echo "medium"
else
  echo "low"
fi
