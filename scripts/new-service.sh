#!/usr/bin/env bash
# Usage: scripts/new-service.sh <service-name> <relative-path>
# Example: scripts/new-service.sh email-worker workers/email
set -euo pipefail

SERVICE="${1:-}"
REL_PATH="${2:-}"
if [[ -z "$SERVICE" || -z "$REL_PATH" ]]; then
  echo "Usage: $0 <service-name> <relative-path>"
  exit 1
fi

TEMPLATE="_templates/CONTEXT.template.md"
TODAY=$(date +%Y-%m-%d)
TARGET="./${REL_PATH}"

[[ ! -f "$TEMPLATE" ]] && echo "✗ Template missing: $TEMPLATE" && exit 1

mkdir -p "$TARGET"

CONTEXT_OUT="${TARGET}/CONTEXT.md"
if [[ ! -f "$CONTEXT_OUT" ]]; then
  sed -e "s/service: service-name/service: ${SERVICE}/" \
      -e "s|path: /services/service-name/|path: /${REL_PATH}/|" \
      -e "s/last_updated: YYYY-MM-DD/last_updated: ${TODAY}/" \
      "$TEMPLATE" > "$CONTEXT_OUT"
  echo "✓ Created: $CONTEXT_OUT"
else
  echo "⚠ Exists, skipped: $CONTEXT_OUT"
fi

CLAUDE_OUT="${TARGET}/CLAUDE.md"
if [[ ! -f "$CLAUDE_OUT" ]]; then
  cat > "$CLAUDE_OUT" <<EOF
# ${SERVICE} — Local Instructions

> You are working inside \`/${REL_PATH}/\`.
> Root \`CLAUDE.md\` still applies.

## Before Starting

1. Read \`CONTEXT.md\` in this directory
2. Apply context triage from root \`CLAUDE.md\` — load other service contexts only if this task crosses a boundary
3. Check \`_master.md\` reverse map before changing any exposed interface

## Local Rules

[Add service-specific constraints here, or delete this section if none]

## After Your Task

\`\`\`
scripts/update-context.sh ${SERVICE}
\`\`\`
EOF
  echo "✓ Created: $CLAUDE_OUT"
else
  echo "⚠ Exists, skipped: $CLAUDE_OUT"
fi

echo ""
echo "Next: add ${SERVICE} to _master.md, then run scripts/sync-master.sh"
