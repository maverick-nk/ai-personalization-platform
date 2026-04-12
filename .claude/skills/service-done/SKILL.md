---
name: service-done
description: End-of-task wrapper that updates CONTEXT.md for each service touched, resolves open flags, syncs _master.md if dependencies changed, and hands off to ship-pr. Run after completing any implementation task before raising a PR. Triggers on phrases like "task done", "I'm done", "wrap up", "finish up", "update context", "/service-done", or when the user names a service and says the work is complete.
---

# Service Done

This skill closes out an implementation task cleanly: updates the context system, resolves flags, checks for dependency drift, and hands off to `/ship-pr`. It ensures the context system stays accurate so future tasks don't work from stale information.

Accepts one or more service names as arguments:
- `/service-done event-ingestion`
- `/service-done inference-api privacy`

If no service is named, ask: "Which service(s) did you just work on?"

---

## Step 1 — Read Current State of Each Service

For each service named, read its `CONTEXT.md`. Note:
- `## Current State` — version, API contract, key behaviors
- `## Recent Changes` — how many entries exist (max 5 before compression)
- `## Flags` — any open `⚑` entries
- `## Interfaces` — exposes / consumes sections

Do not start updating yet — gather state first.

---

## Step 2 — Ask for Change Summary

For each service, ask in one message:

```
For <service-name>:
1. One-line summary of what changed (e.g. "Added Kafka producer for watch events")
2. Did any exposed interfaces change? (endpoints, Kafka topics, Redis key patterns, gRPC RPCs)
3. Did any new dependencies appear? (new services, queues, or data stores this service now calls)
4. Were any open flags resolved?
```

Wait for answers before proceeding.

---

## Step 3 — Update CONTEXT.md for Each Service

For each service, apply these updates in order:

**a. Recent Changes** — prepend a new dated entry:
```
- [YYYY-MM-DD] <change summary from Step 2>
```

If the entry count after adding exceeds 5, compress the oldest entries:
- Combine the 3 oldest into a single Architecture Notes bullet
- Remove them from Recent Changes
- Add to `## Architecture Notes`: `[Compressed YYYY-MM-DD] <summary of compressed entries>`

**b. Current State** — update if anything structural changed:
- Version (if the service now has one)
- API contract (if it changed)
- Key behaviors (if new behaviors were added)

**c. Interfaces** — if any exposed interface changed (new endpoint, new Kafka topic, changed payload):
- Update `### Exposes` with the new or changed interface
- Mark any removed interfaces as `[removed YYYY-MM-DD]` rather than silently deleting

**d. Flags** — for each resolved flag:
- Remove the `⚑` line
- Add a note in Recent Changes: "Resolved flag: <flag description>"

**e. Frontmatter** — update `last_updated` to today's date.

---

## Step 4 — Check for New Dependencies

If the user reported new dependencies in Step 2:

1. Add them to the `depends_on` frontmatter of the service's `CONTEXT.md`
2. Add a reciprocal entry to the `depended_on_by` of the dependency's `CONTEXT.md`
3. Flag `_master.md` as needing sync

---

## Step 5 — Sync _master.md (if dependencies changed)

If Step 4 found new or removed dependencies, run:

```bash
scripts/sync-master.sh
```

Review the output and apply the updated Dependency Map and Reverse Map sections to `_master.md`.

Update `Last synced:` date in `_master.md`.

If `sync-master.sh` is not yet available (infra not bootstrapped):
- Manually update the relevant lines in `_master.md`'s `## Dependency Map` and `## Reverse Map` sections

---

## Step 6 — Interface Change Blast Radius Check

If any **exposed** interface changed (endpoint URL, Kafka topic name, Redis key pattern, gRPC RPC, feature schema):

Look up the service in `_master.md`'s `## Reverse Map`. For each caller listed:

```
⚠ Interface change detected in <service>.
  The following services depend on it: [list from reverse map]
  
  For each: does this change require updating their CONTEXT.md or code?
```

If yes: either load those services' `CONTEXT.md` now and add a `⚑ REVIEW` flag, or ask the user to handle it in a follow-up task.

Do not silently skip this check — interface changes breaking callers is the most common cause of integration bugs in this codebase.

---

## Step 7 — Summary and Handoff

Print a brief wrap-up:

```
Service Done — <service(s)>
───────────────────────────────────────
Updated CONTEXT.md:      event-ingestion
Flags resolved:          0
New dependencies:        none
_master.md synced:       no (no dep changes)
Interface blast radius:  none

Ready for PR. Run /ship-pr to review and raise.
```

If there are unresolved items (e.g. caller services that need review), list them under "Follow-up needed before merging".

Then say: "Run `/ship-pr` when ready."
