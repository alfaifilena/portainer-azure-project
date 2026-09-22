#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Default configuration variables
DATA_MOUNT="${DATA_MOUNT:-/srv/portainer-data}"
INIT_MARKER="$DATA_MOUNT/.initialized"
DRY_RUN=false
DETACH_MODE=false

# Parse command line arguments
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --detach)
            DETACH_MODE=true
            shift
            ;;
    esac
done

echo "=== Starting Advanced Data Disk Setup and Validation ==="

# 1. Safety Check: Warn if path is inside /mnt (Temporary Resource Disk on Azure)
if [[ "$DATA_MOUNT" == /mnt* ]]; then
    echo "CRITICAL WARNING: The path '$DATA_MOUNT' is inside /mnt, which is a temporary resource disk on Azure and gets wiped on deallocate!"
    echo "Please use a persistent path such as /srv/portainer-data."
    exit 1
fi

# Handle detach mode for Disaster Recovery testing
if [ "$DETACH_MODE" = true ]; then
    echo "--- DETACH MODE: Stopping Docker/containerd and unmounting data disk for recovery test ---"
    if systemctl is-active --quiet docker; then sudo systemctl stop docker; fi
    if systemctl is-active --quiet containerd; then sudo systemctl stop containerd; fi
    if mountpoint -q "$DATA_MOUNT"; then
        sudo umount "$DATA_MOUNT"
        echo "Data disk at $DATA_MOUNT has been successfully unmounted."
    fi
    exit 0
fi

# 2. Check if the data disk is mounted
if ! mountpoint -q "$DATA_MOUNT"; then
    echo "Error: Data disk is not mounted at $DATA_MOUNT. Check your /etc/fstab and UUID configurations."
    exit 1
fi

if [ "$DRY_RUN" = true ]; then
    echo "[DRY-RUN MODE] No actual changes will be made."
fi

# 3. Evaluate disk state based on markers and existing structures
if [ -f "$INIT_MARKER" ]; then
    echo "--- Normal Run or Post-Restart: Disk is already initialized ---"
    if [ "$DRY_RUN" = false ]; then
        echo "Ensuring containerd and docker services are running..."
        sudo systemctl start containerd
        sudo systemctl start docker
    else
        echo "[DRY-RUN] Would start containerd and docker."
    fi
else
    echo "--- Initialization / Migration Run Required ---"
    
    # Check if migration was interrupted previously or if it's first run
    if [ -d "$DATA_MOUNT/docker" ] || [ -d "$DATA_MOUNT/containerd" ]; then
        echo "Found partial or un-initialized data structure on disk. Resuming setup..."
    else
        echo "Disk is clean. Preparing directory structures..."
        if [ "$DRY_RUN" = false ]; then
            sudo mkdir -p "$DATA_MOUNT/docker"
            sudo mkdir -p "$DATA_URL/containerd"
            sudo mkdir -p "$DATA_MOUNT/config/secrets"
        fi
    fi

    echo "Stopping Docker and containerd services safely..."
    if [ "$DRY_RUN" = false ]; then
        sudo systemctl stop docker || true
        sudo systemctl stop containerd || true
    fi

    # Migrate data securely using rsync preserving permissions, attributes, and ACLs
    echo "Migrating /var/lib/docker and /var/lib/containerd using rsync..."
    if [ "$DRY_RUN" = false ]; then
        if [ -d "/var/lib/docker" ] && [ "$(ls -A /var/lib/docker)" ]; then
            sudo rsync -aHAXS /var/lib/docker/ "$DATA_MOUNT/docker/"
        fi
        if [ -d "/var/lib/containerd" ] && [ "$(ls -A /var/lib/containerd)" ]; then
            sudo rsync -aHAXS /var/lib/containerd/ "$DATA_MOUNT/containerd/"
        fi

        # Safely rename original paths instead of deleting them immediately
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        if [ -d "/var/lib/docker" ] && [ ! -L "/var/lib/docker" ]; then
            sudo mv /var/lib/docker "/var/lib/docker.pre-disk-$TIMESTAMP"
        fi
        if [ -d "/var/lib/containerd" ] && [ ! -L "/var/lib/containerd" ]; then
            sudo mv /var/lib/containerd "/var/lib/containerd.pre-disk-$TIMESTAMP"
        fi

        # Create initialization marker
        sudo touch "$INIT_MARKER"
        echo "Migration completed successfully and initialization marker created."

        sudo systemctl start containerd
        sudo systemctl start docker
    else
        echo "[DRY-RUN] Would execute rsync migration, rename original directories, and start services."
    fi
fi

echo "=== Data Disk Setup Script Completed Successfully ==="