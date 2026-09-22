#!/usr/bin/env bash
set -Eeuo pipefail

DATA_MOUNT="${DATA_MOUNT:-/srv/portainer-data}"
BACKUP_DIR="${BACKUP_DIR:-$DATA_MOUNT/backups}"

PORTAINER_CONTAINER="${PORTAINER_CONTAINER:-portainer}"
PORTAINER_VOLUME="${PORTAINER_VOLUME:-container-hub_portainer_data}"

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_ROOT="$BACKUP_DIR/portainer-backup-$STAMP"
ARCHIVE="$BACKUP_DIR/portainer-backup-$STAMP.tar.gz"

PORTAINER_WAS_RUNNING=0

log() {
  echo "[INFO] $*"
}

die() {
  echo "[ERROR] $*" >&2
  exit 1
}

restart_portainer_if_needed() {
  if [[ "$PORTAINER_WAS_RUNNING" -eq 1 ]]; then
    log "Starting Portainer again..."
    docker start "$PORTAINER_CONTAINER" >/dev/null || true
  fi
}

trap restart_portainer_if_needed EXIT

[[ "$EUID" -eq 0 ]] || die "Run this script with sudo/root."

mountpoint -q "$DATA_MOUNT" || \
  die "Persistent data disk is not mounted at $DATA_MOUNT."

[[ -f "$DATA_MOUNT/.initialized" ]] || \
  die "Persistent data disk is not initialized."

command -v docker >/dev/null || die "Docker is not installed."
command -v tar >/dev/null || die "tar is not installed."

docker volume inspect "$PORTAINER_VOLUME" >/dev/null 2>&1 || \
  die "Portainer volume not found: $PORTAINER_VOLUME"

VOLUME_PATH="$(
  docker volume inspect \
    --format '{{.Mountpoint}}' \
    "$PORTAINER_VOLUME"
)"

[[ -d "$VOLUME_PATH" ]] || \
  die "Portainer volume path not found: $VOLUME_PATH"

mkdir -p "$BACKUP_ROOT"
mkdir -p "$BACKUP_DIR"

if [[ "$(docker inspect -f '{{.State.Running}}' "$PORTAINER_CONTAINER" 2>/dev/null || true)" == "true" ]]; then
  PORTAINER_WAS_RUNNING=1

  log "Stopping Portainer temporarily for a consistent backup..."
  docker stop "$PORTAINER_CONTAINER" >/dev/null
fi

log "Backing up Portainer persistent data..."

mkdir -p "$BACKUP_ROOT/portainer-volume"

rsync \
  -aHAXS \
  --numeric-ids \
  "$VOLUME_PATH/" \
  "$BACKUP_ROOT/portainer-volume/"

log "Backing up persistent configuration..."

mkdir -p "$BACKUP_ROOT/config"

if [[ -f "$DATA_MOUNT/config/.env" ]]; then
  cp -a \
    "$DATA_MOUNT/config/.env" \
    "$BACKUP_ROOT/config/.env"
fi

if [[ -d "$DATA_MOUNT/config/secrets" ]]; then
  cp -a \
    "$DATA_MOUNT/config/secrets" \
    "$BACKUP_ROOT/config/secrets"
fi

cat > "$BACKUP_ROOT/backup-info.txt" <<EOF
created_at=$(date -Is)
host=$(hostname)
portainer_volume=$PORTAINER_VOLUME
docker_version=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)
disk_uuid=$(blkid -s UUID -o value "$(findmnt -n -o SOURCE "$DATA_MOUNT")" 2>/dev/null || echo unknown)
EOF

log "Creating compressed archive..."

tar \
  -czf "$ARCHIVE" \
  -C "$BACKUP_DIR" \
  "$(basename "$BACKUP_ROOT")"

rm -rf "$BACKUP_ROOT"

[[ -s "$ARCHIVE" ]] || \
  die "Backup archive was not created correctly."

log "Backup completed successfully."
log "Backup file: $ARCHIVE"

ls -lh "$ARCHIVE"

echo
echo "NOTE:"
echo "This archive is an application-level backup."
echo "The Azure Managed Data Disk remains the primary disaster-recovery mechanism."