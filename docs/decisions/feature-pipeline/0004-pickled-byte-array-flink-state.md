# 0004. Pickle (`PICKLED_BYTE_ARRAY`) for Flink Per-User State

**Date:** 2026-04-22
**Status:** Superseded by [ADR 0006](0006-row-type-info-flink-state.md)
**Service:** feature-pipeline
**Decided by:** Niranjan

---

## Context

`FeatureProcessFunction` maintains per-user `UserFeatureState` — a dataclass holding a `list[WatchRecord]` and a `dict[str, float]`. Flink must serialize this state to persist it across checkpoints and recover from restarts. PyFlink requires an explicit type descriptor when registering a `ValueStateDescriptor`. The state shape is a nested Python object with no direct equivalent in Flink's Java-native `RowTypeInfo` system.

---

## Decision

Use `Types.PICKLED_BYTE_ARRAY()` as the state type descriptor. Flink treats the state as an opaque byte array and delegates serialization entirely to Python's `pickle`. No custom serializer, schema registry, or type annotations on the state class are required.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| `RowTypeInfo` with nested type descriptors | PyFlink's `RowTypeInfo` doesn't support arbitrary nested Python types (`list[dataclass]`). Would require flattening the state or a custom Java-side TypeSerializer. Significant boilerplate for no production benefit at current scale. |
| `msgpack` or `protobuf` with custom `TypeSerializer` | Schema-evolution safe and cross-language readable, but requires implementing a Java `TypeSerializer` subclass or a Python codec shim. Overhead not justified for a local-embedded single-worker pipeline. |
| Avro with schema registry | Production-grade evolution support, but introduces Confluent Schema Registry as an infrastructure dependency — heavier than warranted for this stage. |

---

## Consequences

**Gets easier:**
- `UserFeatureState` is a plain dataclass — no serialization annotations, no schema registration, no boilerplate
- Additive schema changes (new optional field with a default value) work without migration — old pickled state deserializes, new field gets its default on first access

**Gets harder / trade-offs accepted:**
- **Breaking state schema changes require discarding checkpoints.** Renaming a field, changing a field's type, or removing a field will cause deserialization errors on restart from checkpoint. The job must restart from `latest` Kafka offset, losing in-flight per-user state for all active users.
- Flink's web UI, savepoint migration tooling, and state backend metrics cannot inspect or transform pickled state — it is opaque to the JVM layer.
- Pickle ties the state to a specific Python version and library snapshot. Upgrading the Python runtime or changing a type used in `WatchRecord` / `UserFeatureState` carries deserialization risk.
- No cross-language readability — a Java or Go debug tool cannot inspect state from a checkpoint.

**Constraints this introduces:**
- Any change to `UserFeatureState` or `WatchRecord` (field rename, type change, removal) must be coordinated with a checkpoint discard — it cannot be deployed as a rolling update.
- Python and direct dependency versions should be pinned and changed deliberately, not as a side-effect of routine upgrades.

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Schema evolution and forward/backward compatibility | Ch 4 — Encoding and Evolution | Pickle provides neither forward nor backward compatibility guarantees across schema changes; additive-only changes are safe, structural changes are not |
| Fault tolerance via checkpointing in stream processing | Ch 11 — Stream Processing (exactly-once semantics) | Flink checkpoints snapshot state + Kafka offsets atomically; the serialization format chosen here determines whether that snapshot survives a code change |

---

## Related

- ADR 0003: [Fire-and-Forget Kafka Delivery](../event-ingestion/0003-fire-and-forget-kafka-delivery.md) — upstream delivery guarantee (at-most-once from ingestion) means replaying missed events after a checkpoint discard is not possible
- CONTEXT.md constraint added: yes
