#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Checking initialization files..."

for file in .env secrets/portainer.crt secrets/portainer.key; do
  if [[ ! -s "$file" ]]; then
    echo "ERROR: $file is missing or empty."
    echo "Run: bash scripts/init.sh"
    exit 1
  fi
done

echo "Checking Docker and required tools..."
docker info >/dev/null
docker compose version
command -v curl >/dev/null

echo "Validating Compose files..."
docker compose --env-file .env -f compose.yaml config --quiet
docker compose --env-file .env -f demo/compose.yaml config --quiet

echo "Starting Portainer..."
docker compose --env-file .env -f compose.yaml up -d \
  --pull missing --wait --wait-timeout 120 portainer

echo "Checking Portainer HTTPS..."
curl --cacert secrets/portainer.crt \
  --fail --silent --show-error \
  --retry 5 --retry-delay 2 --retry-all-errors \
  --connect-timeout 5 --max-time 10 \
  --output /dev/null \
  https://localhost:9443/api/status

echo "Starting the demo application..."
docker compose --env-file .env -f demo/compose.yaml up -d \
  --pull missing --wait --wait-timeout 120 demo-web

echo "Checking the demo page..."
curl --fail --silent --show-error \
  --max-time 10 --output /dev/null \
  http://127.0.0.1:8081/

echo "Current status:"
docker compose --env-file .env -f compose.yaml ps
docker compose --env-file .env -f demo/compose.yaml ps

echo "Deployment checks passed: Portainer HTTPS and demo HTTP."
