#!/bin/bash

# Define the persistent data disk mount path
DATA_DIR="/mnt/portainer-data"
INIT_MARKER="$DATA_DIR/.initialized"

echo "=== Starting Persistent Data Disk Check and Setup ==="

# 1. Ensure the data disk is correctly mounted
if ! mountpoint -q "$DATA_DIR"; then
    echo "Error: Data disk is not mounted at $DATA_DIR"
    exit 1
fi

# 2. Check if this is the first initialization run or a regular restart
if [ ! -f "$INIT_MARKER" ]; then
    echo "--- First Run: Stopping Docker and containerd services to migrate data ---"
    
    sudo systemctl stop docker
    sudo systemctl stop containerd

    # Create approved subdirectories based on the project plan
    sudo mkdir -p "$DATA_DIR/docker"
    sudo mkdir -p "$DATA_DIR/containerd"
    sudo mkdir -p "$DATA_DIR/config/secrets"

    # Migrate existing data from default system paths to the standalone disk (keeping originals temporarily for safety)
    if [ -d "/var/lib/docker" ] && [ "$(ls -A /var/lib/docker)" ]; then
        echo "Migrating Docker data..."
        sudo cp -rp /var/lib/docker/* "$DATA_DIR/docker/"
    fi

    if [ -d "/var/lib/containerd" ] && [ "$(ls -A /var/lib/containerd)" ]; then
        echo "Migrating containerd data..."
        sudo cp -rp /var/lib/containerd/* "$DATA_DIR/containerd/"
    fi

    # Create initialization marker file to prevent formatting or re-migration on subsequent runs
    sudo touch "$INIT_MARKER"
    echo "Data successfully migrated and initialization marker (.initialized) created."

    sudo systemctl start containerd
    sudo systemctl start docker
else
    echo "--- Normal Run or Post-Restart ---"
    echo "Disk is already initialized, ensuring services are running..."
    sudo systemctl start containerd
    sudo systemctl start docker
fi

echo "=== Disk and Services Setup Completed Successfully ==="