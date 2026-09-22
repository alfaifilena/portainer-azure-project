#!/usr/bin/env bash
set -Eeuo pipefail

DATA_MOUNT="${DATA_MOUNT:-/srv/portainer-data}"
PORTAINER_CONTAINER="${PORTAINER_CONTAINER:-portainer}"
PORTAINER_VOLUME="${PORTAINER_VOLUME:-container-hub_portainer_data}"

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

die() {
  echo "[ERROR] $*" >&2
  exit 1
}

log() {
  echo "[INFO] $*"
}

if [[ "$EUID" -ne 0 ]]; then
  die "Run this script with sudo/root."
fi

if [[ $# -ne 1 ]]; then
  echo "Usage:"
  echo "  sudo bash scripts/restore.sh <backup-file.tar.gz>"
  exit 1
fi

BACKUP_FILE="$1"

[[ -f "$BACKUP_FILE" ]] || \
  die "Backup file not found: $BACKUP_FILE"

mountpoint -q "$DATA_MOUNT" || \
  die "Persistent data disk is not mounted at $DATA_MOUNT."

[[ -f "$DATA_MOUNT/.initialized" ]] || \
  die "Persistent data disk is not initialized."

command -v docker >/dev/null || die "Docker is not installed."
command -v rsync >/dev/null || die "rsync is not installed."
command -v tar >/dev/null || die "tar is not installed."

echo "=== Portainer Restore ==="
echo "Backup file: $BACKUP_FILE"
echo "Data disk:   $DATA_MOUNT"
echo

# ------------------------------------------------------------
# Validate archive
# ------------------------------------------------------------

log "Validating backup archive..."

tar -tzf "$BACKUP_FILE" >/dev/null || \
  die "Backup archive is invalid or corrupted."

TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

log "Extracting backup..."

tar -xzf "$BACKUP_FILE" -C "$TMP_DIR"

BACKUP_ROOT="$(
  find "$TMP_DIR" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    | head -n 1
)"

[[ -n "$BACKUP_ROOT" ]] || \
  die "Could not find backup directory inside archive."

[[ -d "$BACKUP_ROOT/portainer-volume" ]] || \
  die "Backup does not contain Portainer volume data."

if [[ -f "$BACKUP_ROOT/backup-info.txt" ]]; then
  echo
  echo "Backup information:"
  cat "$BACKUP_ROOT/backup-info.txt"
  echo
fi

# ------------------------------------------------------------
# Ensure Docker volume exists
# ------------------------------------------------------------

if ! docker volume inspect "$PORTAINER_VOLUME" >/dev/null 2>&1; then
  log "Creating Docker volume: $PORTAINER_VOLUME"
  docker volume create "$PORTAINER_VOLUME" >/dev/null
fi

VOLUME_PATH="$(
  docker volume inspect \
    --format '{{.Mountpoint}}' \
    "$PORTAINER_VOLUME"
)"

[[ -d "$VOLUME_PATH" ]] || \
  die "Docker volume mountpoint not found: $VOLUME_PATH"

# ------------------------------------------------------------
# Stop Portainer
# ------------------------------------------------------------

PORTAINER_WAS_RUNNING=0

if [[ "$(docker inspect -f '{{.State.Running}}' \
  "$PORTAINER_CONTAINER" 2>/dev/null || true)" == "true" ]]; then

  PORTAINER_WAS_RUNNING=1

  log "Stopping Portainer..."
  docker stop "$PORTAINER_CONTAINER" >/dev/null
fi

# ------------------------------------------------------------
# Create safety copy before restore
# ------------------------------------------------------------

STAMP="$(date +%Y%m%d_%H%M%S)"
SAFETY_DIR="$DATA_MOUNT/restore-safety/pre-restore-$STAMP"

log "Creating pre-restore safety copy..."

mkdir -p "$SAFETY_DIR/portainer-volume"

rsync \
  -aHAXS \
  --numeric-ids \
  "$VOLUME_PATH/" \
  "$SAFETY_DIR/portainer-volume/"

if [[ -d "$DATA_MOUNT/config" ]]; then
  mkdir -p "$SAFETY_DIR/config"

  rsync \
    -aHAXS \
    "$DATA_MOUNT/config/" \
    "$SAFETY_DIR/config/"
fi

# ------------------------------------------------------------
# Restore Portainer volume
# ------------------------------------------------------------

log "Restoring Portainer volume..."

rsync \
  -aHAXS \
  --numeric-ids \
  --delete \
  "$BACKUP_ROOT/portainer-volume/" \
  "$VOLUME_PATH/"

# ------------------------------------------------------------
# Restore persistent configuration
# ------------------------------------------------------------

if [[ -d "$BACKUP_ROOT/config" ]]; then

  log "Restoring persistent configuration..."

  mkdir -p "$DATA_MOUNT/config"

  if [[ -f "$BACKUP_ROOT/config/.env" ]]; then
    cp -a \
      "$BACKUP_ROOT/config/.env" \
      "$DATA_MOUNT/config/.env"
  fi

  if [[ -d "$BACKUP_ROOT/config/secrets" ]]; then

    mkdir -p "$DATA_MOUNT/config/secrets"

    rsync \
      -aHAXS \
      --delete \
      "$BACKUP_ROOT/config/secrets/" \
      "$DATA_MOUNT/config/secrets/"
  fi
fi

# ------------------------------------------------------------
# Permissions
# ------------------------------------------------------------

if [[ -f "$DATA_MOUNT/config/.env" ]]; then
  chmod 600 "$DATA_MOUNT/config/.env"
fi

if [[ -f "$DATA_MOUNT/config/secrets/portainer.key" ]]; then
  chmod 600 "$DATA_MOUNT/config/secrets/portainer.key"
fi

if [[ -f "$DATA_MOUNT/config/secrets/portainer.crt" ]]; then
  chmod 644 "$DATA_MOUNT/config/secrets/portainer.crt"
fi

# ------------------------------------------------------------
# Start Portainer again
# ------------------------------------------------------------

if [[ "$PORTAINER_WAS_RUNNING" -eq 1 ]]; then

  log "Starting Portainer..."

  docker start "$PORTAINER_CONTAINER" >/dev/null

  sleep 3

  if [[ "$(docker inspect -f '{{.State.Status}}' \
    "$PORTAINER_CONTAINER" 2>/dev/null || true)" != "running" ]]; then

    die "Portainer failed to start after restore."
  fi
fi

echo
echo "=== Restore Completed Successfully ==="
echo
echo "Safety copy:"
echo "  $SAFETY_DIR"
echo
echo "Restored backup:"
echo "  $BACKUP_FILE"