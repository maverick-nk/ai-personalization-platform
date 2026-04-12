---
name: incident
description: Documents a bug, test failure, or unexpected system behaviour as a structured incident log entry. Captures symptoms, root cause, fix, and the DDIA concept that explains why it happened — turning production bugs into permanent learning records. Triggers on "/incident", "log this bug", "document this failure", "test is failing", or when a significant bug or unexpected behaviour is encountered during development.
---

# Incident Log

Every bug you hit while building this system is a distributed systems concept playing out in your own code. This skill captures that moment: what failed, why, what the fix was, and — most importantly — which system design principle it violated or confirmed.

Over time, `docs/incidents/` becomes a personal war stories file: a searchable record of real failures grounded in DDIA concepts.

---

## Step 1 — Capture the Failure

Ask the user (or infer from context if already described):

```
To log this incident:
1. What failed? (symptoms — what did you observe, what test failed, what error appeared)
2. Which service or component was involved?
3. Have you found the root cause yet, or are you still debugging?
```

If still debugging: write a partial incident log now (symptoms + hypothesis) and mark status `Investigating`. Come back later with `/incident update` to fill in root cause and fix.

If root cause is known: proceed through all steps.

---

## Step 2 — Classify the Incident

Assign a **type** based on what kind of failure it is:

| Type | Description | Typical DDIA chapter |
|---|---|---|
| `delivery-guarantee` | Message lost, duplicated, or processed out of order | Ch 11 |
| `consistency` | Stale read, read-your-writes violation, dirty read | Ch 5, Ch 7 |
| `data-loss` | Data not persisted, TTL expired unexpectedly, write not durable | Ch 3, Ch 7 |
| `schema-skew` | Training/serving feature mismatch, type mismatch, missing field | Ch 4, Ch 11 |
| `latency-slo` | p95/p99 exceeded, timeout, slow path hit under load | Ch 1 |
| `privacy-violation` | Raw user_id leaked, PII in logs, consent not enforced | Ch 12 |
| `race-condition` | Concurrent writes, TOCTOU, non-atomic operation | Ch 7, Ch 8 |
| `network-partition` | Service unreachable, partial failure, timeout behaviour | Ch 8 |
| `config-error` | Wrong topic name, wrong key pattern, misconfigured TTL | — |
| `other` | Doesn't fit above — describe freely | — |

---

## Step 3 — Identify the DDIA Concept

Map the root cause to a specific DDIA concept. Be precise:

- Not "Kafka was slow" → "Consumer lag under backpressure — DDIA Ch 11: backpressure in stream processing"
- Not "Redis returned wrong data" → "Read-your-writes consistency — DDIA Ch 5: replication lag with asynchronous followers"
- Not "test was flaky" → "Non-deterministic window boundary — DDIA Ch 11: watermarks and late-arriving data"

If you can't map it to DDIA, use another reference (Google SRE Book, database internals, etc.) or mark it `unmapped` and describe the principle in plain English.

---

## Step 4 — Write the Incident Log Entry

Generate a filename: `docs/incidents/<YYYY-MM-DD>-<slug>.md`

Slug: 3–5 word kebab-case description of the failure (e.g. `kafka-duplicate-watch-events`, `redis-stale-feature-read`, `consent-check-race-condition`).

```markdown
# <Slug — human readable title>

**Date:** <YYYY-MM-DD>  
**Service:** <service-name>  
**Type:** <type from Step 2>  
**Status:** <Investigating / Resolved>  
**Severity:** <Low / Medium / High>
> High = data loss, privacy violation, or SLO breach in test harness
> Medium = test failure, wrong output, functional regression
> Low = unexpected behaviour caught before any test ran

---

## Symptoms

<What was observed. Error message, test output, wrong value, unexpected behaviour.
Paste exact error text if available — not paraphrased.>

```
<exact error or test output here if applicable>
```

---

## Root Cause

<What actually caused it. Be specific — name the line, the assumption that was wrong,
the missing guarantee, the race condition.>

---

## Fix Applied

<What was changed to resolve it. If still Investigating, write "TBD".>

---

## Why It Happened — Systems Concept

**Concept:** <Name of the system design concept>  
**DDIA Reference:** Ch <N> — <topic> *(or other reference)*

<2–4 sentences explaining the connection between this bug and the concept.
Not just what the concept is — explain specifically how it manifested here.>

---

## What Would Have Prevented It

- <Guard, test, constraint, or design pattern that would have caught or avoided this>
- <e.g. "An idempotency key on the Kafka consumer would have prevented double-processing">
- <e.g. "A schema registry check before writing to Redis would have caught the type mismatch">

---

## Related

- ADR(s) relevant to this failure: <links or "none">
- Follow-up task created: <yes/no — describe if yes>
- Added to `/concept-quiz` weak areas: <yes/no>
```

---

## Step 5 — Update the Incident Index

Append to `docs/incidents/README.md`:

```markdown
| <YYYY-MM-DD> | [<Title>](<YYYY-MM-DD>-<slug>.md) | <service> | <type> | <severity> | <status> |
```

If `docs/incidents/README.md` doesn't exist, create it:

```markdown
# Incident Log

> Real bugs encountered while building the platform — each mapped to a system design concept.
> These are learning records, not post-mortems. Severity reflects impact during development.

| Date | Incident | Service | Type | Severity | Status |
|---|---|---|---|---|---|
```

---

## Step 6 — Cross-Link to Concept Quiz

If the incident maps to a concept that appears in `docs/sys-design-concepts/<service>.md`:

- Check if that concept has a score < 80% in the coverage table
- If so, note: "This concept is already flagged for review in your quiz log."
- If the concept isn't yet in the quiz log (e.g. it's a new concept not yet tested): note "Run `/concept-quiz` — this concept should now be included."

If the incident reveals a concept gap not currently covered by any quiz session, suggest it explicitly:

```
⚠ This incident surfaced <concept> — not yet tested in your quiz log.
  Run /concept-quiz and mention "<concept>" to prioritise it.
```

---

## Step 7 — Confirm

```
Incident logged: docs/incidents/<YYYY-MM-DD>-<slug>.md
Index updated:   docs/incidents/README.md
Status:          <Investigating / Resolved>

Concept anchored: <concept> → DDIA Ch <N>

<If Investigating>:
  When resolved, run /incident to update with root cause and fix.
```

---

## Updating an Investigating Incident

If the user runs `/incident` and mentions a previously open incident, locate the file and update:
- Change `Status: Investigating` → `Status: Resolved`
- Fill in `## Root Cause`, `## Fix Applied`, `## Why It Happened`
- Update the index row status
- Run the concept quiz cross-link check from Step 6
