#!/bin/bash

DATA_DIR="/mnt/portainer-data"
BACKUP_ROOT="/backup"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_ROOT/portainer_full_backup_$TIMESTAMP.tar.gz"

echo "=== Starting Full Backup of the Persistent Disk ==="

sudo mkdir -p "$BACKUP_ROOT"

if [ -d "$DATA_DIR" ]; then
    # Compress the entire data directory into a secure archive
    sudo tar -czf "$BACKUP_FILE" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
    echo "Backup successfully created and saved at: $BACKUP_FILE"
else
    echo "Error: Persistent data disk path does not exist!"
    exit 1
fi