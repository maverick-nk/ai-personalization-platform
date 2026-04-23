# System Design Concepts — feature-pipeline

> Quiz log for the `feature-pipeline` service.
> Reference: "Designing Data-Intensive Applications" — Martin Kleppmann
> Concepts scored ≥ 80% are deprioritised in future sessions.

---

## Concept Coverage

| Concept | Times Tested | Best Score | Last Tested |
|---|---|---|---|
| Kafka offset management | 1 | 100% | 2026-04-23 |
| At-least-once vs exactly-once delivery | 1 | 100% | 2026-04-23 |
| Parquet duplicates on recovery | 1 | 100% | 2026-04-23 |
| Stream processing windows & watermarks | 1 | 100% | 2026-04-23 |
| Columnar storage & partition pruning | 1 | 100% | 2026-04-23 |
| RowTypeInfo schema evolution | 1 | 100% | 2026-04-23 |
| Concurrent writes — lock drain pattern | 1 | 100% | 2026-04-23 |
| Cache TTL & expiry | 1 | 100% | 2026-04-23 |
| Consumer group rebalancing | 1 | 100% | 2026-04-23 |
| Feature drift — session_genre_counts | 1 | 100% | 2026-04-23 |
| Flink checkpoint recovery | 1 | 100% | 2026-04-23 |
| Training/serving skew | 1 | 100% | 2026-04-23 |

---

## Sessions

### 2026-04-23 · Full feature-pipeline service — PyFlink streaming pipeline

**Score: 12/12 (100%)**
**Concepts tested:** Kafka offset management, At-least-once vs exactly-once delivery, Parquet duplicates on recovery, Stream processing windows & watermarks, Columnar storage & partition pruning, RowTypeInfo schema evolution, Concurrent writes — lock drain pattern, Cache TTL & expiry, Consumer group rebalancing, Feature drift — session_genre_counts, Flink checkpoint recovery, Training/serving skew

---

**Q1 · [Concept] · Kafka offset management**
The pipeline starts with KafkaOffsetsInitializer.latest(). What does this mean for event consumption on first startup?

- A) The pipeline reads all historical events from the beginning of the topic
- B) The pipeline only consumes events published after it started — pre-existing events are skipped
- C) The pipeline reads from the earliest unread offset recorded in the consumer group
- D) "Latest" is a throughput hint, not an offset position

**User answered:** B · **Correct:** B · ✓

> Starting from `latest` means Flink tells Kafka "give me only new messages from this point forward." Any events already in the topic before the pipeline started are ignored. This is why the pipeline pairs `latest` with checkpointing — once a checkpoint commits, the offset is saved and recovery replays from there, not from `latest` again. The trade-off is that events published during the gap between first start and first checkpoint are at risk if the pipeline crashes before the checkpoint fires.
> DDIA ref: Chapter 11 — Stream Processing (log-based message brokers, consumer offsets)

---

**Q2 · [Trade-off] · At-least-once vs exactly-once delivery**
The pipeline uses enable_checkpointing(60_000) with latest starting offsets. Why does this combination produce at-least-once (not exactly-once) delivery?

- A) Flink only supports exactly-once with Kafka Streams, not PyFlink
- B) On recovery, Flink restores state from the last checkpoint and replays Kafka messages from the offset committed at that snapshot — events between the checkpoint and the crash are processed a second time
- C) Checkpointing snapshots state but does not track Kafka offsets, so events are always processed at most once
- D) latest offsets cause Flink to skip events on restart, reducing delivery to at-most-once

**User answered:** B · **Correct:** B · ✓

> Flink's checkpointing atomically snapshots both operator state and the committed Kafka offset. On recovery, it rewinds to the last good checkpoint and replays all messages from that saved offset — meaning any event that arrived after the checkpoint but before the crash gets processed again. This is at-least-once: no events are lost, but duplicates are possible. True exactly-once would require a two-phase commit between Flink's state backend and every sink (Redis + Parquet) — feasible with Kafka sinks using transactions, but Redis and Parquet have no transaction protocol to participate in.
> DDIA ref: Chapter 11 — Stream Processing (fault tolerance, exactly-once semantics, idempotent writes)

---

**Q3 · [Scenario] · Parquet duplicates on recovery**
After a pipeline crash and restart, checkpoint recovery replays 50 watch events that were already written to Parquet before the crash. What is the impact on the offline training store?

- A) No impact — Parquet writes are idempotent by design
- B) Duplicate rows appear for those 50 events; model training must deduplicate on (pseudo_user_id, event_time_epoch) before using the data
- C) Flink automatically deduplicates before writing to Parquet on recovery
- D) Parquet files written before the crash are deleted and rewritten from the checkpoint

**User answered:** B · **Correct:** B · ✓

> Parquet is an append-only columnar format — there is no upsert or deduplication built in. When replay writes the same 50 events again, they land as new rows in the partition file. The training pipeline reading that partition will see each of those events twice, which skews feature distributions and inflates effective training set size. The fix is always to deduplicate on (pseudo_user_id, event_time_epoch) as the natural composite key before feeding data to the model. This is a direct consequence of accepting at-least-once delivery — all downstream consumers of the offline store must be written to tolerate it.
> DDIA ref: Chapter 11 — Stream Processing (idempotency, at-least-once processing, end-to-end correctness)

---

**Q4 · [Trade-off] · Stream processing windows & watermarks**
The pipeline evicts stale records manually (event_time_epoch >= now - 600) rather than using Flink's native event-time windowing with watermarks. What is the key limitation of manual eviction?

- A) Manual eviction is slower — native windows use hash partitioning for O(1) eviction
- B) Manual eviction uses the event's own timestamp but "now" is processing time — Flink's watermark-based windows correctly handle late-arriving events by waiting for the watermark to advance before closing a window
- C) Flink's native windows don't support per-user keying, which is why manual eviction was needed
- D) There is no meaningful difference — manual eviction and native windowing produce identical results

**User answered:** B · **Correct:** B · ✓

> In this pipeline, "now" in the eviction check is time.time() — wall-clock processing time, not the event's logical time. If a watch event arrives 30 seconds late (e.g. due to mobile buffering), a native event-time window with a watermark would correctly place it within the 10-minute window it belongs to. Manual eviction may evict it immediately because processing time has moved on. For this project the difference is acceptable — the 10-minute window is approximate and late arrival is rare on a local setup — but in production with mobile clients and network delays, late data handling becomes a correctness requirement, not an optimisation.
> DDIA ref: Chapter 11 — Stream Processing (event time vs processing time, watermarks, late data)

---

**Q5 · [Trade-off] · Columnar storage & partition pruning**
Parquet files are date-partitioned (year=YYYY/month=MM/day=DD/). Why is date partitioning specifically valuable for model training workloads?

- A) Date partitions reduce file count by batching all events into one daily file
- B) Training jobs that read only the last 30 days can skip all other partitions entirely at the metadata level — no data from older partitions is read or scanned, reducing I/O proportionally
- C) Parquet requires date partitioning to maintain sorted order within files
- D) Date partitioning keeps Redis and Parquet in sync by sharing the same key prefix

**User answered:** B · **Correct:** B · ✓

> This is predicate pushdown combined with partition pruning. When a training job filters on event_date >= '2026-03-24', the query engine reads the directory tree and skips every partition whose path doesn't satisfy the predicate — no file is opened, no bytes are read from disk. Without partitioning, a full table scan would read every Parquet file regardless of date. Columnar storage adds a second layer: within a file, only the columns requested are read, not full rows. The combination makes large-scale feature retrieval dramatically cheaper than row-oriented formats like CSV or JSONL.
> DDIA ref: Chapter 3 — Storage and Retrieval (column-oriented storage, predicate pushdown); Chapter 10 — Batch Processing (data locality, efficient reads)

---

**Q6 · [Concept] · RowTypeInfo schema evolution**
The pipeline uses Types.ROW_NAMED(...) for Flink state instead of PICKLED_BYTE_ARRAY. What does "additive forward compatibility" mean in this context?

- A) You can add, rename, or remove fields freely — RowTypeInfo handles all schema changes
- B) You can add new optional fields with defaults without discarding existing checkpoints; structural changes (rename, remove, type change) still require a checkpoint discard and cold restart
- C) RowTypeInfo gives full bidirectional schema evolution equivalent to Avro with a schema registry
- D) Forward compatibility means new code can read old data only if the total field count stays the same

**User answered:** B · **Correct:** B · ✓

> RowTypeInfo serializes fields positionally by name — adding a new field at the end with a default value is safe because old checkpoints simply don't have that field and Flink fills in the default on deserialization. But renaming a field changes its identity in the descriptor, removing a field shifts positional alignment, and changing a type breaks the deserializer — all three require discarding the checkpoint and cold-starting from `latest`. This is weaker than Avro, which encodes a writer schema alongside the data and can resolve differences against a reader schema at runtime. The trade-off accepted here: RowTypeInfo is zero-infrastructure and sufficient for additive evolution, which covers most real-world changes.
> DDIA ref: Chapter 4 — Encoding and Evolution (forward and backward compatibility, schema evolution, Avro vs positional encoding)

---

**Q7 · [Scenario] · Concurrent writes — lock drain pattern**
ParquetSink._flush() copies the buffer under a lock, then releases the lock before writing to disk. Why is releasing the lock before the disk write critical?

- A) Python's GIL prevents holding a lock during I/O — the code would deadlock
- B) Holding the lock during the disk write blocks buffer() from accepting new events for the entire write duration — a slow write stalls the pipeline and risks dropping events under backpressure
- C) PyArrow is not thread-safe and raises an exception if called from a locked context
- D) The lock only protects the list reference, not its contents — releasing before write is a Python convention with no correctness impact

**User answered:** B · **Correct:** B · ✓

> Parquet writes involve PyArrow schema validation, memory allocation, snappy compression, and a filesystem syscall — easily 10–100ms on a busy machine. Holding the lock throughout would mean every call to buffer() blocks for that entire duration, serializing the pipeline's main processing thread behind disk I/O. The drain pattern solves this: acquire the lock only long enough to swap out the buffer (microseconds), then do the slow work outside the lock so the pipeline can keep accepting events.
> DDIA ref: Chapter 8 — Distributed Systems Trouble (process pauses, I/O latency); general concurrency: minimize critical section duration

---

**Q8 · [Trade-off] · Cache TTL & expiry**
Features are written to Redis with TTL=3600s. What happens to inference for a user who stops watching content for over an hour?

- A) Their Redis key expires; the inference API finds no key and must fall back to a default or cold-start response
- B) Redis extends the TTL automatically on each read, so features never expire for any user who has received a recommendation
- C) The TTL resets to 3600s on every inference read, so the record persists indefinitely for active users
- D) Expired keys are tombstoned — future writes for that user fail until the tombstone is manually cleared

**User answered:** A · **Correct:** A · ✓

> TTL expiry is the mechanism that prevents Redis from growing unboundedly. When the key expires, the inference API gets a cache miss and must handle it gracefully: return a generic trending feed (cold-start fallback) rather than crashing or returning empty results. The 3600s value is a deliberate trade-off — long enough that active users rarely hit a miss mid-session, short enough to reclaim memory for inactive users.
> DDIA ref: Chapter 5 — Replication (read-your-writes, cache consistency); general caching: TTL as a bounded staleness contract

---

**Q9 · [Concept] · Consumer group rebalancing**
A second instance of feature-pipeline starts while the first is running, both using consumer group "feature-pipeline". The topic has 3 partitions. What happens?

- A) Both instances consume all 3 partitions independently, doubling throughput
- B) Kafka triggers a rebalance — the 3 partitions are redistributed between the 2 instances; the instance receiving a new partition starts from its last committed offset, but per-user Flink state for keys on that partition starts fresh
- C) The second instance fails to join — only one consumer per group is allowed
- D) Kafka load-balances at the message level, so both instances receive every other message

**User answered:** B · **Correct:** B · ✓

> Kafka's consumer group protocol assigns each partition to exactly one consumer instance at a time. When the second instance joins, the group coordinator triggers a rebalance and redistributes the 3 partitions. Kafka offset continuity is preserved — the new instance picks up from the last committed offset. However, per-user Flink state lives in the task manager of the instance that originally owned that partition. After a rebalance, the new owner starts with empty state for those users — their feature windows reset. Production systems address this with remote state backends (RocksDB + S3) and savepoint-based partition migration.
> DDIA ref: Chapter 11 — Stream Processing (consumer groups, partition assignment, stateful rebalancing)

---

**Q10 · [Scenario] · Feature drift — session_genre_counts**
Before the fix, session_genre_counts accumulated lifetime totals and was never cleared when records were evicted from the 10-min window. What was the observable consequence for session_genre_vector?

- A) No consequence — normalization produces the same ratios regardless of time horizon
- B) session_genre_vector reflected the user's all-time genre distribution rather than their current 10-min session — a user who switched genre would show stale weights for hours or longer
- C) The state would grow unboundedly and eventually cause an OOM in the task manager
- D) The bug only affected category_affinity_score, not session_genre_vector

**User answered:** B · **Correct:** B · ✓

> This is a classic feature drift bug. The normalization looks mathematically valid, but it's computed over the wrong time horizon. A user who watched action films for months, then switched to documentary for the last 10 minutes, would still show ~95% action in their genre vector because the lifetime counts dominate. The fix — rebuilding session_genre_counts from scratch after each eviction pass — ensures the vector only reflects the surviving 10-minute window.
> DDIA ref: Chapter 11 — Stream Processing (stateful computation, windowing correctness); general ML: feature definitions must match their names

---

**Q11 · [Scenario] · Flink checkpoint recovery**
Checkpointing is configured at 60s intervals. The pipeline crashes at t=59s after the last successful checkpoint. What is the recovery behaviour?

- A) Flink replays from the beginning of the Kafka topic to reconstruct all state
- B) Flink restores operator state from the t=0 checkpoint and replays Kafka messages from the offset committed in that snapshot — events from the last 59s are reprocessed
- C) Flink cannot recover and the operator restarts from latest, discarding the 59s of events
- D) Flink recovers from in-memory state snapshots — no replay occurs and no events are lost

**User answered:** B · **Correct:** B · ✓

> The checkpoint contains two things: a snapshot of all operator state and the Kafka offsets current when that snapshot was taken. On recovery, Flink atomically restores both — state rolls back to t=0, and the Kafka source seeks back to those saved offsets. The 59 seconds of events are then replayed from Kafka's log. This is why the log-based nature of Kafka is essential to Flink's fault tolerance model — without a replayable log, at-least-once recovery would be impossible.
> DDIA ref: Chapter 11 — Stream Processing (fault tolerance via checkpointing, log-based message brokers as a recovery mechanism)

---

**Q12 · [Trade-off] · Training/serving skew**
The Redis hash and Parquet schema use identical field names and value types. Why is this schema consistency critical for model correctness?

- A) Identical schemas allow the inference API to read from Parquet when Redis is down
- B) If the training pipeline reads different feature representations than what the inference API serves at prediction time, the model learns patterns that don't match its inference inputs — predictions degrade silently
- C) Kafka requires producer and consumer to share a schema; Redis and Parquet follow the same constraint
- D) Identical schemas reduce storage by allowing Redis to write Parquet files directly

**User answered:** B · **Correct:** B · ✓

> Training/serving skew produces no exceptions, no obvious errors — just quietly wrong predictions. The model trains on one distribution of feature values and is served a different one at inference time. Keeping a single schema contract enforced at both write paths is the structural fix. This is exactly what a feature store is designed to guarantee, and why schema contracts are registered alongside model versions in MLflow.
> DDIA ref: Chapter 4 — Encoding and Evolution (schema evolution, forward/backward compatibility); general ML: training-serving consistency

---
