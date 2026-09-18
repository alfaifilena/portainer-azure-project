#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

command -v openssl >/dev/null

umask 077

if [[ ! -f .env.example ]]; then
  echo "ERROR: .env.example is missing."
  exit 1
fi

if [[ ! -e .env ]]; then
  cp .env.example .env
  echo "Created .env"
else
  echo "Keeping existing .env"
fi

mkdir -p secrets
chmod 700 secrets

CERT="secrets/portainer.crt"
KEY="secrets/portainer.key"

if [[ -e "$CERT" || -e "$KEY" ]]; then
  if [[ ! -s "$CERT" || ! -s "$KEY" ]]; then
    echo "ERROR: Certificate or key is missing or empty."
    echo "Review the existing files before continuing."
    exit 1
  fi

  echo "Keeping existing certificate and key."
else
  openssl req -x509 -nodes -newkey rsa:3072 \
    -sha256 -days 365 \
    -keyout "$KEY" \
    -out "$CERT" \
    -subj "/CN=portainer" \
    -addext "subjectAltName=DNS:portainer,DNS:localhost,IP:127.0.0.1"

  echo "Created certificate and key."
fi

chmod 600 .env "$KEY"
chmod 644 "$CERT"

echo "Initialization completed."
echo "Portainer configuration has not been changed."
