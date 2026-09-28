#!/usr/bin/env bash
set -euo pipefail

if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then
  echo "STOP: This script is for the Azure server, not WSL."
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: Run this script with sudo on the server."
  exit 1
fi

if [[ ! -d /run/systemd/system ]]; then
  echo "ERROR: This script requires a server running systemd."
  exit 1
fi

SSHD_CONFIG="/etc/ssh/sshd_config"
BACKUP="${SSHD_CONFIG}.before-hardening.$(date +%Y%m%d%H%M%S)"

echo "=========================================================="
echo "WARNING: this script disables SSH password login."
echo "Make sure key-based login already works before continuing:"
echo "  - You are connected right now over SSH using a key, AND"
echo "  - You will keep this session open and verify with a"
echo "    SECOND ssh session before closing this one."
echo "=========================================================="
read -r -p "Type 'yes' to continue: " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Aborted. Nothing was changed."
  exit 1
fi

echo "Installing required tools..."
apt-get update
apt-get install -y ufw unattended-upgrades

echo "Configuring the firewall (ufw)..."
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable
ufw status verbose

echo "Backing up sshd_config to $BACKUP ..."
cp "$SSHD_CONFIG" "$BACKUP"

echo "Hardening SSH configuration..."
# Use a dedicated drop-in file instead of editing sshd_config directly,
# so the change is easy to find and to revert.
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/99-hardening.conf <<'EOF'
# Added by scripts/harden.sh — key-based login only.
PasswordAuthentication no
PermitRootLogin no
EOF

echo "Validating the new SSH configuration..."
sshd -t

echo "Reloading SSH..."
systemctl reload ssh || systemctl reload sshd

echo "Enabling automatic security updates..."
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now unattended-upgrades

echo "=========================================================="
echo "Hardening applied."
echo "IMPORTANT: before closing this session, open a NEW terminal"
echo "and confirm you can still connect:"
echo "  ssh azureadmin@<VM_IP>"
echo "If the new connection fails, restore the backup with:"
echo "  sudo cp $BACKUP $SSHD_CONFIG"
echo "  sudo rm -f /etc/ssh/sshd_config.d/99-hardening.conf"
echo "  sudo systemctl reload ssh"
echo "=========================================================="
