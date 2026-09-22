#!/usr/bin/env bash
set -euo pipefail

DEFER_DOCKER_START="${DEFER_DOCKER_START:-0}"

if grep -qi microsoft /proc/sys/kernel/osrelease; then
  echo "STOP: This installer is for the Ubuntu server."
  echo "In WSL, use Docker Desktop integration."
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: Run this script with sudo on the server."
  exit 1
fi

source /etc/os-release

if [[ "$ID" != "ubuntu" ]]; then
  echo "ERROR: This script supports Ubuntu only."
  exit 1
fi

case "$VERSION_ID" in
  22.04|24.04|26.04) ;;
  *)
    echo "ERROR: Ubuntu version not supported by this script."
    exit 1
    ;;
esac

if [[ ! -d /run/systemd/system ]]; then
  echo "ERROR: This installer requires systemd."
  exit 1
fi

# If Docker CE is already installed, do not reinstall it.
if command -v docker >/dev/null 2>&1 &&
   dpkg-query -W -f='${Status}' docker-ce 2>/dev/null |
     grep -qx "install ok installed"; then

  echo "Docker CE is already installed."

else
  # Reject conflicting packages only for a fresh installation.
  for package in \
    docker.io \
    docker-compose \
    docker-compose-v2 \
    docker-doc \
    docker-buildx \
    podman-docker \
    containerd \
    runc
  do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null |
      grep -qx "install ok installed"; then

      echo "ERROR: Conflicting package found: $package"
      echo "Review the existing installation before continuing."
      exit 1
    fi
  done

  echo "Installing required tools..."
  apt-get update
  apt-get install -y ca-certificates curl openssl git rsync

  echo "Adding the official Docker repository..."
  install -m 0755 -d /etc/apt/keyrings

  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc

  chmod a+r /etc/apt/keyrings/docker.asc

  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

  echo "Installing Docker and Compose..."
  apt-get update

  apt-get install -y --no-upgrade \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
fi

echo "Checking Docker CLI and Compose..."
docker --version
docker compose version

if [[ "$DEFER_DOCKER_START" == "1" ]]; then
  echo "Persistent-disk/recovery mode detected."
  echo "Docker will remain stopped until data-disk setup is complete."

  systemctl enable containerd.service docker.service

  systemctl stop docker.service 2>/dev/null || true
  systemctl stop docker.socket 2>/dev/null || true
  systemctl stop containerd.service 2>/dev/null || true

  echo "Docker installation completed with startup deferred."

else
  echo "Starting Docker normally..."

  systemctl enable --now containerd.service
  systemctl enable --now docker.service

  docker --host unix:///var/run/docker.sock info >/dev/null
  docker --host unix:///var/run/docker.sock version

  echo "Docker installation checks passed."
fi