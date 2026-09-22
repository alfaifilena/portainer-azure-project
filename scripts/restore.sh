#!/bin/bash

BACKUP_FILE=$1
DATA_DIR="/mnt/portainer-data"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: sudo bash scripts/restore.sh /path/to/backup.tar.gz"
    exit 1
fi

echo "=== Starting Data Restoration to the Persistent Disk ==="

# Stop services temporarily to ensure file integrity during restore
sudo systemctl stop docker
sudo systemctl stop containerd

# Clear current contents and extract the backup directly onto the persistent disk
sudo rm -rf "$DATA_DIR"/*
sudo tar -xzf "$BACKUP_FILE" -C "$(dirname "$DATA_DIR")"

echo "Data successfully restored to $DATA_DIR"

# Restart services with the restored data
sudo systemctl start containerd
sudo systemctl start docker

echo "=== Services are now running with the restored data ==="