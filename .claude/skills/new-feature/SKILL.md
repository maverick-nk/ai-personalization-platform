---
name: new-feature
description: Creates a correctly-named branch, loads the right service CONTEXT.md, and sets up the working context before starting any feature or fix. Use at the start of every implementation task. Triggers on phrases like "start work on", "implement", "begin feature", "new feature", "/new-feature", or when the user names a service and a task together.
---

# New Feature

This skill is the entry point for all implementation work. It enforces branch naming conventions, loads only the minimum required context, and ensures nothing is built on the wrong branch.

---

## Step 1 — Parse the Request

Extract from the user's message:

- **Service(s):** which service(s) will be touched (e.g. `event-ingestion`, `inference-api`)
- **Task type:** use the prefix table below to pick the right branch prefix
- **Short slug:** 2–4 word kebab-case description of the work (e.g. `kafka-producer`, `consent-check-middleware`)

Branch prefix table:

| Work type | Prefix |
|---|---|
| New service or feature | `feat/` |
| Infrastructure, Docker, Kubernetes, config | `infra/` |
| Bug fix | `fix/` |
| Test harness or load tests | `test/` |
| CI/CD pipelines | `ci/` |
| Documentation only | `docs/` |
| Dependency bumps, cleanup, tooling | `chore/` |

If ambiguous, ask: "Is this a new feature (`feat/`) or a bug fix (`fix/`)?" — one question, wait for answer.

Proposed branch name format: `<prefix>/<service>-<slug>` or `<prefix>/<slug>` if multi-service.

State the proposed branch name and ask: "Branch off `main`?" — if the user says a different base, use that.

---

## Step 2 — Create the Branch

```bash
git checkout <base>
git checkout -b <branch-name>
```

Confirm the branch is active before proceeding.

---

## Step 3 — Load Context (Minimum Required)

Read `_master.md` first. Then apply the context triage rule from root `CLAUDE.md`:

**Always load:** `CONTEXT.md` for each service directly named in the task.

**Load a dependency's `CONTEXT.md` only if the task involves:**
- Adding or changing a call to its API, queue, or data source
- Changing a contract that dependency relies on
- Modifying shared config or data structures used across services

**Skip dependency context if the task is:**
- Refactoring or optimizing logic inside one service
- Fixing a bug confirmed to be within one service
- Adding unit tests that don't cross service boundaries

After reading the required `CONTEXT.md` files, state in one sentence: "Loaded context for: [list]. Skipped: [list] — not needed for this task."

---

## Step 4 — Summarise and Hand Off

Output a short task brief:

```
Branch:   <branch-name>
Service:  <service(s)>
Context:  <CONTEXT.md files loaded>
Task:     <one-line description of what will be implemented>

Key constraints to keep in mind:
- <pull 2–3 relevant constraints from the service CONTEXT.md ## Do Not section or root CLAUDE.md>
```

Then say: "Ready — what should I implement first?"

Do not start writing code until the user confirms or gives the first implementation instruction.

---

## Step 5 — Remind at End of Task

When the implementation task is complete, prompt:

```
Task complete. Before raising a PR:
  1. Run /service-done <service> to update CONTEXT.md
  2. Run /ship-pr to review and raise the pull request
```
