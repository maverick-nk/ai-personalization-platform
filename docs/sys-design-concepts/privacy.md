# System Design Concepts — privacy

> Quiz log for the `privacy` service.
> Reference: "Designing Data-Intensive Applications" — Martin Kleppmann
> Concepts scored ≥ 80% are deprioritised in future sessions.

---

## Concept Coverage

| Concept | Times Tested | Best Score | Last Tested |
|---|---|---|---|
| ACID atomicity | 1 | 100% | 2026-04-30 |
| Consistency vs availability (CAP) | 1 | 100% | 2026-04-30 |
| Fail-safe defaults | 1 | 100% | 2026-04-30 |
| Append-only log and event sourcing | 1 | 100% | 2026-04-30 |
| Range partitioning (TTL via DROP) | 1 | 100% | 2026-04-30 |
| Partition key constraints (IDENTITY, composite PK) | 1 | 100% | 2026-04-30 |
| Read-your-writes consistency | 1 | 100% | 2026-04-30 |
| Opt-in consent default | 1 | 100% | 2026-04-30 |
| Async ORM session lifecycle (expire_on_commit) | 1 | 100% | 2026-04-30 |
| Write-ahead log and durability | 1 | 100% | 2026-04-30 |
| Hot/cold data tiering | 1 | 100% | 2026-04-30 |
| Isolation levels and concurrent writes | 1 | 0% | 2026-04-30 |

---

## Sessions

### 2026-04-30 · Full privacy service — consent table, partitioned audit log, consent check middleware, revocation flow, fail-closed design

**Score: 11/12 (92%)**  
**Concepts tested:** ACID atomicity, Consistency vs availability (CAP), Fail-safe defaults, Append-only log and event sourcing, Range partitioning (TTL via DROP), Partition key constraints, Read-your-writes consistency, Opt-in consent default, Async ORM session lifecycle, Write-ahead log and durability, Hot/cold data tiering, Isolation levels and concurrent writes

---

**Q1 · [Concept] · ACID atomicity**
The consent endpoint writes to both `consent` and `audit_log` in a single session with a single `await session.commit()`. What property ensures either both writes succeed or neither does?

- A) Durability — committed data survives crashes
- B) Atomicity — the commit is all-or-nothing
- C) Isolation — concurrent transactions cannot interleave
- D) Consistency — the database enforces foreign key constraints

**User answered:** B · **Correct:** B · ✓

> Atomicity is the "A" in ACID. A transaction is the unit of work — either all statements commit together, or none do. If the audit insert raises, SQLAlchemy rolls back the entire transaction, leaving the consent table unchanged.
> DDIA ref: Chapter 7 — Transactions

---

**Q2 · [Trade-off] · Consistency vs availability (CAP)**
ADR 0007 chose to degrade personalization for ALL users during a privacy service outage rather than cache last-known consent. In CAP terms, which side does this place inference-api on?

- A) AP — favours availability over consistency
- B) CP — favours consistency (consent never stale) over availability (personalization degrades)
- C) Neither — CAP only applies to distributed databases
- D) CP — but only for users who revoked consent

**User answered:** B · **Correct:** B · ✓

> Deliberate CP-side choice at a compliance boundary. If the system cannot get a definitive consent answer, it assumes the restrictive default rather than proceeding optimistically. The cost is availability; the benefit is that a revoked user can never receive personalized content during an outage.
> DDIA ref: Chapter 9 — Consistency and Consensus

---

**Q3 · [Scenario] · Fail-safe defaults**
The inference-api calls the privacy service with a 4ms timeout. The service is overloaded and takes 20ms to respond. What happens?

- A) The inference-api waits 20ms and receives consent_granted=true — timeout only applies to connection establishment
- B) Timeout fires at 4ms; inference-api treats result as consent_granted=false and returns trending fallback
- C) Timeout fires at 4ms; inference-api returns 504 Gateway Timeout
- D) Timeout fires at 4ms; inference-api retries with 10ms timeout before falling back

**User answered:** B · **Correct:** B · ✓

> The timeout is a hard deadline on the entire round-trip. Any error or timeout is treated as consent_granted=false (fail closed), returning the trending fallback — never a 5xx. Retrying inside the same request adds latency and worsens overload.
> DDIA ref: Chapter 8 — Trouble with Distributed Systems

---

**Q4 · [Concept] · Append-only log and event sourcing**
The audit_log is append-only; consent table holds only current state. Which event sourcing pattern does this implement?

- A) audit_log is the WAL — crash-recovery for the consent table
- B) consent table is the event log; audit_log is a materialized view
- C) audit_log is the event log (immutable history); consent table is a materialized view of current state
- D) Both are event logs — neither is authoritative

**User answered:** C · **Correct:** C · ✓

> Event sourcing: audit_log is the immutable source of truth for what happened and when. The consent table is a projection holding only the latest state for fast lookups. The consent table could be reconstructed from audit_log; the reverse is not true.
> DDIA ref: Chapter 12 — The Future of Data Systems

---

**Q5 · [Trade-off] · Range partitioning (TTL via DROP)**
Why is `DROP TABLE audit_log_YYYY_MM` preferable to `DELETE FROM audit_log WHERE timestamp < cutoff` for TTL at scale?

- A) DROP bypasses MVCC, so it runs faster under high write concurrency
- B) DELETE is row-by-row: holds locks, generates WAL per row, requires VACUUM — DROP is O(1) DDL with no WAL bloat
- C) DELETE requires a full table scan because timestamp is not indexed on partitioned tables
- D) DROP also removes associated indexes; DELETE leaves orphaned index entries

**User answered:** B · **Correct:** B · ✓

> DELETE marks each row dead (MVCC tombstone), writes WAL per row, and requires VACUUM. On millions of rows this is O(N) with lock contention. DROP TABLE removes the partition's file in one DDL statement regardless of row count — O(1), no per-row WAL, no VACUUM.
> DDIA ref: Chapter 6 — Partitioning

---

**Q6 · [Concept] · Partition key constraints (IDENTITY, composite PK)**
Why did the migration use `GENERATED ALWAYS AS IDENTITY` instead of `SERIAL`, and why is the PK `(id, timestamp)` instead of just `(id)`?

- A) SERIAL propagates automatically; composite PK is for the lack of a natural unique key
- B) SERIAL sequences are not propagated to child partitions; PostgreSQL requires the partition key in every unique constraint on a partitioned table
- C) IDENTITY is faster; composite PK prevents duplicate (id, timestamp) pairs across partitions
- D) Both are SQLAlchemy ORM requirements

**User answered:** B · **Correct:** B · ✓

> Two independent PostgreSQL constraints: (1) SERIAL sequences live on the parent and are not inherited by child partitions — IDENTITY propagates correctly. (2) PostgreSQL cannot enforce cross-partition uniqueness, so the partition key must appear in every unique constraint including the PK.
> DDIA ref: Chapter 6 — Partitioning

---

**Q7 · [Concept] · Read-your-writes consistency**
A user revokes consent (committed). 1ms later the inference-api checks consent. What consistency guarantee applies, and does our implementation provide it?

- A) Monotonic reads — once revocation is seen, older state is never returned
- B) Read-your-writes — both write and read hit the same Postgres primary with no replication lag
- C) Linearizability — via SQLAlchemy's session isolation level
- D) Eventual consistency — brief window where old state may be returned

**User answered:** B · **Correct:** B · ✓

> Read-your-writes: the privacy service is the single writer and reader of consent state, both hitting the same Postgres primary. No replication lag exists between write and read paths. A read replica would introduce a violation window where a revoked user could still receive personalized content.
> DDIA ref: Chapter 5 — Replication

---

**Q8 · [Trade-off] · Opt-in consent default**
Why does the privacy service treat a missing consent record as consent_granted=false (opt-in)?

- A) Opt-in is faster — a missing record is a single PK lookup
- B) Opt-in reduces database storage — most users never explicitly grant consent
- C) Opt-in ensures personalization only occurs with explicit affirmative consent — safer default under GDPR and CCPA
- D) Opt-in simplifies revocation — requires only a soft delete

**User answered:** C · **Correct:** C · ✓

> Under GDPR Article 7, consent must be freely given, specific, informed, and unambiguous. Under opt-in, a new user who has never hit the consent endpoint gets the trending fallback. This also aligns with fail-closed behavior: missing record and unreachable privacy service both resolve to denied.
> DDIA ref: Chapter 12 — The Future of Data Systems

---

**Q9 · [Scenario] · Async ORM session lifecycle (expire_on_commit)**
Without `expire_on_commit=False`, what happens when the consent endpoint accesses `record.updated_at` after `await session.commit()`?

- A) Nothing — SQLAlchemy caches column values for the object's lifetime
- B) SQLAlchemy marks attributes expired after commit and attempts lazy load; in async context this raises `MissingGreenlet`
- C) Attribute returns None — defaults to server_default after commit
- D) SQLAlchemy re-issues a SELECT on the same connection, refreshing transparently

**User answered:** B · **Correct:** B · ✓

> SQLAlchemy expires all attributes after commit by default (for synchronous lazy-load re-fetch). In async, the lazy load is a synchronous I/O call that greenlet cannot execute outside an async context — raises `MissingGreenlet` with no obvious pointer to the root cause. `expire_on_commit=False` keeps in-memory values as-is post-commit.

---

**Q10 · [Concept] · Write-ahead log and durability**
When `await session.commit()` returns, PostgreSQL guarantees durability. What mechanism provides this?

- A) PostgreSQL flushes data pages of both tables to disk synchronously before acknowledging
- B) PostgreSQL writes the change to WAL and flushes WAL to disk before acknowledging; data pages may still be in the buffer pool
- C) PostgreSQL replicates to a standby before acknowledging
- D) PostgreSQL holds the transaction in memory and flushes via background checkpoint; durability is probabilistic

**User answered:** B · **Correct:** B · ✓

> WAL is written and fsync'd before the commit is acknowledged. Data pages (heap files) can remain dirty in the buffer pool — they catch up at checkpoint time. If the server crashes immediately after commit, WAL replay on restart makes the transaction fully visible. WAL writes are sequential (fast); random data page writes are deferred.
> DDIA ref: Chapter 3 — Storage and Retrieval, Chapter 7 — Transactions

---

**Q11 · [Trade-off] · Hot/cold data tiering**
ADR 0006 notes expired audit partitions should be archived to cold storage rather than dropped in production. What compliance requirement drives this?

- A) GDPR Article 17 (right to erasure) requires deleted data to be recoverable for 90 days
- B) CCPA requires 12-month audit trail for consumer data requests; GDPR requires proof of consent for as long as data is processed — cold storage preserves history without hot Postgres cost
- C) Cold storage is required for disaster recovery — allows consent table reconstruction
- D) Regulatory bodies require audit logs in immutable format (Parquet is write-once)

**User answered:** B · **Correct:** B · ✓

> CCPA: 12-month audit trail for consumer data requests. GDPR Article 7(1): proof of consent for as long as data is processed on that basis. Cold tier (Parquet on S3, queryable via Athena) retains full history at a fraction of Postgres storage cost. Hot tier for sub-millisecond consent checks; cold tier for infrequent compliance queries.
> DDIA ref: Chapter 3 — Storage and Retrieval (Parquet), Chapter 10 — Batch Processing

---

**Q12 · [Scenario] · Isolation levels and concurrent writes**
A grant transaction is in-flight (not yet committed). Simultaneously, the inference-api checks consent for the same user. PostgreSQL default is Read Committed. What does the consent check see?

- A) consent_granted=true — Read Committed allows dirty reads
- B) consent_granted=false (or no row) — Read Committed only reads committed data; the grant hasn't committed yet
- C) Blocks and waits until the grant commits, then reads the new state
- D) Result is undefined under Read Committed

**User answered:** C · **Correct:** B · ✗

> Read Committed does not allow dirty reads (that is Read Uncommitted). It also does not block reads waiting for concurrent writes — the read proceeds immediately and sees the last committed state. If the grant hasn't committed, the check sees consent_granted=false. This is the correct behavior: the check should never see an uncommitted, potentially-rolled-back grant.
> DDIA ref: Chapter 7 — Transactions (read committed, dirty reads vs non-repeatable reads)

---
