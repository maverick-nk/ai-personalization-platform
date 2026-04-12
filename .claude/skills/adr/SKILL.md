---
name: adr
category: learning
description: Creates an Architecture Decision Record (ADR) capturing a non-trivial design decision — what was decided, what alternatives were considered, the trade-offs, and which system design concepts apply. Produces a permanent, searchable record in docs/decisions/<service>/. Triggers on "/adr", "why did we choose", "document this decision", "record this trade-off", or when a significant design choice is made during implementation.
---

# Architecture Decision Record (ADR)

An ADR captures the *why* behind a design decision at the moment it is clearest — before the context fades. The goal is not documentation for its own sake, but a future reference you can actually use: when you revisit this code in 3 months, the ADR explains what you were trading off, not just what you chose.

Format based on Michael Nygard's ADR template, extended with DDIA concept links.

---

## Step 1 — Gather Context

Ask the user (in one message, wait for full answer):

```
To write the ADR, I need:
1. What did you decide? (one sentence — the actual choice made)
2. What problem were you solving or constraint were you working within?
3. What alternatives did you consider? (even if briefly — list them)
4. What are the main consequences of this choice — what gets easier, what gets harder?
```

If the context is already clear from the recent diff or conversation, pre-fill your best understanding and ask: "Does this capture the decision correctly, or do you want to adjust anything?"

Do not proceed until the user confirms or provides the information.

---

## Step 2 — Identify the Service and Slug

- **Service:** which service this decision belongs to (e.g. `event-ingestion`, `inference-api`, or `shared` for cross-cutting decisions)
- **Slug:** 3–5 word kebab-case title (e.g. `hmac-over-encryption-pseudonymization`, `redis-hash-per-user`, `kafka-for-event-ingestion`)
- **Sequence number:** check `docs/decisions/<service>/` for existing ADRs. The new file gets the next number: `0001-`, `0002-`, etc. If directory is empty, start at `0001-`.

File path: `docs/decisions/<service>/<NNNN>-<slug>.md`

---

## Step 3 — Map to System Design Concepts

From the decision, identify 1–3 relevant DDIA concepts or systems principles. Be specific:

- Not just "distributed systems" — specify "at-least-once vs exactly-once delivery (DDIA Ch 11)"
- Not just "consistency" — specify "read-your-writes consistency (DDIA Ch 5)"
- Not just "storage" — specify "log-structured storage vs B-tree trade-offs (DDIA Ch 3)"

These become revision anchors — when you see the concept in the quiz, you'll have a real decision to ground it in.

---

## Step 4 — Write the ADR

Create the file at the path from Step 2:

```markdown
# <NNNN>. <Title — human-readable version of the slug>

**Date:** <YYYY-MM-DD>  
**Status:** Accepted  
**Service:** <service-name>  
**Decided by:** <user / pair / team>

---

## Context

<2–4 sentences. What situation or constraint prompted this decision?
What would have happened without an explicit choice here?>

---

## Decision

<1–3 sentences. The actual choice made, stated plainly.>

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| <Alternative 1> | <One-line reason it wasn't chosen> |
| <Alternative 2> | <One-line reason it wasn't chosen> |
| *(add more rows as needed)* | |

---

## Consequences

**Gets easier:**
- <What this decision makes simpler or cheaper>

**Gets harder / trade-offs accepted:**
- <What this decision makes more complex, slower, or riskier>

**Constraints this introduces:**
- <Any hard constraints future work must respect as a result of this decision>

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| <concept> | Ch <N> — <topic> | <one sentence> |
| <concept> | Ch <N> — <topic> | <one sentence> |

---

## Related

- ADR(s) this supersedes or is related to: <links or "none">
- CONTEXT.md flag added: <yes/no — if this decision constrains future work, a Do Not entry should be added to the service's CONTEXT.md>
```

---

## Step 5 — Update the Index

Append a row to `docs/decisions/README.md`:

```markdown
| <NNNN> | [<Title>](<service>/<NNNN>-<slug>.md) | <service> | <YYYY-MM-DD> | Accepted |
```

If `docs/decisions/README.md` doesn't exist, create it:

```markdown
# Architecture Decision Records

> Permanent record of non-trivial design decisions made during this project.
> Each ADR captures: decision, alternatives, trade-offs, and relevant DDIA concepts.

| # | Title | Service | Date | Status |
|---|---|---|---|---|
```

---

## Step 6 — Optionally Update CONTEXT.md

If the decision introduces a hard constraint that future work must respect (e.g. "never store raw user_id in Kafka"), add it to the `## Do Not` section of the relevant service's `CONTEXT.md`:

```
- Do not store raw user_id in Kafka payloads — pseudonymization is mandatory (see ADR 0001)
```

Ask: "Should I add a constraint to the service's CONTEXT.md `## Do Not` section?" — if yes, make the edit.

---

## Step 7 — Confirm and Summarise

```
ADR created: docs/decisions/<service>/<NNNN>-<slug>.md
Index updated: docs/decisions/README.md
CONTEXT.md updated: <yes / no>

Concepts anchored:
  - <concept> → DDIA Ch <N>
  - <concept> → DDIA Ch <N>

These will appear in /concept-quiz sessions for <service>.
```
