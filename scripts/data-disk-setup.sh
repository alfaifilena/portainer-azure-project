#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Portainer persistent data disk setup / migration / recovery
# ============================================================

DATA_MOUNT="${DATA_MOUNT:-/srv/portainer-data}"
DATA_LABEL="${DATA_LABEL:-portainer-data}"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"

MODE="${1:-status}"

MARKER="$DATA_MOUNT/.initialized"
IN_PROGRESS="$DATA_MOUNT/.migration-in-progress"

FSTAB_BEGIN="# BEGIN PORTAINER_DATA_DISK"
FSTAB_END="# END PORTAINER_DATA_DISK"

SWITCH_STARTED=0

log() {
  printf '[INFO] %s\n' "$*"
}

warn() {
  printf '[WARN] %s\n' "$*" >&2
}

die() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

require_root() {
  [[ "$EUID" -eq 0 ]] || die "Run this script with sudo/root."
}

require_cmds() {
  local cmd

  for cmd in \
    findmnt \
    findfs \
    blkid \
    lsblk \
    rsync \
    mount \
    umount \
    mountpoint \
    systemctl \
    awk \
    grep \
    sed \
    date \
    readlink
  do
    command -v "$cmd" >/dev/null || \
      die "Required command not found: $cmd"
  done
}

validate_mount_path() {
  case "$DATA_MOUNT" in
    /mnt|/mnt/*)
      die "DATA_MOUNT must not be under /mnt. Use /srv/portainer-data."
      ;;
  esac
}

find_data_device() {
  local dev="${DATA_DEVICE:-}"

  if [[ -z "$dev" ]]; then
    dev="$(findfs "LABEL=$DATA_LABEL" 2>/dev/null || true)"
  fi

  [[ -n "$dev" ]] || \
    die "Could not find disk with label '$DATA_LABEL'."

  readlink -f "$dev"
}

assert_not_os_disk() {
  local dev="$1"
  local root_src
  local root_parent
  local dev_parent

  root_src="$(findmnt -n -o SOURCE /)"
  root_src="$(readlink -f "$root_src")"

  root_parent="$(lsblk -no PKNAME "$root_src" 2>/dev/null || true)"
  dev_parent="$(lsblk -no PKNAME "$dev" 2>/dev/null || true)"

  [[ "$dev" != "$root_src" ]] || \
    die "Refusing to use the OS root device: $dev"

  if [[ -n "$root_parent" ]]; then
    [[ "$(basename "$dev")" != "$root_parent" ]] || \
      die "Refusing to use the OS disk: $dev"

    [[ "$dev_parent" != "$root_parent" ]] || \
      die "Refusing to use a partition on the OS disk: $dev"
  fi
}

get_disk_facts() {
  DATA_DEVICE_RESOLVED="$(find_data_device)"

  assert_not_os_disk "$DATA_DEVICE_RESOLVED"

  DATA_FSTYPE="$(
    blkid -s TYPE -o value "$DATA_DEVICE_RESOLVED" 2>/dev/null || true
  )"

  DATA_UUID="$(
    blkid -s UUID -o value "$DATA_DEVICE_RESOLVED" 2>/dev/null || true
  )"

  [[ -n "$DATA_FSTYPE" ]] || \
    die "Data disk has no filesystem. This script NEVER formats disks."

  [[ -n "$DATA_UUID" ]] || \
    die "Could not read UUID from $DATA_DEVICE_RESOLVED."
}

ensure_root_mount_fstab() {
  mkdir -p "$DATA_MOUNT"

  if ! grep -q \
    "UUID=$DATA_UUID $DATA_MOUNT " \
    /etc/fstab
  then
    log "Adding persistent UUID mount to /etc/fstab"

    printf \
      'UUID=%s %s %s defaults,nofail 0 2\n' \
      "$DATA_UUID" \
      "$DATA_MOUNT" \
      "$DATA_FSTYPE" \
      >> /etc/fstab
  fi

  if ! mountpoint -q "$DATA_MOUNT"; then
    log "Mounting data disk at $DATA_MOUNT"
    mount "$DATA_MOUNT"
  fi

  local mounted_src

  mounted_src="$(
    readlink -f "$(findmnt -n -o SOURCE "$DATA_MOUNT")"
  )"

  [[ "$mounted_src" == "$DATA_DEVICE_RESOLVED" ]] || \
    die "$DATA_MOUNT is mounted from $mounted_src, expected $DATA_DEVICE_RESOLVED"
}

ensure_layout() {
  mkdir -p \
    "$DATA_MOUNT/docker" \
    "$DATA_MOUNT/containerd" \
    "$DATA_MOUNT/config/secrets"
}

has_unexpected_payload() {
  # Allowed before the first migration:
  #
  # lost+found/
  # docker/
  # containerd/
  # config/
  # config/secrets/
  #
  # All of these must still be empty except lost+found.

  if find "$DATA_MOUNT" \
      -mindepth 1 \
      -maxdepth 1 \
      ! -name lost+found \
      ! -name docker \
      ! -name containerd \
      ! -name config \
      -print -quit |
      grep -q .
  then
    return 0
  fi

  if find "$DATA_MOUNT/docker" \
      -mindepth 1 \
      -print -quit 2>/dev/null |
      grep -q .
  then
    return 0
  fi

  if find "$DATA_MOUNT/containerd" \
      -mindepth 1 \
      -print -quit 2>/dev/null |
      grep -q .
  then
    return 0
  fi

  # config/secrets itself is allowed to exist.
  if find "$DATA_MOUNT/config" \
      -mindepth 1 \
      -maxdepth 1 \
      ! -name secrets \
      -print -quit 2>/dev/null |
      grep -q .
  then
    return 0
  fi

  # Files inside config/secrets mean the disk already contains payload.
  if find "$DATA_MOUNT/config/secrets" \
      -mindepth 1 \
      -print -quit 2>/dev/null |
      grep -q .
  then
    return 0
  fi

  return 1
}

stop_runtime() {
  log "Stopping Docker and containerd"

  systemctl stop docker.service 2>/dev/null || true
  systemctl stop docker.socket 2>/dev/null || true
  systemctl stop containerd.service 2>/dev/null || true
}

start_runtime() {
  log "Starting containerd and Docker"

  systemctl start containerd.service
  systemctl start docker.service

  docker info >/dev/null

  log "Docker started successfully."
}

copy_and_verify() {
  local src="$1"
  local dst="$2"
  local label="$3"

  [[ -d "$src" ]] || die "$src does not exist."

  mkdir -p "$dst"

  log "Copying $label"

  rsync \
    -aHAXS \
    --numeric-ids \
    "$src/" \
    "$dst/"

  log "Verifying $label copy"

  local diff

  diff="$(
    rsync \
      -aHAXSni \
      --delete \
      --numeric-ids \
      "$src/" \
      "$dst/" || true
  )"

  if [[ -n "$diff" ]]; then
    printf '%s\n' "$diff" >&2
    die "Verification failed for $label."
  fi

  log "$label verification passed."
}

copy_project_config() {
  [[ -f "$PROJECT_ROOT/.env" ]] || \
    die "$PROJECT_ROOT/.env is missing."

  [[ -d "$PROJECT_ROOT/secrets" ]] || \
    die "$PROJECT_ROOT/secrets is missing."

  log "Copying .env and secrets to persistent disk"

  rsync \
    -a \
    "$PROJECT_ROOT/.env" \
    "$DATA_MOUNT/config/.env"

  rsync \
    -a \
    "$PROJECT_ROOT/secrets/" \
    "$DATA_MOUNT/config/secrets/"
}

write_bind_fstab_block() {
  # Remove a previous block created by this script.
  sed -i \
    '/^# BEGIN PORTAINER_DATA_DISK$/,/^# END PORTAINER_DATA_DISK$/d' \
    /etc/fstab

  cat >> /etc/fstab <<EOF
$FSTAB_BEGIN
$DATA_MOUNT/docker /var/lib/docker none bind 0 0
$DATA_MOUNT/containerd /var/lib/containerd none bind 0 0
$FSTAB_END
EOF
}

install_systemd_guards() {
  log "Installing systemd mount dependencies"

  mkdir -p \
    /etc/systemd/system/containerd.service.d \
    /etc/systemd/system/docker.service.d

  cat > \
    /etc/systemd/system/containerd.service.d/10-portainer-data-disk.conf \
    <<EOF
[Unit]
RequiresMountsFor=$DATA_MOUNT /var/lib/containerd
EOF

  cat > \
    /etc/systemd/system/docker.service.d/10-portainer-data-disk.conf \
    <<EOF
[Unit]
RequiresMountsFor=$DATA_MOUNT /var/lib/docker /var/lib/containerd
After=containerd.service
EOF

  systemctl daemon-reload
}

backup_and_link_project_config() {
  local stamp="$1"

  if [[ -L "$PROJECT_ROOT/.env" ]]; then
    rm "$PROJECT_ROOT/.env"
  elif [[ -e "$PROJECT_ROOT/.env" ]]; then
    mv \
      "$PROJECT_ROOT/.env" \
      "$PROJECT_ROOT/.env.pre-disk-$stamp"
  fi

  ln -s \
    "$DATA_MOUNT/config/.env" \
    "$PROJECT_ROOT/.env"

  if [[ -L "$PROJECT_ROOT/secrets" ]]; then
    rm "$PROJECT_ROOT/secrets"
  elif [[ -e "$PROJECT_ROOT/secrets" ]]; then
    mv \
      "$PROJECT_ROOT/secrets" \
      "$PROJECT_ROOT/secrets.pre-disk-$stamp"
  fi

  ln -s \
    "$DATA_MOUNT/config/secrets" \
    "$PROJECT_ROOT/secrets"

  log "Project .env and secrets now point to persistent storage."
}

switch_runtime_to_disk() {
  local stamp="$1"

  SWITCH_STARTED=1

  log "Switching Docker storage to persistent disk"

  if ! mountpoint -q /var/lib/docker; then
    if [[ -d /var/lib/docker ]]; then
      mv \
        /var/lib/docker \
        "/var/lib/docker.pre-disk-$stamp"
    fi

    mkdir -p /var/lib/docker
  fi

  if ! mountpoint -q /var/lib/containerd; then
    if [[ -d /var/lib/containerd ]]; then
      mv \
        /var/lib/containerd \
        "/var/lib/containerd.pre-disk-$stamp"
    fi

    mkdir -p /var/lib/containerd
  fi

  write_bind_fstab_block
  install_systemd_guards

  mountpoint -q /var/lib/containerd || \
    mount /var/lib/containerd

  mountpoint -q /var/lib/docker || \
    mount /var/lib/docker

  mountpoint -q /var/lib/docker || \
    die "/var/lib/docker is not bind-mounted."

  mountpoint -q /var/lib/containerd || \
    die "/var/lib/containerd is not bind-mounted."

  log "Docker and containerd bind mounts are active."
}

write_marker() {
  local docker_version="unknown"

  docker_version="$(
    docker version \
      --format '{{.Server.Version}}' \
      2>/dev/null || true
  )"

  cat > "$MARKER" <<EOF
initialized_at=$(date -Is)
host=$(hostname)
disk_uuid=$DATA_UUID
docker_version=$docker_version
project_root=$PROJECT_ROOT
EOF

  rm -f "$IN_PROGRESS"

  log "Initialization marker created."
}

on_migration_error() {
  warn "Migration did not complete."
  warn "Original OS-disk data has NOT been deleted."

  if [[ "$SWITCH_STARTED" -eq 0 ]]; then
    warn "Storage switch had not started; restarting original Docker services."
    systemctl start containerd.service 2>/dev/null || true
    systemctl start docker.service 2>/dev/null || true
  else
    warn "Storage switching had already started."
    warn "Do not delete any *.pre-disk-* directories."
    warn "Inspect the system before attempting another migration."
  fi
}

status_report() {
  get_disk_facts

  printf 'Data device : %s\n' "$DATA_DEVICE_RESOLVED"
  printf 'Disk UUID   : %s\n' "$DATA_UUID"
  printf 'Filesystem  : %s\n' "$DATA_FSTYPE"
  printf 'Mount path  : %s\n' "$DATA_MOUNT"

  printf 'Mounted     : %s\n' \
    "$(mountpoint -q "$DATA_MOUNT" && echo yes || echo no)"

  printf 'Initialized : %s\n' \
    "$([[ -f "$MARKER" ]] && echo yes || echo no)"

  printf 'In progress : %s\n' \
    "$([[ -f "$IN_PROGRESS" ]] && echo yes || echo no)"

  printf 'Docker bind : %s\n' \
    "$(mountpoint -q /var/lib/docker && echo yes || echo no)"

  printf 'Ctrd bind   : %s\n' \
    "$(mountpoint -q /var/lib/containerd && echo yes || echo no)"
}

initialize() {
  get_disk_facts
  ensure_root_mount_fstab
  ensure_layout

  [[ ! -f "$MARKER" ]] || \
    die "Disk already initialized. Use --recover."

  [[ ! -f "$IN_PROGRESS" ]] || \
    die "Interrupted migration detected. Review it, then use --resume-migration."

  if has_unexpected_payload; then
    die \
      "Disk contains data but has no initialization marker. Review it before using --resume-migration."
  fi

  command -v docker >/dev/null || \
    die "Docker is not installed."

  local stamp

  stamp="$(date +%Y%m%d_%H%M%S)"

  printf \
    'started_at=%s\nhost=%s\n' \
    "$(date -Is)" \
    "$(hostname)" \
    > "$IN_PROGRESS"

  trap on_migration_error ERR

  stop_runtime

  copy_and_verify \
    /var/lib/docker \
    "$DATA_MOUNT/docker" \
    "Docker data"

  copy_and_verify \
    /var/lib/containerd \
    "$DATA_MOUNT/containerd" \
    "containerd data"

  copy_project_config

  switch_runtime_to_disk "$stamp"

  backup_and_link_project_config "$stamp"

  start_runtime

  write_marker

  trap - ERR

  log "Migration completed successfully."
  log "Original data remains in *.pre-disk-$stamp directories."
  log "Do NOT delete those directories until reboot/recovery tests pass."
}

resume_migration() {
  get_disk_facts
  ensure_root_mount_fstab
  ensure_layout

  [[ ! -f "$MARKER" ]] || \
    die "Disk is already initialized. Use --recover."

  if [[ ! -f "$IN_PROGRESS" ]]; then
    warn "No .migration-in-progress marker found."
    warn "--resume-migration was explicitly requested, so continuing."
  fi

  command -v docker >/dev/null || \
    die "Docker is not installed."

  local stamp

  stamp="$(date +%Y%m%d_%H%M%S)"

  trap on_migration_error ERR

  stop_runtime

  if ! mountpoint -q /var/lib/docker; then
    if [[ -n "$(ls -A /var/lib/docker 2>/dev/null || true)" ]]; then
      copy_and_verify \
        /var/lib/docker \
        "$DATA_MOUNT/docker" \
        "Docker data"
    else
      log "Docker live directory is empty; keeping persistent disk copy."
    fi
  fi

  if ! mountpoint -q /var/lib/containerd; then
    if [[ -n "$(ls -A /var/lib/containerd 2>/dev/null || true)" ]]; then
      copy_and_verify \
        /var/lib/containerd \
        "$DATA_MOUNT/containerd" \
        "containerd data"
    else
      log "containerd live directory is empty; keeping persistent disk copy."
    fi
  fi

  if [[ ! -f "$DATA_MOUNT/config/.env" ]]; then
    copy_project_config
  fi

  switch_runtime_to_disk "$stamp"

  backup_and_link_project_config "$stamp"

  start_runtime

  write_marker

  trap - ERR

  log "Migration resume completed successfully."
}

recover() {
  get_disk_facts
  ensure_root_mount_fstab
  ensure_layout

  [[ -f "$MARKER" ]] || \
    die "Disk is not marked initialized. Refusing recovery."

  command -v docker >/dev/null || \
    die "Docker is not installed on this host."

  local stamp

  stamp="$(date +%Y%m%d_%H%M%S)"

  stop_runtime

  # Preserve fresh Docker state that may have been created
  # by the replacement VM before recovery.

  if ! mountpoint -q /var/lib/docker; then
    if [[ -d /var/lib/docker ]] &&
       [[ -n "$(ls -A /var/lib/docker 2>/dev/null || true)" ]]
    then
      mv \
        /var/lib/docker \
        "/var/lib/docker.pre-disk-recovery-$stamp"

      mkdir -p /var/lib/docker
    fi
  fi

  if ! mountpoint -q /var/lib/containerd; then
    if [[ -d /var/lib/containerd ]] &&
       [[ -n "$(ls -A /var/lib/containerd 2>/dev/null || true)" ]]
    then
      mv \
        /var/lib/containerd \
        "/var/lib/containerd.pre-disk-recovery-$stamp"

      mkdir -p /var/lib/containerd
    fi
  fi

  switch_runtime_to_disk "$stamp"

  backup_and_link_project_config "$stamp"

  start_runtime

  log "Recovery completed successfully."
}

detach() {
  get_disk_facts

  [[ -f "$MARKER" ]] || \
    die "Disk is not marked initialized. Refusing detach workflow."

  warn "Stopping Docker/containerd before detaching the data disk."

  stop_runtime

  umount /var/lib/docker 2>/dev/null || true
  umount /var/lib/containerd 2>/dev/null || true

  sync

  umount "$DATA_MOUNT"

  log "Persistent disk is unmounted."
  log "The Azure Managed Disk can now be detached safely."
}

dry_run() {
  status_report

  echo
  echo "Dry run only."
  echo "No files, services, mounts, or fstab entries were changed."
  echo

  if ! mountpoint -q "$DATA_MOUNT"; then
    echo "State: data disk is not currently mounted."
    echo "Mount it before evaluating migration state."
    return
  fi

  if [[ -f "$MARKER" ]]; then
    echo "State: initialized disk."
    echo "Normal recovery action: --recover"

  elif [[ -f "$IN_PROGRESS" ]]; then
    echo "State: interrupted migration."
    echo "Review first, then use: --resume-migration"

  elif has_unexpected_payload; then
    echo "WARNING: Disk contains payload but has no marker."
    echo "Do NOT use --initialize."
    echo "Review the contents before using --resume-migration."

  else
    echo "State: prepared empty data disk."
    echo "First migration action: --initialize"
  fi
}

usage() {
  cat <<EOF
Usage:

  sudo bash scripts/data-disk-setup.sh --dry-run

  sudo bash scripts/data-disk-setup.sh --initialize

  sudo bash scripts/data-disk-setup.sh --resume-migration

  sudo bash scripts/data-disk-setup.sh --recover

  sudo bash scripts/data-disk-setup.sh --detach

  sudo bash scripts/data-disk-setup.sh --status


Environment overrides:

  DATA_MOUNT=/srv/portainer-data

  DATA_LABEL=portainer-data

  DATA_DEVICE=/dev/nvme0n2

  PROJECT_ROOT=/path/to/portainer-azure-project


Safety:

  - This script NEVER formats a disk.
  - It refuses DATA_MOUNT paths under /mnt.
  - It refuses the OS disk.
  - It does not delete original Docker/containerd data.
  - Original directories are renamed to *.pre-disk-*.
  - .initialized is created only after successful migration.
  - Existing payload without .initialized blocks --initialize.
  - Recovery requires a valid .initialized marker.
EOF
}

require_root
require_cmds
validate_mount_path

case "$MODE" in
  --dry-run)
    dry_run
    ;;

  --initialize)
    initialize
    ;;

  --resume-migration)
    resume_migration
    ;;

  --recover)
    recover
    ;;

  --detach)
    detach
    ;;

  status|--status)
    status_report
    ;;

  -h|--help)
    usage
    ;;

  *)
    usage
    exit 2
    ;;
esac
