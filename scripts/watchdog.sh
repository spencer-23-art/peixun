#!/bin/bash
# ============================================================================
# peixun System Ultra-Lightweight Watchdog
# ============================================================================

LOG_FILE="/var/log/peixun_watchdog.log"
MAX_LOG_SIZE=1048576

if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$LOG_SIZE" -gt "$MAX_LOG_SIZE" ]; then
        mv -f "$LOG_FILE" "${LOG_FILE}.old"
        echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] Log rotated." > "$LOG_FILE"
    fi
fi

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

DEPLOY_DIR="/root/peixun"
SERVICES=("peixun-proxy" "peixun-redis" "peixun-worker" "peixun-service")

for CONTAINER in "${SERVICES[@]}"; do
    STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null)
    if [ "$STATUS" != "running" ]; then
        log_msg "[ALERT] Container [$CONTAINER] is not running (Status: ${STATUS:-not_found}), starting..."
        docker start "$CONTAINER" >> "$LOG_FILE" 2>&1
        NEW_STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null)
        if [ "$NEW_STATUS" = "running" ]; then
            log_msg "[SUCCESS] Container [$CONTAINER] successfully started."
        else
            log_msg "[ERROR] docker start failed, trying docker compose up..."
            if [ -d "$DEPLOY_DIR" ]; then
                cd "$DEPLOY_DIR" && (docker compose up -d "$CONTAINER" || docker-compose up -d "$CONTAINER") >> "$LOG_FILE" 2>&1
            fi
        fi
    fi
done

WEB_STATUS=$(docker inspect -f '{{.State.Status}}' "peixun-service" 2>/dev/null)
if [ "$WEB_STATUS" = "running" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8000/api/health 2>/dev/null)
    if [ "$HTTP_CODE" != "200" ]; then
        log_msg "[WARNING] peixun-service is unresponsive (HTTP $HTTP_CODE), restarting..."
        docker restart peixun-service >> "$LOG_FILE" 2>&1
    fi
fi
