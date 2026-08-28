#!/bin/bash
# peixun-worker health check
CONTAINER="peixun-worker"
LOG="/var/log/peixun_worker_health.log"

RUNNING=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)

if [ "$RUNNING" != "true" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') [ALERT] $CONTAINER is not running, starting..." >> "$LOG"
  docker start "$CONTAINER" >> "$LOG" 2>&1
  
  CHECK=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)
  if [ "$CHECK" = "true" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUCCESS] $CONTAINER successfully started." >> "$LOG"
  else
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] docker start failed, trying docker compose..." >> "$LOG"
    if [ -d "/root/peixun" ]; then
      cd /root/peixun && (docker compose up -d "$CONTAINER" || docker-compose up -d "$CONTAINER") >> "$LOG" 2>&1
    fi
  fi
fi
