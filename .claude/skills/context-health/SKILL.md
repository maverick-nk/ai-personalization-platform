---
name: context-health
category: infrastructure
description: Audits the repo context system for staleness, missing coverage, broken dependency references, and open flags — then fixes or reports each finding. Use periodically or before starting a large task. Triggers on phrases like "check context health", "audit context", "context system status", "/context-health", or "are the CONTEXT.md files up to date".
---

# Context Health

This skill runs a full maintenance pass over the repo's context system. It detects drift between documentation and code, and surfaces issues that would cause Claude to work from stale information.

Run this:
- Before starting any Phase 1 service implementation
- When returning to the repo after more than a week away
- After a large merge that touches multiple services

---

## Step 1 — Staleness Check

For every `CONTEXT.md` file in the repo:

1. Read the `last_updated` frontmatter field
2. Compare to today's date
3. Flag any file where `last_updated` is older than **14 days**

Report format:
```
STALE (N days):
  - services/event-ingestion/CONTEXT.md  (last: YYYY-MM-DD)
  - services/inference-api/CONTEXT.md    (last: YYYY-MM-DD)

UP TO DATE:
  - services/privacy/CONTEXT.md
  ...
```

---

## Step 2 — Coverage Check

Find all directories that contain any of: `src/`, `pyproject.toml`, `go.mod`, `package.json`, `Dockerfile`, `main.py`, `main.go`.

Cross-reference against the `## Service Index` in `_master.md`.

Report any directory with implementation files that is **not** listed in `_master.md`:
```
MISSING FROM _master.md:
  - services/new-service/   (has pyproject.toml — no CONTEXT.md)
```

If a new service directory is found, ask: "Should I create a CONTEXT.md for `<path>` now?"
If yes, copy `_templates/CONTEXT.template.md`, fill in what can be inferred, mark unknowns as `?`.

---

## Step 3 — Broken Dependency References

For each `CONTEXT.md`, read the `depends_on` frontmatter list.

For each entry that does NOT end in `*` (i.e. is an internal service, not external):
- Check it exists in the `## Service Index` of `_master.md`
- If missing: flag as broken reference

Report:
```
BROKEN DEPENDENCY REFS:
  - inference-api depends_on: [feature-pipeline] — not in _master.md
```

---

## Step 4 — Open Flags

Search every `CONTEXT.md` for lines containing `⚑`.

Report by service:
```
OPEN FLAGS:
  - inference-api: ⚑ UNDOCUMENTED — Redis key TTL not confirmed
  - privacy: ⚑ STALE — consent table schema changed
```

For each open flag, ask: "Is `<flag>` in `<service>` resolved? If yes, I'll remove it and log it in Recent Changes."

---

## Step 5 — _master.md Sync Check

Run `scripts/sync-master.sh` (or simulate its logic by reading all `CONTEXT.md` frontmatter) and compare the output to what's currently in `_master.md`.

Report any divergence:
```
_master.md OUT OF SYNC:
  - feature-pipeline → depends_on in CONTEXT.md has [kafka*, redis*, parquet*]
    but _master.md shows [kafka*, redis*]  ← missing parquet*
```

If divergences are found, ask: "Should I update `_master.md` to match the current `CONTEXT.md` frontmatter?"

---

## Step 6 — Summary Report

After all checks, output a single summary:

```
Context Health Report — YYYY-MM-DD
───────────────────────────────────
Stale CONTEXT.md files:     N  (listed above)
Missing from _master.md:    N
Broken dependency refs:     N
Open flags:                 N
_master.md sync issues:     N

Overall: HEALTHY / NEEDS ATTENTION
```

If everything is clean: "Context system is healthy — no action needed."

If issues were found and fixed during this run: list what was changed.
If issues remain unresolved: list what needs manual review.
