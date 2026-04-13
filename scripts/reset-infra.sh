#!/usr/bin/env bash
# Tears down all infra containers and wipes all volumes.
# Use when you need a clean slate (schema migrations, corrupted state, etc.).
# Usage: ./scripts/reset-infra.sh [--restart]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"

RESTART=false
for arg in "$@"; do
  [[ "$arg" == "--restart" ]] && RESTART=true
done

echo "→ Stopping and removing containers, networks, and volumes..."
docker compose -f "$COMPOSE_FILE" down -v --remove-orphans

echo "✓ Infra reset. All volumes wiped."

if $RESTART; then
  echo ""
  exec "$REPO_ROOT/scripts/start-infra.sh"
fi
