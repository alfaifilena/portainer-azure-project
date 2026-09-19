#!/bin/bash

# Description: Script to manage Portainer operations (status, logs, stop, start, restart).


# Check if an argument is provided
if [ -z "$1" ]; then
    echo "[ERROR] No action specified!"
    echo "Usage: $0 {status|logs|start|stop|restart}"
    exit 1
fi

ACTION=$1

case "$ACTION" in
    status)
        echo "=== Checking Portainer Container Status ==="
        docker ps -a --filter name=portainer
        ;;
    logs)
        echo "=== Fetching Portainer Container Logs ==="
        docker logs --tail 50 portainer
        ;;
    start)
        echo "=== Starting Portainer Container ==="
        docker start portainer
        ;;
    stop)
        echo "=== Stopping Portainer Container ==="
        docker stop portainer
        ;;
    restart)
        echo "=== Restarting Portainer Container ==="
        docker restart portainer
        ;;
    *)
        echo "[ERROR] Invalid action: $ACTION"
        echo "Usage: $0 {status|logs|start|stop|restart}"
        exit 1
        ;;
esac