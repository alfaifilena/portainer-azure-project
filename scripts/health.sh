#!/usr/bin/env bash
set -u

DATA_MOUNT="${DATA_MOUNT:-/srv/portainer-data}"
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

FAILURES=0

success() {
    echo "[SUCCESS] $1"
}

error() {
    echo "[ERROR] $1"
    FAILURES=$((FAILURES + 1))
}

echo "=== Starting Portainer Health Check ==="

# 1. Persistent data disk
if mountpoint -q "$DATA_MOUNT"; then
    success "Persistent data disk is mounted at $DATA_MOUNT."
else
    error "Persistent data disk is NOT mounted at $DATA_MOUNT."
fi

# 2. Initialization marker
if [[ -f "$DATA_MOUNT/.initialized" ]]; then
    success "Persistent data disk is initialized."
else
    error ".initialized marker is missing."
fi

# 3. Docker persistent bind mount
if mountpoint -q /var/lib/docker; then
    success "/var/lib/docker is mounted from persistent storage."
else
    error "/var/lib/docker is NOT mounted from persistent storage."
fi

# 4. containerd persistent bind mount
if mountpoint -q /var/lib/containerd; then
    success "/var/lib/containerd is mounted from persistent storage."
else
    error "/var/lib/containerd is NOT mounted from persistent storage."
fi

# 5. containerd service
if systemctl is-active --quiet containerd; then
    success "containerd service is running."
else
    error "containerd service is not running."
fi

# 6. Docker service
if systemctl is-active --quiet docker; then
    success "Docker service is running."
else
    error "Docker service is not running."
fi

# Continue Docker checks only if Docker responds
if docker info >/dev/null 2>&1; then
    success "Docker Engine API is responding."

    # 7. Portainer container
    PORTAINER_STATUS="$(
        docker inspect -f '{{.State.Status}}' portainer 2>/dev/null || true
    )"

    if [[ "$PORTAINER_STATUS" == "running" ]]; then
        success "Portainer container is running."
    else
        error "Portainer container is not running. Status: ${PORTAINER_STATUS:-Not Found}"
    fi

    # 8. Demo Nginx container
    NGINX_STATUS="$(
        docker inspect -f '{{.State.Status}}' \
        container-hub-demo-demo-web-1 2>/dev/null || true
    )"

    if [[ "$NGINX_STATUS" == "running" ]]; then
        success "Nginx demo container is running."
    else
        error "Nginx demo container is not running. Status: ${NGINX_STATUS:-Not Found}"
    fi

else
    error "Docker Engine API is not responding."
fi

# 9. Portainer HTTPS/API health
CERT="$PROJECT_ROOT/secrets/portainer.crt"

if [[ -s "$CERT" ]]; then
    if curl \
        --cacert "$CERT" \
        --fail \
        --silent \
        --show-error \
        --connect-timeout 5 \
        --max-time 10 \
        https://localhost:9443/api/status \
        >/dev/null
    then
        success "Portainer HTTPS API is responding."
    else
        error "Portainer HTTPS API is not responding correctly."
    fi
else
    error "Portainer TLS certificate is missing: $CERT"
fi

# 10. Nginx HTTP health
if curl \
    --fail \
    --silent \
    --show-error \
    --connect-timeout 5 \
    --max-time 10 \
    http://127.0.0.1:8081/ \
    >/dev/null
then
    success "Nginx demo page is responding."
else
    error "Nginx demo page is not responding."
fi

echo
echo "=== Health Check Summary ==="

if [[ "$FAILURES" -eq 0 ]]; then
    echo "[SUCCESS] All health checks passed."
    exit 0
else
    echo "[ERROR] $FAILURES health check(s) failed."
    exit 1
fi