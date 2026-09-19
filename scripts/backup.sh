#!/bin/bash

# Description: Script to backup Portainer data and configuration securely.

echo "=== Starting Portainer Backup Process ==="

# Define variables
BACKUP_DIR="/var/backups/portainer"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/portainer_backup_$DATE.tar.gz"

# 1. Ensure backup directory exists
sudo mkdir -p "$BACKUP_DIR"

# 2. Check if Portainer data volume/directory exists
if [ ! -d "/var/lib/docker/volumes/portainer_data" ] && [ ! -d "/opt/portainer" ]; then
    echo "[ERROR] Portainer data directory/volume not found!"
    exit 1
fi

echo "[INFO] Creating backup archive..."

# 3. Create a compressed tarball of Portainer data (adjust path based on your deployment)
if [ -d "/var/lib/docker/volumes/portainer_data" ]; then
    sudo tar -czf "$BACKUP_FILE" -C /var/lib/docker/volumes portainer_data
else
    sudo tar -czf "$BACKUP_FILE" -C /opt portainer
fi

# 4. Verify if backup file was created successfully
if [ -f "$BACKUP_FILE" ]; then
    echo "[SUCCESS] Backup successfully created at: $BACKUP_FILE"
    ls -lh "$BACKUP_FILE"
else
    echo "[ERROR] Backup failed to create."
    exit 1
fi

echo "=== Backup Process Completed ==="