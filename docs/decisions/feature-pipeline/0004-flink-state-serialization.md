# 0004. RowTypeInfo for Flink Per-User State Serialization

**Date:** 2026-04-22
**Status:** Accepted
**Service:** feature-pipeline
**Decided by:** Niranjan

---

## Context

`FeatureProcessFunction` maintains per-user `UserFeatureState` — a Python dataclass holding a `list[WatchRecord]` and a `dict[str, float]`. Flink must serialize this state to persist it across checkpoints and recover from restarts. PyFlink requires an explicit type descriptor when registering a `ValueStateDescriptor`, and the state shape is a nested Python object with no trivial equivalent in Flink's Java-native type system.

The lowest-friction path (`Types.PICKLED_BYTE_ARRAY()`) was evaluated and rejected: pickle state is opaque to the JVM layer, making it incompatible with Flink's web UI, State Processor API, and savepoint migration tooling. With phase 2 productionisation planned, migrating away from pickle in production would require discarding all checkpoints and cold-starting every active user. Switching to typed state now, while there are no real users, has no migration cost.

---

## Decision

Use explicit `Types.ROW_NAMED(...)` type descriptors for both `WatchRecord` and `UserFeatureState`. The dataclasses remain the working representation for feature computation; `to_row()` / `from_row()` methods on each class handle conversion at the Flink state boundary only. PyFlink is imported lazily inside those methods so `state.py` remains importable without a JVM, keeping unit tests runnable without PyFlink installed.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| `PICKLED_BYTE_ARRAY` | Zero boilerplate but opaque to Flink's web UI, State Processor API, and savepoint tooling. Production migration to any typed format later requires discarding checkpoints and cold-starting all active users — a product-level incident. |
| Avro with schema registry | True bidirectional schema evolution and cross-language state reads. Right answer when a schema registry is already in the stack or multi-language consumers exist. Deferred: introduces `apache-avro`, `.avsc` files, and registry infrastructure not warranted at current scale. |
| `msgpack` / `protobuf` with custom `TypeSerializer` | Schema-evolution safe but requires a Java-side `TypeSerializer` subclass — significant boilerplate with no practical advantage over `RowTypeInfo` for a single-language, single-worker pipeline. |

---

## Consequences

**Gets easier:**
- Flink web UI can display state size metrics and checkpoint details per key
- State Processor API can read and transform state from savepoints for debugging or offline migrations
- Savepoint-based rolling upgrades work for additive changes — a new optional field with a default does not require a checkpoint discard
- `state.py` stays importable without PyFlink installed, so unit tests remain fast with no JVM dependency

**Gets harder / trade-offs accepted:**
- Breaking changes (field rename, type change, removal) still require a checkpoint discard and a cold restart from `latest` — `RowTypeInfo` gives additive forward compatibility, not arbitrary schema evolution
- `to_row()` / `from_row()` in `state.py` must be kept in sync with `_WATCH_RECORD_TYPE` / `_USER_FEATURE_STATE_TYPE` in `pipeline.py`; adding a field to the dataclass without updating both silently drops or misaligns that field

**Constraints this introduces:**
- Field order in `to_row()` must match the positional order declared in `Types.ROW_NAMED(...)` — the type descriptor and conversion methods are a paired contract
- Any code reading `self._state.value()` must go through `UserFeatureState.from_row()` — never treat the raw value as a `UserFeatureState` directly

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Schema evolution and forward/backward compatibility | Ch 4 — Encoding and Evolution | RowTypeInfo gives additive forward compatibility; Avro/protobuf would give full bidirectional evolution — the right upgrade path when a schema registry is introduced |
| Fault tolerance via checkpointing in stream processing | Ch 11 — Stream Processing | Typed state is a prerequisite for Flink's savepoint-based rolling upgrades and State Processor API; opaque pickle bytes break both |

---

## Related

- ADR 0003: [Fire-and-Forget Kafka Delivery](../event-ingestion/0003-fire-and-forget-kafka-delivery.md) — at-most-once ingestion means events lost before Kafka cannot be recovered after a checkpoint discard
- ADR 0005: [At-Least-Once Delivery via Checkpointing](0005-at-least-once-checkpointing-kafka-offsets.md) — checkpointing still applies; typed state makes those checkpoints inspectable and migrateable
- CONTEXT.md constraint added: yes
