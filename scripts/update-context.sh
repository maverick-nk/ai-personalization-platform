#!/usr/bin/env bash
# Usage: scripts/update-context.sh <service-name>
set -euo pipefail

SERVICE="${1:-}"
if [[ -z "$SERVICE" ]]; then
  echo "Usage: $0 <service-name>"
  exit 1
fi

CONTEXT_FILE=$(find . -path "*/node_modules" -prune -o \
  -name "CONTEXT.md" -print | xargs grep -l "^service: ${SERVICE}$" 2>/dev/null | head -1)

if [[ -z "$CONTEXT_FILE" ]]; then
  echo "✗ No CONTEXT.md found for: ${SERVICE}"
  echo "  Create one: cp _templates/CONTEXT.template.md <service-path>/CONTEXT.md"
  exit 1
fi

echo "✓ Found: $CONTEXT_FILE"

LINE_COUNT=$(wc -l < "$CONTEXT_FILE")
if [[ "$LINE_COUNT" -gt 130 ]]; then
  echo "⚠ ${LINE_COUNT} lines (limit: 150) — consider compressing ## Architecture Notes"
fi

TODAY=$(date +%Y-%m-%d)
echo ""
echo "One-line summary of what changed (Enter to skip):"
read -r CHANGE_SUMMARY

if [[ -n "$CHANGE_SUMMARY" ]]; then
  ENTRY="- [${TODAY}] ${CHANGE_SUMMARY}"
  TMPFILE=$(mktemp)
  awk -v entry="$ENTRY" '/^## Recent Changes$/ { print; print entry; next } { print }' \
    "$CONTEXT_FILE" > "$TMPFILE"
  mv "$TMPFILE" "$CONTEXT_FILE"
  echo "✓ Added: $ENTRY"
fi

CHANGE_COUNT=$(grep -c "^- \[20" "$CONTEXT_FILE" || true)
if [[ "$CHANGE_COUNT" -gt 5 ]]; then
  echo "⚠ Recent Changes has ${CHANGE_COUNT} entries — compress oldest into ## Architecture Notes"
fi

TMPFILE=$(mktemp)
sed "s/^last_updated: .*/last_updated: ${TODAY}/" "$CONTEXT_FILE" > "$TMPFILE"
mv "$TMPFILE" "$CONTEXT_FILE"
echo "✓ last_updated → ${TODAY}"

echo ""
echo "Checklist:"
echo "  ☐ New dependencies found?     → update _master.md"
echo "  ☐ Flags resolved?             → remove from ## Flags, note in Recent Changes"
echo "  ☐ Interfaces changed?         → update ## Interfaces"
echo "  ☐ Graph still accurate?       → run scripts/sync-master.sh"
