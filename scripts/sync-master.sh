#!/usr/bin/env bash
# Reads depends_on frontmatter from all CONTEXT.md files and prints updated
# Dependency Map and Reverse Map sections for you to paste into _master.md.
# Usage: scripts/sync-master.sh
set -euo pipefail

TODAY=$(date +%Y-%m-%d)
echo "Scanning CONTEXT.md files..."

declare -A DEPS
declare -A PATHS
declare -A STATUSES

while IFS= read -r -d '' f; do
  svc=$(awk '/^---/{f++} f==1{next} f==2{exit} /^service:/{print $2}' "$f" | tr -d '[:space:]')
  path=$(awk '/^---/{f++} f==1{next} f==2{exit} /^path:/{print $2}' "$f" | tr -d '[:space:]')
  status=$(awk '/^---/{f++} f==1{next} f==2{exit} /^status:/{print $2}' "$f" | tr -d '[:space:]')
  deps=$(awk '/^---/{f++} f==1{next} f==2{exit} /^depends_on:/{print}' "$f" \
    | sed 's/depends_on: //' | tr -d '[][:space:]')
  [[ -z "$svc" ]] && continue
  DEPS["$svc"]="$deps"
  PATHS["$svc"]="${path:-?}"
  STATUSES["$svc"]="${status:-active}"
  echo "  ✓ $svc"
done < <(find . -path "*/node_modules" -prune -o -name "CONTEXT.md" -print0)

echo ""
echo "══ SERVICE INDEX ══════════════════════════"
echo "| Service | Path | Status | CONTEXT.md |"
echo "|---|---|---|---|"
for svc in $(echo "${!PATHS[@]}" | tr ' ' '\n' | sort); do
  echo "| $svc | ${PATHS[$svc]} | ${STATUSES[$svc]} | ✓ |"
done

echo ""
echo "══ DEPENDENCY MAP ═════════════════════════"
for svc in $(echo "${!DEPS[@]}" | tr ' ' '\n' | sort); do
  echo "$svc  →  [${DEPS[$svc]}]"
done

echo ""
echo "══ REVERSE MAP ════════════════════════════"
declare -A REV
for svc in $(echo "${!DEPS[@]}" | tr ' ' '\n' | sort); do
  IFS=',' read -ra list <<< "${DEPS[$svc]}"
  for dep in "${list[@]}"; do
    dep=$(echo "$dep" | tr -d '[:space:]')
    [[ -z "$dep" ]] && continue
    REV["$dep"]+="${svc}, "
  done
done
for dep in $(echo "${!REV[@]}" | tr ' ' '\n' | sort); do
  callers="${REV[$dep]%, }"
  echo "$dep  ←  [$callers]"
done

echo ""
echo "Paste the above into _master.md and update 'Last synced: ${TODAY}'"
