---
name: ship-pr
description: Reviews the current branch, checks code quality, then raises a pull request with consistent formatting aligned to this repo's conventions. Use when a feature branch is ready to merge. Triggers on phrases like "raise a PR", "open a PR", "ship this", "create a pull request", "review and raise", or "/ship-pr".
---

# Ship PR

This skill reviews staged changes for quality issues, then creates a pull request with a consistent title, summary, and test plan — following the branch and PR conventions in `docs/implementation-plan.md`.

---

## Step 1 — Verify Branch State

Before anything else:

1. Run `git branch --show-current` — confirm you are NOT on `main`. If on `main`, stop and tell the user.
2. Run `git status` — confirm there are no uncommitted changes. If there are, ask: "There are uncommitted changes. Commit them first, or should I include them in this PR?"
3. Run `git log main..HEAD --oneline` — list commits that will be in the PR. If empty, stop: "No commits ahead of main — nothing to PR."
4. Run `git diff main...HEAD` — read the full diff to understand what changed.

State the branch name and commit count in one line before proceeding.

---

## Step 2 — Code Review

Read the diff from Step 1. Check for:

**Correctness**
- Logic errors or off-by-one mistakes
- Unhandled error paths at service boundaries (Kafka, Redis, Postgres, gRPC)
- Missing schema validation on ingress points

**Privacy & Security**
- Raw `user_id` or PII appearing in logs, Kafka payloads, Redis keys, or Parquet
- Secrets or credentials hardcoded or committed
- SQL constructed via string concatenation (injection risk)

**Contract compliance**
- Kafka topic names match `_master.md` (`user.watch.events`, `user.session.events`)
- Redis key pattern matches `user:{pseudo_id}:features`
- Feature names match the 6 defined in CLAUDE.md
- gRPC proto changes that would break the Inference API contract

**Operational readiness**
- No `print()` / `fmt.Println()` debug statements left in
- Prometheus metrics instrumented for any new endpoints or hot paths
- Context update: does `CONTEXT.md` for affected services need updating?

If issues are found:
- List them grouped by severity: **blocking** (must fix before PR) vs **non-blocking** (note in PR, fix later)
- For blocking issues: fix them before proceeding, or ask the user if they want to proceed anyway
- For non-blocking issues: add them to the PR body under `## Known issues / follow-ups`

If no issues are found: state "Review passed — no issues found." and proceed.

---

## Step 3 — Determine PR Metadata

From the branch name and diff, derive:

**Title** (under 70 chars): Use the branch prefix as a signal:
- `feat/*` → "Add <thing>"
- `fix/*` → "Fix <thing>"
- `infra/*` → "Set up / Configure <thing>"
- `ci/*` → "Add CI pipeline for <thing>"
- `test/*` → "Add tests for <thing>"
- `docs/*` → "Document <thing>"
- `chore/*` → "Bump / Clean up <thing>"

**Labels** (suggest, don't set automatically):
- `feat/*` → `feature`
- `fix/*` → `bug`
- `infra/*` → `infrastructure`
- `ci/*` → `ci`
- `docs/*` → `docs`

**Base branch:** `main` unless the user says otherwise.

---

## Step 4 — Build Test Plan

Based on what changed, generate a checklist of things to verify:

- If the change touches an API endpoint → include a curl / test call example
- If it touches Kafka → confirm topic exists and message lands
- If it touches Redis → confirm key pattern and TTL
- If it touches Postgres → confirm migration ran cleanly
- If it touches the feature schema → confirm Parquet and Redis schemas match
- If it touches the Inference API → confirm GetRecommendations returns valid response
- Always include: "Run test harness: `pytest tests/` — all scenarios pass"

---

## Step 5 — Push and Create PR

1. Run `git push -u origin <branch>` if the branch has no remote tracking ref yet
2. Create the PR using `gh pr create` with this exact body structure:

```
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
- <bullet 1 — what changed>
- <bullet 2 — why / motivation>
- <bullet 3 — any notable design decision, if relevant>

## Services touched
<!-- List services modified. Link to their CONTEXT.md -->
- `<service-name>` — <one-line description of change>

## Test plan
- [ ] <item from Step 4>
- [ ] <item from Step 4>
- [ ] Run test harness: `pytest tests/` — all scenarios pass

## Known issues / follow-ups
<!-- Non-blocking issues from Step 2, or leave blank -->

## Context update
- [ ] Ran `scripts/update-context.sh <service>` for each service touched

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

3. Output the PR URL to the user.

---

## Step 6 — Post-PR Reminders

After the PR is created, remind the user:

- If any `CONTEXT.md` files need updating: "Run `scripts/update-context.sh <service>` for: [list]"
- If `_master.md` needs a new dependency entry: "Update `_master.md` and run `scripts/sync-master.sh`"
- If non-blocking issues were noted: "Follow-up tasks logged in the PR description"
