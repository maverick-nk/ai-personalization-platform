# System Design Concepts — shared (infra)

> Quiz log for shared infrastructure decisions.
> Reference: "Designing Data-Intensive Applications" — Martin Kleppmann
> Concepts scored ≥ 80% are deprioritised in future sessions.

---

## Concept Coverage

| Concept | Times Tested | Best Score | Last Tested |
|---|---|---|---|
| Distributed Coordination / KRaft | 1 | 100% | 2026-04-12 |
| Raft Consensus (quorum, majority) | 1 | 100% | 2026-04-12 |
| Redis Persistence Modes (RDB vs AOF) | 1 | 100% | 2026-04-12 |
| Derived Data and Recomputability | 1 | 100% | 2026-04-12 |
| Write-Ahead Log and Crash Recovery | 1 | 100% | 2026-04-12 |
| Health Checks and Failure Detection | 1 | 100% | 2026-04-12 |
| MVCC and Concurrency Control | 1 | 100% | 2026-04-12 |
| Shared Infrastructure / Noisy Neighbour | 1 | 100% | 2026-04-12 |
| Columnar Storage and Parquet | 1 | 100% | 2026-04-12 |
| Log-Based Message Brokers | 1 | 100% | 2026-04-12 |
| At-Least-Once Delivery and Idempotency | 1 | 100% | 2026-04-12 |
| Liveness vs Readiness Probes | 1 | 100% | 2026-04-12 |

---

## Sessions

### 2026-04-12 · Infrastructure bootstrap — KRaft Kafka, Redis, Postgres, MLflow via docker-compose

**Score: 12/12 (100%)**
**Concepts tested:** Distributed Coordination/KRaft, Raft Consensus, Redis Persistence Modes, Derived Data, WAL/Crash Recovery, Health Checks, MVCC, Shared Infrastructure, Columnar Storage, Log-Based Brokers, At-Least-Once Delivery, Liveness vs Readiness Probes

---

**Q1 · [Concept] · Distributed Coordination / KRaft**
KRaft mode removes Zookeeper from Kafka. What role was Zookeeper playing in the classic Kafka setup?

- A) It stored Kafka message data as a backup in case the broker's log was corrupted
- B) It acted as the distributed coordinator for broker registration, leader election, and topic metadata management
- C) It provided the persistent disk storage layer for Kafka's commit log segments
- D) It handled consumer group rebalancing and offset tracking on behalf of consumers

**User answered:** B · **Correct:** B · ✓

> Zookeeper was Kafka's external coordination service — brokers registered themselves in ZK, controllers used it to run leader elections, and topic/partition metadata was stored there. KRaft moves all of this into Kafka itself using Raft, eliminating Zookeeper entirely.
> DDIA ref: Chapter 9 — Consistency and Consensus

---

**Q2 · [Concept] · Raft Consensus (quorum, majority)**
In a single-broker KRaft setup, what is the minimum number of acknowledgements needed to commit a message?

- A) 1 — the broker acknowledges its own write, satisfying the majority requirement for a cluster of size 1
- B) 2 — the broker plus the KRaft controller must both acknowledge
- C) 0 — KRaft skips acknowledgements in single-node mode for performance
- D) 3 — Raft requires a minimum quorum of 3 nodes regardless of cluster size

**User answered:** A · **Correct:** A · ✓

> Majority of a 1-node cluster is 1. The single broker is simultaneously leader and only voter, committing immediately on its own write. Replication factor 1 is the Kafka-level expression of the same trade-off.
> DDIA ref: Chapter 9 — Consistency and Consensus

---

**Q3 · [Concept] · Redis Persistence Modes**
We started Redis with `--save "" --appendonly no`. What does this mean for data durability?

- A) Redis persists data every second using AOF
- B) Redis operates as a pure in-memory store — all data is lost when the container stops
- C) Redis takes RDB snapshots every 60 seconds
- D) Redis replicates writes to a replica before acknowledging

**User answered:** B · **Correct:** B · ✓

> Both persistence mechanisms are disabled. Redis holds everything in RAM only — acceptable because features are derived data, always reconstructible by replaying Kafka events.
> DDIA ref: Chapter 5 — Replication (durability trade-offs); Chapter 12 — derived data

---

**Q4 · [Trade-off] · Derived Data and Recomputability**
What property of the system architecture makes Redis having no persistence acceptable?

- A) The inference API caches all Redis data locally
- B) Feature data is derived from the Kafka event log — reconstructible by replaying events from any offset
- C) Redis persistence is re-enabled in production (Phase 2)
- D) MLflow stores a copy of all feature vectors alongside each model version

**User answered:** B · **Correct:** B · ✓

> Redis is a materialised view, not a system of record. Kafka is the source of truth. As long as Kafka retains events, features can be fully recomputed.
> DDIA ref: Chapter 11 — Stream Processing; Chapter 12 — Kappa architecture

---

**Q5 · [Concept] · Write-Ahead Log and Crash Recovery**
What guarantee does the WAL provide in the event of a Postgres crash?

- A) WAL ensures queries execute faster by caching recent writes
- B) WAL allows Postgres to reconstruct committed transactions after a crash by replaying logged changes
- C) WAL prevents concurrent write conflicts by serialising transactions
- D) WAL is only relevant for replication, not single-node crash recovery

**User answered:** B · **Correct:** B · ✓

> Every change is written to the WAL before it's applied to data files. On crash, Postgres replays from the last checkpoint. The postgres_data volume ensures both WAL and data files survive container restarts.
> DDIA ref: Chapter 7 — Transactions (WAL, crash recovery)

---

**Q6 · [Scenario] · Health Checks and Failure Detection**
MLflow's health check is `curl -f http://localhost:5000/health`. What failure mode does this NOT protect against?

- A) MLflow container crashing immediately after starting
- B) MLflow process starting but HTTP server not yet listening
- C) MLflow accepting requests but returning incorrect model registry data
- D) Postgres not being ready when MLflow first connects

**User answered:** C · **Correct:** C · ✓

> Health checks verify liveness, not correctness. curl /health tells you the HTTP server is up, not that the DB connection is valid or results are accurate. This is the liveness vs readiness distinction.
> DDIA ref: Chapter 8 — The Trouble with Distributed Systems

---

**Q7 · [Concept] · MVCC and Concurrency Control**
How does MVCC affect concurrent reads and writes to the consent table?

- A) Readers block writers
- B) Writers block readers
- C) Readers see a consistent snapshot without blocking writers; writers proceed without blocking readers
- D) MVCC serialises all operations

**User answered:** C · **Correct:** C · ✓

> Postgres keeps multiple row versions. Readers get a snapshot at transaction start; writers create new versions. Neither blocks the other. Dead versions are cleaned up by autovacuum.
> DDIA ref: Chapter 7 — Transactions (snapshot isolation, MVCC)

---

**Q8 · [Trade-off] · Shared Infrastructure / Noisy Neighbour**
What is the primary risk of MLflow and privacy sharing one Postgres instance at production scale?

- A) Postgres cannot support multiple logical databases on one instance
- B) A resource-intensive MLflow operation could contend for Postgres I/O, adding latency to consent checks
- C) An MLflow rollback would roll back concurrent consent changes
- D) Postgres MVCC cannot handle concurrent readers from two applications

**User answered:** B · **Correct:** B · ✓

> Two logical databases share the same I/O, memory, and WAL writer. An MLflow training run logging many metrics could saturate the WAL writer, spiking consent check latency. Acceptable at local dev scale; addressed in Phase 2.
> DDIA ref: Chapter 1 — Reliable, Scalable, Maintainable Systems

---

**Q9 · [Concept] · Columnar Storage and Parquet**
What property of Parquet makes it well-suited for reading training data into LightGBM?

- A) Parquet supports in-place updates
- B) Parquet stores data in row-major order for fast per-user retrieval
- C) Parquet's columnar layout lets the pipeline read only the needed feature columns without loading irrelevant ones
- D) Parquet compresses each row independently

**User answered:** C · **Correct:** C · ✓

> Columnar layout enables column pruning and predicate pushdown — only the requested columns are read from disk. The trade-off is immutability: no in-place updates, only new files or partitions.
> DDIA ref: Chapter 3 — Storage and Retrieval (column-oriented storage, predicate pushdown)

---

**Q10 · [Trade-off] · Log-Based Message Brokers**
How does Kafka's log retention differ from traditional queues, and why does it matter for the feature pipeline?

- A) No difference — both retain messages indefinitely
- B) Kafka's retained log allows the feature pipeline to replay events from any past offset — essential for recomputing features after a bug fix or Redis wipe
- C) Traditional queues retain messages; Kafka deletes on acknowledgement
- D) Log retention is irrelevant since features are always computed from live events

**User answered:** B · **Correct:** B · ✓

> Traditional queues delete on acknowledgement. Kafka's non-destructive log enables replaying events to recompute derived data. Kafka retention policy becomes a critical operational parameter.
> DDIA ref: Chapter 11 — Stream Processing (log-based brokers, replaying events)

---

**Q11 · [Scenario] · At-Least-Once Delivery and Idempotency**
The feature pipeline re-processes 50 already-written watch events due to a network blip. What happens to `watch_count_10min` with a naive Redis INCR?

- A) No impact — INCR is idempotent
- B) watch_count_10min is overcounted — 50 duplicate events each increment the counter again
- C) The pipeline auto-deduplicates via Kafka message keys
- D) Redis TTL expires the duplicate writes before the inference API reads them

**User answered:** B · **Correct:** B · ✓

> At-least-once means duplicates are possible on retry. A naive INCR is not idempotent — each duplicate inflates the count. Fix requires deduplication by event ID, or recomputing the window from scratch rather than incrementing.
> DDIA ref: Chapter 11 — Stream Processing (at-least-once vs exactly-once, idempotent consumers)

---

**Q12 · [Trade-off] · Liveness vs Readiness Probes**
Which statement correctly describes the liveness/readiness distinction and why it matters for the inference API?

- A) Liveness = should pod be restarted; readiness = should pod receive traffic. A pod that started but hasn't loaded its model yet should fail readiness but pass liveness
- B) Liveness = should pod receive traffic; readiness = should pod be restarted
- C) Both probes do the same thing — distinction only relevant for stateful services
- D) Readiness runs once at startup; liveness runs continuously

**User answered:** A · **Correct:** A · ✓

> A pod initialising its model load should fail readiness (removed from load balancer) but pass liveness (not restarted). Using only liveness would send requests to an unready pod; restarting on slow model load creates a restart loop.
> DDIA ref: Chapter 8 — The Trouble with Distributed Systems

---
