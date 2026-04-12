---
name: repo-context-system
category: tooling
description: Sets up and maintains a token-efficient, graph-aware context system for software repos used with Claude Code. Use this skill whenever starting a new project, onboarding Claude to an existing repo, or when the user mentions context management, wiki setup, service documentation, or wants Claude to understand a codebase structure. Triggers on phrases like "set up context", "create the wiki", "document the services", "update the context system", or "start a new project".
---

# Repo Context System

This skill sets up and maintains a lightweight knowledge graph so Claude Code loads only the minimum context needed for each task — reducing token usage and keeping Claude focused.

## What It Creates

```
/
├── CLAUDE.md                        ← Root behavioral instructions for Claude
├── _master.md                       ← Service relationship graph (the map)
├── _templates/
│   └── CONTEXT.template.md          ← Template for new services
├── scripts/
│   ├── update-context.sh            ← Run after every task
│   ├── sync-master.sh               ← Regenerates _master.md from frontmatter
│   └── new-service.sh               ← Bootstraps a new service
└── <service-path>/
    ├── CLAUDE.md                    ← Service-local instructions
    └── CONTEXT.md                   ← Living context doc for this service
```

---

## Step 1 — Detect State

Before asking the user anything, inspect the repo root:

- Does `CLAUDE.md` exist? Does `_master.md` exist? → if neither: **NEW SETUP**
- Do service directories exist but lack `CONTEXT.md`? → **PARTIAL SETUP**
- Does everything exist but `last_updated` dates are stale (>14 days)? → **MAINTENANCE**
- Is everything present and recent? → Report "Context system looks healthy" and stop unless the user wants to add a new service

State your finding in one sentence, then proceed to the matching step below.

---

## Step 2A — New Setup

Ask the user these questions in **two separate groups** — wait for answers before moving to the next group.

**Group 1 — Project basics:**
- What is the name and one-sentence purpose of this project?
- List your services, workers, or modules — just names and their folder paths.

**Group 2 — Relationships** (ask per service, keep it conversational):
- Which other services does `<service>` call or depend on?
- Is `<service>` called by anything else?
- Are there any frozen interfaces or hard constraints I should never violate in any service?

Mark anything the user is unsure about as `?` — never guess relationships.

Then scaffold all files using the exact file contents in **Section 4** below.

---

## Step 2B — Partial Setup

1. List which services are missing `CONTEXT.md` or `CLAUDE.md`
2. Ask: "Should I create context files for these now?"
3. For each confirmed service, ask the Group 2 relationship questions above
4. Create missing files using templates in Section 4

---

## Step 2C — Maintenance

Run this checklist automatically without asking first, then report findings:

- **Staleness**: Find `CONTEXT.md` files with `last_updated` older than 14 days → list them
- **Coverage**: Find dirs containing `src/`, `package.json`, `pyproject.toml`, or `go.mod` that are not in `_master.md` → list them
- **Flags**: Search all `CONTEXT.md` for `⚑` entries → list by service
- **Broken refs**: Check each `depends_on` frontmatter value exists in `_master.md` → list mismatches

For each finding, ask the user what to fix, then apply changes.

---

## Step 3 — After Scaffolding

Always finish with:
1. A summary list of files created or updated
2. A reminder to run `chmod +x scripts/*.sh` if scripts were created
3. Next recommended action (e.g. "Fill in `?` fields in each CONTEXT.md, then run `scripts/sync-master.sh`")

Do not update `## Recent Changes` in any CONTEXT.md during setup — that section is for feature/fix tasks only.

---

## Step 4 — Exact File Contents to Generate

Use these verbatim. Fill in bracketed placeholders from user input.

---

### `CLAUDE.md` (repo root)

```markdown
# Project Instructions for Claude

## 1. Start Every Task Here

Read `_master.md` first. Then apply this triage before loading any other files:

### Context Triage — Load Only What the Task Needs

**Always load:**
- `CONTEXT.md` of the service(s) directly named in the task

**Load a dependency's CONTEXT.md only if the task involves:**
- Calling that dependency (adding/changing/removing a call to its API, queue, or data source)
- Changing a contract that dependency relies on (endpoint, event schema, shared model)
- Modifying shared config or data structures used across both services

**Do not load a dependency's CONTEXT.md if the task is:**
- Refactoring or optimizing logic inside a single service
- Adding/modifying unit tests that don't cross service boundaries
- Fixing a bug confirmed to be within one service
- Updating internal documentation, comments, or types

**Decision rule:** Would this change break or require awareness from another service?
If no → skip that dependency's context. If yes → load it.

> Goal: on a typical single-service task, load exactly 1 CONTEXT.md.

### Examples

| Task | Load |
|---|---|
| Optimize a method in `auth-service` | `auth-service` CONTEXT only |
| Add a field to auth token payload | `auth-service` + services that parse the token |
| Fix a null check in `payment-pipeline` | `payment-pipeline` CONTEXT only |
| Change the user-db schema | `user-db` + all services in its `depended_on_by` |

---

## 2. While Working

- If you discover an undocumented dependency mid-task, add `⚑ UNDOCUMENTED` to that service's `## Flags`
- If a task in service A incidentally affects service B, note it — do not modify B without updating B's context
- Do not read entire directories speculatively — follow the graph in `_master.md`

---

## 3. End Every Task — Context Update (Mandatory)

After every task, for each service touched:

1. Run `scripts/update-context.sh <service-name>`
2. If unavailable, manually:
   - Add one dated line to `## Recent Changes`
   - Update `## Current State` if something structural changed
   - Clear resolved `## Flags` and note the resolution in Recent Changes
   - If Recent Changes exceeds 5 entries, compress the oldest into `## Architecture Notes`
3. If a new dependency was found, update `_master.md`

> This step is not optional. An outdated context is worse than no context.

---

## 4. CONTEXT.md Size Rules

Each `CONTEXT.md` must stay under **150 lines**. If approaching the limit:
- Compress `## Architecture Notes` into fewer, denser lines
- Collapse Recent Changes older than 30 days into one summary line
- Never delete `## Current State`, `## Depends On`, or `## Depended On By`

---

## 5. Missing Context

If a service has no `CONTEXT.md`:
- Copy `_templates/CONTEXT.template.md` to the service directory
- Fill in what can be inferred; mark unknowns with `?`
- Add the service to `_master.md`

---

## 6. What Claude Must Never Do

- Load dependency context speculatively — only load what the current task requires
- Read entire directories to build a mental map — use `_master.md` instead
- Update `_master.md` relationship entries without evidence from actual code
- Let `CONTEXT.md` files become free-form notes — follow the schema
- Skip the end-of-task context update because the task felt small
```

---

### `_master.md` (repo root)

```markdown
# Service Relationship Graph

> Dependency lines are derived from each service's CONTEXT.md frontmatter.
> Run `scripts/sync-master.sh` to regenerate. Only edit ## Notes and ## System Overview manually.

**Last synced:** [TODAY]

---

## System Overview

[USER'S ONE-SENTENCE PROJECT DESCRIPTION]

---

## Service Index

| Service | Path | Status | CONTEXT.md |
|---|---|---|---|
[ONE ROW PER SERVICE: | service-name | /path/ | active | ✓ |]

> Status values: `active` · `deprecated` · `experimental` · `external`

---

## Dependency Map

> `service` → depends on → `[list]`

```
[ONE LINE PER SERVICE: service-name  →  [dep1, dep2]]
```

> `*` = external/third-party. No CONTEXT.md — document inside the service that uses it.

---

## Reverse Map

> Shows blast radius when a service changes.

```
[ONE LINE PER SERVICE: service-name  ←  [caller1, caller2]]
```

---

## Shared Resources

| Resource | Type | Used By |
|---|---|---|
[FILL IN OR DELETE THIS SECTION IF NONE]

---

## Flags

| Flagged By | Issue | Date | Resolved |
|---|---|---|---|

---

## Notes

[FREE-FORM ARCHITECTURE DECISIONS — KEEP BRIEF]
```

---

### `_templates/CONTEXT.template.md`

```markdown
---
service: service-name
path: /services/service-name/
status: active
depends_on: []
depended_on_by: []
last_updated: YYYY-MM-DD
---

# Service: service-name

## Purpose
<!-- 2–3 lines max. What does this service do and why does it exist? -->

---

## Current State

- Version:
- API contract:
- Key behaviors:

---

## Architecture Notes
<!-- Compressed long-term memory. Past tense. Max 20 lines. -->
<!-- Each line = a decision or structural fact worth preserving across tasks. -->

---

## Recent Changes
<!-- Last 5 tasks only. Oldest entries get compressed into Architecture Notes. -->
<!-- Format: [YYYY-MM-DD] One-line description of what changed and why. -->

---

## Flags
<!-- ⚑ UNDOCUMENTED | ⚑ STALE | ⚑ REVIEW -->
<!-- Clear once resolved — note resolution in Recent Changes. -->

---

## Interfaces

### Exposes
<!-- Endpoints, events, or exports other services rely on -->

### Consumes
<!-- APIs, queues, or data sources this service calls -->

---

## Do Not
<!-- Hard constraints. Things Claude must not do without explicit instruction. -->
<!-- Leave blank if none. -->
```

---

### `<service-path>/CONTEXT.md`

Use the template above. Fill in:
- `service`, `path`, `status` from user input
- `depends_on`, `depended_on_by` from the relationship answers
- `last_updated` as today's date
- `## Purpose` from what the user described
- All other sections start empty or with `?` for unknowns

---

### `<service-path>/CLAUDE.md`

```markdown
# [Service Name] — Local Instructions

> You are working inside `[/service/path/]`.
> The root `CLAUDE.md` still applies. This file adds service-specific constraints.

## Before Starting

1. Read `CONTEXT.md` in this directory
2. Apply the context triage from root `CLAUDE.md` — load dependent service contexts only if this task crosses a service boundary
3. Check `_master.md` reverse map before changing any exposed interface

## Local Rules

[ASK USER: any frozen endpoints, naming conventions, file layout rules, or hard constraints for this service? If none, leave this section blank or delete it.]

## After Your Task

Run from repo root:
```
scripts/update-context.sh [service-name]
```
```

---

### `scripts/update-context.sh`

```bash
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
```

---

### `scripts/sync-master.sh`

```bash
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
```

---

### `scripts/new-service.sh`

```bash
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
```
