#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

DATA_MOUNT="${DATA_MOUNT:-/srv/portainer-data}"
PERSISTENT_CONFIG="$DATA_MOUNT/config"

command -v openssl >/dev/null

umask 077

if [[ ! -f .env.example ]]; then
  echo "ERROR: .env.example is missing."
  exit 1
fi

# ------------------------------------------------------------
# If an initialized persistent data disk is available,
# use its existing configuration instead of generating new data.
# ------------------------------------------------------------

if mountpoint -q "$DATA_MOUNT" 2>/dev/null &&
   [[ -f "$DATA_MOUNT/.initialized" ]]; then

  echo "Persistent Portainer data disk detected."

  if [[ ! -s "$PERSISTENT_CONFIG/.env" ]]; then
    echo "ERROR: Persistent .env is missing or empty."
    exit 1
  fi

  if [[ ! -s "$PERSISTENT_CONFIG/secrets/portainer.crt" ||
        ! -s "$PERSISTENT_CONFIG/secrets/portainer.key" ]]; then
    echo "ERROR: Persistent Portainer certificate or key is missing."
    exit 1
  fi

  # data-disk-setup.sh should normally create these links.
  # Refuse to silently overwrite unrelated local configuration.

  if [[ -e .env || -L .env ]]; then
    if [[ ! -L .env ]]; then
      echo "ERROR: .env exists locally but is not linked to persistent storage."
      echo "Run data-disk-setup.sh --recover first."
      exit 1
    fi
  else
    ln -s "$PERSISTENT_CONFIG/.env" .env
  fi

  if [[ -e secrets || -L secrets ]]; then
    if [[ ! -L secrets ]]; then
      echo "ERROR: secrets exists locally but is not linked to persistent storage."
      echo "Run data-disk-setup.sh --recover first."
      exit 1
    fi
  else
    ln -s "$PERSISTENT_CONFIG/secrets" secrets
  fi

  echo "Using persistent .env and TLS certificates."

else

  # ----------------------------------------------------------
  # First installation before persistent-disk migration.
  # Create local configuration normally.
  # ----------------------------------------------------------

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
fi

chmod 600 .env
chmod 600 secrets/portainer.key
chmod 644 secrets/portainer.crt

echo "Initialization completed."
echo "Existing persistent Portainer configuration was preserved."