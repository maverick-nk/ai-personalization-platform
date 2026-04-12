---
name: concept-quiz
description: After each sub-feature implementation, maps what was built to system design concepts from "Designing Data-Intensive Applications" (Kleppmann) and related systems literature, then tests understanding via interactive MCQs. Stores questions, answers, scores, and reasoning in docs/sys-design-concepts/<service>.md. Triggers on "/concept-quiz", "test my knowledge", "quiz me", "what concepts did we use", or "system design concepts".
---

# Concept Quiz

This skill turns implementation work into active learning. After building a sub-feature, it identifies the system design concepts exercised, tests understanding interactively, and builds a persistent knowledge log per service.

Primary reference: **"Designing Data-Intensive Applications" — Martin Kleppmann (DDIA)**
Secondary references: distributed systems literature, database internals, streaming systems papers.

---

## Step 1 — Identify What Was Just Built

Read the recent diff:

```bash
git diff HEAD~1 HEAD
```

Or if the sub-feature spans multiple commits since the branch was created:

```bash
git diff main...HEAD
```

Extract:
- **Service:** which service directory changed
- **Sub-feature:** one-line description (e.g. "Kafka producer with pseudonymized user IDs")
- **Key implementation decisions:** data structures used, protocols, failure modes handled, guarantees made or assumed

If the diff is ambiguous, ask: "What sub-feature did you just finish?" — one question, wait for answer.

---

## Step 2 — Load the Concept Coverage File

Check if `docs/sys-design-concepts/<service>.md` exists.

If it exists: read the `## Concept Coverage` table. Extract:
- Concepts already tested
- Best score per concept
- Mark any concept with **best score ≥ 80%** as `SKIP` — do not generate questions for it unless it appears in a new, meaningfully different context

If the file does not exist: create it now using the template in **Section 7** below. All concepts start fresh.

---

## Step 3 — Map Implementation to Concepts

From the diff and Step 1 analysis, identify which system design concepts are exercised. Use this concept map as a guide — it is not exhaustive, add concepts as appropriate:

### Event Ingestion API
| What was built | Concepts to test |
|---|---|
| Kafka producer | Message brokers, log-structured storage, at-least-once vs exactly-once delivery, producer acknowledgements |
| Pseudonymization (HMAC) | Data anonymisation vs pseudonymisation, hash functions, key management |
| Schema validation | Schema evolution, forward/backward compatibility, Avro vs JSON vs Protobuf trade-offs |
| REST API endpoint | Synchronous vs asynchronous communication, idempotency, HTTP semantics |

### Streaming Feature Pipeline
| What was built | Concepts to test |
|---|---|
| Kafka consumer | Consumer groups, partition assignment, offset management, at-least-once processing |
| Sliding window feature | Stream processing windows (tumbling, sliding, session), watermarks, late data |
| Redis write | In-memory data structures, TTL, cache eviction policies, write-through vs write-behind |
| Parquet sink | Columnar storage, predicate pushdown, partitioning strategies, offline vs online stores |
| Feature computation | Feature drift, training/serving skew, idempotent transformations |

### Privacy Service
| What was built | Concepts to test |
|---|---|
| Postgres consent table | ACID transactions, isolation levels, write durability |
| Consent check middleware | Read-your-writes consistency, linearisability vs eventual consistency |
| Audit log | Append-only log, immutability, event sourcing pattern |
| Revocation flow | Consistency models — what guarantees does immediate revocation require? |

### Inference API
| What was built | Concepts to test |
|---|---|
| Redis feature fetch | Cache-aside pattern, hot key problem, read latency tail |
| gRPC endpoint | RPC vs REST, protocol buffers, connection multiplexing |
| Model hot-swap | Blue-green deployment, atomic pointer swap, in-process versioning |
| Cold-start fallback | Graceful degradation, fallback strategies, circuit breaker pattern |
| Consent interceptor | Middleware/interceptor pattern, fail-open vs fail-closed |

### Model Training Pipeline
| What was built | Concepts to test |
|---|---|
| Parquet reader | Batch vs stream processing, data locality, predicate pushdown |
| MLflow registration | Model versioning, artifact stores, lineage tracking |
| Feature schema contract | Schema registry, preventing training/serving skew |
| Train/validation split | Temporal vs random splits — why temporal matters for time-series ML |

### Infrastructure / Docker
| What was built | Concepts to test |
|---|---|
| Kafka + Zookeeper setup | Distributed coordination, leader election, ZooKeeper's role (and KRaft replacing it) |
| Redis configuration | Persistence modes (RDB vs AOF), replication, single-threaded event loop |
| Postgres setup | WAL, checkpointing, MVCC |
| Health checks | Liveness vs readiness probes, failure detection |

---

## Step 4 — Determine Question Count

Scale question count to the complexity and scope of the sub-feature:

| Sub-feature complexity | Question count |
|---|---|
| Single function / utility (e.g. pseudonymization helper) | 3–5 |
| Single component with one external dependency (e.g. Redis writer) | 5–8 |
| Full integration across two systems (e.g. Kafka producer + schema validation) | 8–12 |
| End-to-end flow or full service bootstrap | 12–15 |

Maximum: **15 questions**. Never exceed this regardless of complexity.

Skip questions on SKIP-flagged concepts (scored ≥ 80% previously) unless the new context makes them genuinely different. If skipping reduces count below 3, include 1–2 SKIP-concept questions at increased difficulty (scenario-based or trade-off).

---

## Step 5 — Generate Questions

Generate the questions before presenting them. Each question must be one of:

**Type A — Concept definition/recall**
Tests whether the user knows what a term means and when it applies.
> "Kafka provides at-least-once delivery by default. What does this mean for a consumer processing watch events?"
> A) Each event is processed exactly once regardless of failures
> B) Each event is processed at least once; duplicates are possible on failure/retry
> C) Events may be skipped if the broker crashes before acknowledgement
> D) Each event is processed at most once to avoid duplicate side effects

**Type B — Trade-off reasoning**
Tests whether the user understands *why* a design decision was made.
> "We chose HMAC-SHA256 for pseudonymization rather than encryption. What is the key trade-off?"
> A) HMAC is reversible; encryption is not — we chose HMAC to allow recovery of original user IDs
> B) HMAC is a one-way function — it cannot be reversed, making it suitable for pseudonymization where the original ID must never be recoverable from the token alone
> C) HMAC is faster than encryption, so it reduces API latency below 50ms
> D) Encryption requires a key rotation policy; HMAC does not

**Type C — Scenario-based**
Presents a production situation and asks what will happen or what to do.
> "The feature pipeline crashes mid-window and restarts from the last committed Kafka offset. A user had 8 watch events in the last 10 minutes, 3 of which were already written to Redis before the crash. What does the user's `watch_count_10min` show immediately after recovery?"
> A) 8 — Flink re-reads all events from the offset and recomputes correctly
> B) 3 — only the pre-crash writes survive in Redis
> C) 11 — the 8 events are reprocessed and added to the existing 3 in Redis
> D) 0 — Redis TTL expired during the crash window

Always include 4 options (A–D). One correct answer. No "all of the above" or "none of the above".

---

## Step 6 — Run the Quiz Interactively

Present questions **one at a time**. Do not reveal the answer until the user responds.

Format for each question:

```
─────────────────────────────────────────────────
Q<N> of <total> · [Type: Concept / Trade-off / Scenario] · Topic: <concept name>
─────────────────────────────────────────────────
<Question text>

A) ...
B) ...
C) ...
D) ...

Your answer (A/B/C/D):
```

After the user answers:

**If correct:**
```
✓ Correct.

<2–4 sentence explanation of why this is right, anchored to DDIA chapter/concept
or specific behaviour in this codebase. Always explain, even when correct —
the reasoning matters as much as the answer.>

DDIA ref: Chapter <N> — <topic> (if applicable)
```

**If incorrect:**
```
✗ Incorrect. The answer is <X>.

<2–4 sentence explanation of why the correct answer is right and why the user's
choice was wrong. Be specific — don't just restate the correct answer.>

DDIA ref: Chapter <N> — <topic> (if applicable)
```

After the final question, print the session score:

```
─────────────────────────────────────────────────
Quiz complete: <N>/<total> correct (<pct>%)
─────────────────────────────────────────────────
Weak areas to revisit: <list concepts scored 0/1 if any>
Strong: <list concepts scored 1/1>
```

---

## Step 7 — Write Results to File

Append the session to `docs/sys-design-concepts/<service>.md`.

**If the file does not exist**, create it with this structure first:

```markdown
# System Design Concepts — <service-name>

> Quiz log for the `<service-name>` service.
> Reference: "Designing Data-Intensive Applications" — Martin Kleppmann
> Concepts scored ≥ 80% are deprioritised in future sessions.

---

## Concept Coverage

| Concept | Times Tested | Best Score | Last Tested |
|---|---|---|---|

---

## Sessions

```

**After each session**, do two things:

**a. Update the Concept Coverage table** — for each concept tested this session:
- If the concept is already in the table: increment `Times Tested`, update `Best Score` if this session score is higher, update `Last Tested`
- If new: add a new row

**b. Append the session record** under `## Sessions`:

```markdown
### <YYYY-MM-DD> · <sub-feature description>

**Score: <N>/<total> (<pct>%)**  
**Concepts tested:** <comma-separated list>

---

**Q1 · [Concept] · <concept name>**
<question text>

- A) ...
- B) ...
- C) ...
- D) ...

**User answered:** <X> · **Correct:** <Y> · <✓ / ✗>

> <Full explanation — same text shown during the quiz>
> DDIA ref: <if applicable>

---

**Q2 · ...**
...

---
```

Sessions are appended in chronological order (newest at the bottom).

---

## Step 8 — Handoff

After writing the file, print:

```
Results saved to docs/sys-design-concepts/<service>.md

Concepts now at ≥ 80% (will be deprioritised): <list or "none yet">
Concepts to revisit: <list or "none">

Continue building, or run /concept-quiz again after the next sub-feature.
```

---

## DDIA Chapter Reference (Quick Lookup)

| Chapter | Topics |
|---|---|
| Ch 1 — Reliable, Scalable, Maintainable | Reliability, scalability, maintainability, load parameters |
| Ch 2 — Data Models and Query Languages | Relational vs document vs graph, schema-on-read vs schema-on-write |
| Ch 3 — Storage and Retrieval | LSM trees, B-trees, SSTables, column storage, Parquet |
| Ch 4 — Encoding and Evolution | Avro, Protobuf, Thrift, schema evolution, forward/backward compatibility |
| Ch 5 — Replication | Leader-follower, replication lag, read-your-writes, monotonic reads |
| Ch 6 — Partitioning | Key-range vs hash partitioning, hot spots, secondary indexes |
| Ch 7 — Transactions | ACID, isolation levels, read committed, snapshot isolation, serializability |
| Ch 8 — Distributed Systems Trouble | Unreliable networks, clocks, process pauses, truth in distributed systems |
| Ch 9 — Consistency and Consensus | Linearisability, CAP, ordering guarantees, Zookeeper, leader election |
| Ch 10 — Batch Processing | MapReduce, dataflow, joins in batch systems |
| Ch 11 — Stream Processing | Event streams, Kafka, stream-table duality, windowing, watermarks, exactly-once |
| Ch 12 — Future of Data Systems | Lambda vs Kappa architecture, end-to-end correctness, data privacy |
