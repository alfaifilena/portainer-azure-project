#!/usr/bin/env bash
set -euo pipefail

# This installer targets an Ubuntu server, not Docker Desktop in WSL.
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
  echo "ERROR: This installer requires a server running systemd."
  exit 1
fi

# Stop for conflicting packages; do not remove them automatically.
for package in docker.io docker-compose docker-compose-v2 \
  docker-doc docker-buildx podman-docker containerd runc; do
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null \
    | grep -qx "install ok installed"; then
    echo "ERROR: Conflicting package found: $package"
    echo "Review the existing installation before continuing."
    exit 1
  fi
done

echo "Installing required tools..."
apt-get update
apt-get install -y ca-certificates curl openssl git

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

echo "Starting Docker..."
systemctl enable --now docker

echo "Checking the local Docker engine and Compose..."
docker --host unix:///var/run/docker.sock info >/dev/null
docker --host unix:///var/run/docker.sock version
docker compose version

echo "Docker installation checks passed."
