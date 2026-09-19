#!/bin/bash

# Description: Script to restore Portainer backup on a clean target safely.


# Check if backup file path is provided as an argument
if [ -z "$1" ]; then
    echo "[ERROR] No backup file path specified!"
    echo "Usage: $0 /path/to/portainer_backup_YYYYMMDD_HHMMSS.tar.gz"
    exit 1
fi

BACKUP_FILE=$1

# 1. Verify if the backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "[ERROR] Backup file not found at: $BACKUP_FILE"
    exit 1
fi

echo "=== Starting Portainer Restore Process ==="

# 2. Check if Portainer container or volume already exists (Safety check for clean target)
if [ "$(docker ps -a -q -f name=portainer)" ] || [ -d "/var/lib/docker/volumes/portainer_data" ]; then
    echo "[WARNING] Existing Portainer container or data volume detected!"
    echo "[ERROR] Restore aborted to prevent overwriting existing data. Please run on a clean target."
    exit 1
fi

echo "[INFO] Target environment verified as clean. Proceeding with restore..."

# 3. Create the data volume and extract the backup archive
sudo mkdir -p /var/lib/docker/volumes/portainer_data
sudo tar -xzf "$BACKUP_FILE" -C /var/lib/docker/volumes/

# 4. Verify extraction success
if [ $? -eq 0 ]; then
    echo "[SUCCESS] Portainer backup restored successfully from: $BACKUP_FILE"
else
    echo "[ERROR] Failed to extract and restore the backup archive."
    exit 1
fi

echo "=== Restore Process Completed ==="