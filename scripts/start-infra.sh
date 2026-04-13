#!/usr/bin/env bash
# Starts local infrastructure and waits for all services to become healthy.
# Usage: ./scripts/start-infra.sh [--reset]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"

RESET=false
for arg in "$@"; do
  [[ "$arg" == "--reset" ]] && RESET=true
done

# ── Optional reset ─────────────────────────────────────────────────────────
if $RESET; then
  echo "→ Resetting infra volumes..."
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
fi

# ── Start ──────────────────────────────────────────────────────────────────
echo "→ Starting infrastructure..."
docker compose -f "$COMPOSE_FILE" up -d

# ── Health polling ─────────────────────────────────────────────────────────
SERVICES=(kafka redis postgres mlflow)
TIMEOUT=120
INTERVAL=5

echo "→ Waiting for services to be healthy (timeout: ${TIMEOUT}s)..."

all_healthy() {
  for svc in "${SERVICES[@]}"; do
    status=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "missing")
    if [[ "$status" != "healthy" ]]; then
      return 1
    fi
  done
  return 0
}

elapsed=0
while ! all_healthy; do
  if (( elapsed >= TIMEOUT )); then
    echo ""
    echo "✗ Timed out after ${TIMEOUT}s. Service health:"
    for svc in "${SERVICES[@]}"; do
      status=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "not found")
      printf "  %-12s %s\n" "$svc" "$status"
    done
    echo ""
    echo "Run 'docker compose logs' to diagnose."
    exit 1
  fi
  printf "."
  sleep "$INTERVAL"
  elapsed=$(( elapsed + INTERVAL ))
done

echo ""
echo "✓ All services healthy:"
for svc in "${SERVICES[@]}"; do
  printf "  %-12s healthy\n" "$svc"
done

echo ""
echo "Endpoints:"
echo "  Kafka     kafka:9092  (internal) / localhost:9092 (host)"
echo "  Redis     redis:6379  (internal) / localhost:6379 (host)"
echo "  Postgres  postgres:5432           / localhost:5432 (host)"
echo "  MLflow    http://mlflow:5000      / http://localhost:5001 (host)"
echo "  Parquet   /data/parquet (Docker volume: parquet_store)"
