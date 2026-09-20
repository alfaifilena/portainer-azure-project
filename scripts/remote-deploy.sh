#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

REMOTE_DIR="${REMOTE_DIR:-portainer-azure-project}"

# 1) عنوان الخادم: من المتغيرات أولاً، وإلا من terraform output (public_ip و ssh_command)
if [[ -z "${VM_IP:-}" || -z "${VM_USER:-}" ]]; then
  if ! command -v terraform >/dev/null; then
    echo "ERROR: Set VM_IP and VM_USER, or install terraform with access to the state."
    exit 1
  fi
  # outputs.tf: public_ip, and ssh_command = "ssh <user>@<ip>"
  VM_IP="${VM_IP:-$(terraform -chdir=terraform output -raw public_ip 2>/dev/null || true)}"
  if [[ -z "${VM_USER:-}" ]]; then
    SSH_CMD="$(terraform -chdir=terraform output -raw ssh_command 2>/dev/null || true)"
    VM_USER="$(awk '{print $2}' <<<"$SSH_CMD" | cut -d@ -f1)"
  fi
fi

if [[ -z "${VM_IP:-}" || -z "${VM_USER:-}" ]]; then
  echo "ERROR: Could not determine the VM address."
  echo "Terraform state is usually only on the infrastructure owner's machine."
  echo "Run with: VM_IP=<ip> VM_USER=<user> bash scripts/remote-deploy.sh"
  exit 1
fi

SSH_OPTS=(-o ConnectTimeout=10)
if [[ -n "${SSH_KEY:-}" ]]; then
  SSH_OPTS+=(-i "$SSH_KEY")
fi
TARGET="$VM_USER@$VM_IP"

echo "Target: $TARGET  (remote dir: ~/$REMOTE_DIR)"

# 2) نرفض النشر إذا فيه تعديلات غير محفوظة، لأن الخادم ياخذ آخر commit فقط
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "ERROR: You have uncommitted changes. Commit them first; only committed code is deployed."
  exit 1
fi

# 3) تحقق من الاتصال قبل أي شيء
if ! ssh "${SSH_OPTS[@]}" -o BatchMode=yes "$TARGET" 'echo SSH_OK' >/dev/null; then
  echo "ERROR: Cannot connect to $TARGET."
  echo "Timed out: your IP may have changed (curl -s https://ifconfig.me) or the VM is stopped."
  echo "Permission denied: your public key is not on the VM."
  exit 1
fi
echo "SSH connection OK."

# 4) انسخ آخر commit فقط (بدون .git و terraform)
echo "Copying commit $(git rev-parse --short HEAD) to the VM..."
git archive --format=tar HEAD -- . ':(exclude)terraform' | \
  ssh "${SSH_OPTS[@]}" "$TARGET" "mkdir -p ~/$REMOTE_DIR && tar -x -C ~/$REMOTE_DIR"

# 5) شغّل التسلسل على الخادم (بدون أسئلة تفاعلية)
ssh "${SSH_OPTS[@]}" "$TARGET" "REMOTE_DIR=$REMOTE_DIR bash -s" <<'REMOTE'
set -euo pipefail
cd ~/"$REMOTE_DIR"

if ! command -v docker >/dev/null; then
  sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a bash scripts/docker-install.sh
else
  echo "Docker already installed, skipping installation."
fi

sudo bash scripts/init.sh
sudo bash scripts/deploy.sh
REMOTE

echo
echo "Deployment finished on $TARGET."
echo "Open the tunnel from your machine:"
echo "  ssh -N -o ExitOnForwardFailure=yes -L 9443:127.0.0.1:9443 -L 8081:127.0.0.1:8081 $TARGET"
echo "Then open: https://localhost:9443"
echo "First login only, get the setup token on the VM with:"
echo "  sudo docker compose --env-file .env -f compose.yaml logs --tail 30 portainer"