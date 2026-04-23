# 0005. At-Least-Once Delivery via Flink Checkpointing + Kafka Latest Offsets

**Date:** 2026-04-22
**Status:** Accepted
**Service:** feature-pipeline
**Decided by:** Niranjan

---

## Context

The feature pipeline must survive restarts without permanently losing events that are already in Kafka. Without any offset management, `KafkaOffsetsInitializer.latest()` would skip everything published while the pipeline was down — restarting after a crash would leave user feature state stale until new events arrived. The pipeline also writes to two sinks (Redis and Parquet) that have different idempotency properties, which constrains how much the delivery guarantee can practically be strengthened.

---

## Decision

Use `env.enable_checkpointing(60_000)` combined with `KafkaOffsetsInitializer.latest()`. Flink snapshots per-user state and Kafka consumer offsets together every 60 seconds. On restart from a checkpoint, Flink resumes from the checkpointed Kafka offsets rather than `latest`, replaying any events processed after the last checkpoint. On a clean first start (no checkpoint), consumption begins at `latest`. This gives **at-least-once** delivery: events processed in the window between the last checkpoint and a crash will be replayed and processed again.

Exactly-once delivery was not pursued.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| No checkpointing (original state) | On any restart the pipeline reads from `latest`, skipping all events published during downtime. Per-user state is permanently stale for users who were active during the outage. |
| Exactly-once via Flink two-phase commit | Requires `TwoPhaseCommitSinkFunction` for both sinks. Redis has no transaction protocol — exactly-once Redis writes are not achievable without external coordination. Parquet files are append-only — rolling back a written file is not possible. Cost is prohibitive for no practical benefit given the idempotency of Redis writes. |
| `KafkaOffsetsInitializer.committed_offsets()` without checkpointing | Relies on Kafka consumer group commits rather than Flink checkpoints. Commits happen asynchronously and are not coordinated with state snapshots — offsets and state can drift, producing incorrect feature values after recovery. |

---

## Consequences

**Gets easier:**
- Events published during a planned restart or crash are not silently lost — they are replayed once the pipeline recovers from checkpoint
- Recovery is automatic: Flink reloads state and resumes the correct Kafka offset without operator intervention

**Gets harder / trade-offs accepted:**
- **Events in the checkpoint window (up to 60s) may be processed twice on restart.** For Redis, this is harmless — `hset` overwrites the same key with the same or newer values (idempotent). For Parquet, duplicate rows for the same `(pseudo_user_id, event_time_epoch)` can appear across files.
- **Parquet duplicates require deduplication in model training.** The model-training pipeline reading Parquet must deduplicate by `(pseudo_user_id, event_time_epoch)` before constructing training datasets, or accept a small bias from replayed events.
- A clean start with no checkpoint still reads from `latest` — events published before the first checkpoint of a brand-new deployment are not consumed. This is intentional: the pipeline is not designed for historical backfill.
- Checkpointing adds ~5–10% overhead to checkpoint-interval throughput due to state snapshotting. Negligible at current parallelism=1 scale.

**Constraints this introduces:**
- Both sinks must tolerate duplicate writes — any future sink added to the pipeline must either be idempotent or implement its own deduplication.
- Model-training must deduplicate Parquet reads on `(pseudo_user_id, event_time_epoch)` before use — this is a cross-service contract.

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| At-least-once vs exactly-once delivery | Ch 11 — Stream Processing (fault tolerance) | Checkpointing gives at-least-once; exactly-once is skipped because neither Redis nor append-only Parquet can participate in two-phase commit |
| Idempotent writes as a substitute for exactly-once | Ch 11 — Idempotence and exactly-once semantics | Redis `hset` idempotency means duplicates from replay are safe on the online store; Parquet requires explicit deduplication downstream |
| Epoch-based recovery (snapshot + replay) | Ch 11 — Checkpointing and Savepoints | Flink's checkpoint mechanism is a distributed snapshot — state and Kafka offsets are captured atomically so recovery always restores a consistent cut |

---

## Related

- ADR 0004: [Pickle for Flink State](0004-pickled-byte-array-flink-state.md) — pickle state must be checkpoint-compatible; structural state schema changes invalidate existing checkpoints and force a cold restart at `latest`, compounding the event-loss risk noted in ADR 0003
- ADR 0003: [Fire-and-Forget Kafka Delivery](../event-ingestion/0003-fire-and-forget-kafka-delivery.md) — events lost at the ingestion boundary (fire-and-forget producer) cannot be recovered by this pipeline's checkpoint mechanism; the two decisions compound: loss is possible before Kafka, duplication is possible after Kafka
- CONTEXT.md constraint added: yes
