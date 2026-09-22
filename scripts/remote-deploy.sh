#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Deployment modes:
# normal     = normal update/deploy
# initialize = first migration to a new persistent data disk
# recover    = restore an initialized data disk on a replacement VM
DEPLOY_MODE="${DEPLOY_MODE:-normal}"

# Important:
# Keep the same project path used by the existing containers.
REMOTE_PROJECT_ROOT="${REMOTE_PROJECT_ROOT:-/home/b2admin/portainer-azure-project}"

DATA_MOUNT="${DATA_MOUNT:-/srv/portainer-data}"
DATA_LABEL="${DATA_LABEL:-portainer-data}"

case "$DEPLOY_MODE" in
  normal|initialize|recover)
    ;;
  *)
    echo "ERROR: Invalid DEPLOY_MODE: $DEPLOY_MODE"
    echo "Allowed values: normal, initialize, recover"
    exit 1
    ;;
esac

# ------------------------------------------------------------
# Determine VM address
# ------------------------------------------------------------

if [[ -z "${VM_IP:-}" || -z "${VM_USER:-}" ]]; then

  if ! command -v terraform >/dev/null; then
    echo "ERROR: Set VM_IP and VM_USER, or install Terraform."
    exit 1
  fi

  VM_IP="${VM_IP:-$(
    terraform -chdir=terraform output -raw public_ip 2>/dev/null || true
  )}"

  if [[ -z "${VM_USER:-}" ]]; then
    SSH_CMD="$(
      terraform -chdir=terraform output -raw ssh_command 2>/dev/null || true
    )"

    VM_USER="$(
      awk '{print $2}' <<<"$SSH_CMD" |
        cut -d@ -f1
    )"
  fi
fi

if [[ -z "${VM_IP:-}" || -z "${VM_USER:-}" ]]; then
  echo "ERROR: Could not determine VM address or username."
  echo
  echo "Example:"
  echo "VM_IP=<ip> VM_USER=azureadmin bash scripts/remote-deploy.sh"
  exit 1
fi

# ------------------------------------------------------------
# SSH options
# ------------------------------------------------------------

SSH_OPTS=(
  -o ConnectTimeout=10
  -o ExitOnForwardFailure=yes
)

if [[ -n "${SSH_KEY:-}" ]]; then
  SSH_OPTS+=(
    -i "$SSH_KEY"
  )
fi

TARGET="$VM_USER@$VM_IP"

echo "========================================"
echo "Deployment mode : $DEPLOY_MODE"
echo "Target          : $TARGET"
echo "Remote project  : $REMOTE_PROJECT_ROOT"
echo "Data mount      : $DATA_MOUNT"
echo "========================================"

# ------------------------------------------------------------
# Deploy only committed code
# ------------------------------------------------------------

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "ERROR: Uncommitted tracked changes detected."
  echo "Commit your changes before deployment."
  exit 1
fi

# ------------------------------------------------------------
# Check SSH connectivity
# ------------------------------------------------------------

if ! ssh "${SSH_OPTS[@]}" \
  -o BatchMode=yes \
  "$TARGET" \
  'echo SSH_OK' >/dev/null
then
  echo "ERROR: Cannot connect to $TARGET."
  echo
  echo "Possible causes:"
  echo "- SSH key is not authorized"
  echo "- NSG does not allow your current IP"
  echo "- VM is stopped"
  echo "- Wrong VM_IP or VM_USER"
  exit 1
fi

echo "SSH connection OK."

# ------------------------------------------------------------
# Copy current Git commit to VM
# Terraform is intentionally excluded.
# .env and secrets should never be in Git.
# ------------------------------------------------------------

COMMIT="$(git rev-parse --short HEAD)"

echo "Copying commit $COMMIT to $TARGET..."

git archive \
  --format=tar \
  HEAD \
  -- . ':(exclude)terraform' |
ssh "${SSH_OPTS[@]}" "$TARGET" \
  "sudo mkdir -p '$REMOTE_PROJECT_ROOT' &&
   sudo tar -x -C '$REMOTE_PROJECT_ROOT'"

# ------------------------------------------------------------
# Execute deployment workflow remotely
# ------------------------------------------------------------

ssh "${SSH_OPTS[@]}" "$TARGET" \
  bash -s -- \
  "$DEPLOY_MODE" \
  "$REMOTE_PROJECT_ROOT" \
  "$DATA_MOUNT" \
  "$DATA_LABEL" <<'REMOTE'

set -euo pipefail

DEPLOY_MODE="$1"
PROJECT_ROOT="$2"
DATA_MOUNT="$3"
DATA_LABEL="$4"

cd "$PROJECT_ROOT"

echo
echo "Remote deployment mode: $DEPLOY_MODE"

# ------------------------------------------------------------
# Required project files
# ------------------------------------------------------------

for file in \
  scripts/docker-install.sh \
  scripts/data-disk-setup.sh \
  scripts/init.sh \
  scripts/deploy.sh \
  compose.yaml \
  demo/compose.yaml
do
  if [[ ! -e "$file" ]]; then
    echo "ERROR: Required project file missing: $file"
    exit 1
  fi
done

# ------------------------------------------------------------
# Detect persistent disk
# ------------------------------------------------------------

DATA_DEVICE="$(
  findfs "LABEL=$DATA_LABEL" 2>/dev/null || true
)"

echo "Persistent disk device: ${DATA_DEVICE:-not detected}"

# ============================================================
# NORMAL DEPLOYMENT
# ============================================================

if [[ "$DEPLOY_MODE" == "normal" ]]; then

  if ! command -v docker >/dev/null; then
    echo "Docker not installed. Installing normally..."

    sudo DEBIAN_FRONTEND=noninteractive \
      NEEDRESTART_MODE=a \
      bash scripts/docker-install.sh
  else
    echo "Docker already installed."
  fi

  # If an initialized disk is already mounted, use it.
  if mountpoint -q "$DATA_MOUNT" &&
     [[ -f "$DATA_MOUNT/.initialized" ]]
  then
    echo "Initialized persistent data disk detected."
    echo "Using existing persistent Docker/Portainer data."

  elif [[ -n "$DATA_DEVICE" ]]; then
    echo "ERROR: Persistent data disk is attached but is not"
    echo "currently detected as an initialized mounted disk."
    echo
    echo "Use one of:"
    echo "  DEPLOY_MODE=initialize"
    echo "  DEPLOY_MODE=recover"
    exit 1
  fi

  sudo bash scripts/init.sh
  sudo bash scripts/deploy.sh

# ============================================================
# FIRST DATA-DISK INITIALIZATION
# ============================================================

elif [[ "$DEPLOY_MODE" == "initialize" ]]; then

  [[ -n "$DATA_DEVICE" ]] || {
    echo "ERROR: No disk with label '$DATA_LABEL' is attached."
    exit 1
  }

  if ! command -v docker >/dev/null; then
    echo "Installing Docker normally for first deployment..."

    sudo DEBIAN_FRONTEND=noninteractive \
      NEEDRESTART_MODE=a \
      bash scripts/docker-install.sh
  fi

  # First create the application normally.
  sudo bash scripts/init.sh
  sudo bash scripts/deploy.sh

  echo
  echo "Running persistent disk migration..."

  sudo \
    PROJECT_ROOT="$PROJECT_ROOT" \
    DATA_MOUNT="$DATA_MOUNT" \
    DATA_LABEL="$DATA_LABEL" \
    DATA_DEVICE="$DATA_DEVICE" \
    bash scripts/data-disk-setup.sh --initialize

  echo
  echo "Verifying deployment after migration..."

  sudo bash scripts/init.sh
  sudo bash scripts/deploy.sh

# ============================================================
# DISASTER RECOVERY
# ============================================================

elif [[ "$DEPLOY_MODE" == "recover" ]]; then

  [[ -n "$DATA_DEVICE" ]] || {
    echo "ERROR: No persistent Portainer data disk detected."
    exit 1
  }

  echo "Recovery mode selected."

  # Install Docker but keep it stopped until the persistent
  # data disk is mounted and Docker storage is redirected.
  if ! command -v docker >/dev/null; then

    echo "Installing Docker with startup deferred..."

    sudo \
      DEFER_DOCKER_START=1 \
      DEBIAN_FRONTEND=noninteractive \
      NEEDRESTART_MODE=a \
      bash scripts/docker-install.sh

  else
    echo "Docker already installed."

    sudo systemctl stop docker.service 2>/dev/null || true
    sudo systemctl stop docker.socket 2>/dev/null || true
    sudo systemctl stop containerd.service 2>/dev/null || true
  fi

  # data-disk-setup.sh requires rsync.
  if ! command -v rsync >/dev/null; then
    echo "Installing rsync..."
    sudo apt-get update
    sudo apt-get install -y rsync
  fi

  echo
  echo "Recovering Docker and Portainer state..."

  sudo \
    PROJECT_ROOT="$PROJECT_ROOT" \
    DATA_MOUNT="$DATA_MOUNT" \
    DATA_LABEL="$DATA_LABEL" \
    DATA_DEVICE="$DATA_DEVICE" \
    bash scripts/data-disk-setup.sh --recover

  echo
  echo "Validating persistent configuration..."

  sudo bash scripts/init.sh

  echo
  echo "Validating application deployment..."

  sudo bash scripts/deploy.sh

fi

# ------------------------------------------------------------
# Final verification
# ------------------------------------------------------------

echo
echo "========================================"
echo "Final verification"
echo "========================================"

sudo docker ps

echo
sudo docker volume ls

echo
echo "Docker mounts:"

findmnt /var/lib/docker || true
findmnt /var/lib/containerd || true

if mountpoint -q "$DATA_MOUNT"; then
  echo
  echo "Persistent disk:"
  findmnt "$DATA_MOUNT"
fi

echo
echo "Deployment completed successfully."
REMOTE

echo
echo "========================================"
echo "Deployment finished"
echo "========================================"
echo "Target: $TARGET"
echo "Mode:   $DEPLOY_MODE"
echo
echo "Portainer SSH tunnel:"
echo
echo "ssh -N -o ExitOnForwardFailure=yes \\"
echo "  -L 9443:127.0.0.1:9443 \\"
echo "  -L 8081:127.0.0.1:8081 \\"
echo "  $TARGET"
echo
echo "Then open:"
echo "  https://localhost:9443"
echo "  http://localhost:8081"