#!/bin/bash
# Description: Health check script for Docker service, Portainer container, 
#              and port responsiveness.


echo "=== Starting Portainer Health Check ==="

# 1. Check if the Docker service is active and running
if ! systemctl is-active --quiet docker; then
    echo "[ERROR] Docker service is currently not running!"
    exit 1
else
    echo "[SUCCESS] Docker service is running properly."
fi

# 2. Check the status of the Portainer container
CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' portainer 2>/dev/null)

if [ "$CONTAINER_STATUS" == "running" ]; then
    echo "[SUCCESS] Portainer container is running."
else
    echo "[ERROR] Portainer container is not running or not found. Current status: ${CONTAINER_STATUS:-Not Found}"
    exit 1
fi

# 3. Check responsiveness of the Portainer port (e.g., standard ports 9443 or 9000)
if curl -k -s --head https://localhost:9443 | grep "200 OK" > /dev/null || curl -s --head http://localhost:9000 | grep "200 OK" > /dev/null; then
    echo "[SUCCESS] Portainer interface is responding to requests successfully."
else
    echo "[WARNING] Portainer container is running, but did not respond to the quick health check probe on the port."
fi

echo "=== Health Check Completed ==="