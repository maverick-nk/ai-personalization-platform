# 0006. RowTypeInfo for Flink Per-User State

**Date:** 2026-04-22
**Status:** Accepted
**Service:** feature-pipeline
**Decided by:** Niranjan

---

## Context

ADR 0004 chose `PICKLED_BYTE_ARRAY` for Flink state as the lowest-friction option during initial implementation. With phase 2 productionisation planned (Flink cluster, web UI, State Processor API for debugging), pickle becomes a migration liability: switching serialization formats in production requires discarding all checkpoints, causing a cold-start for every active user. Switching now, while there are no real users, costs nothing.

---

## Decision

Replace `Types.PICKLED_BYTE_ARRAY()` with explicit `Types.ROW_NAMED(...)` type descriptors for both `WatchRecord` and `UserFeatureState`. The dataclasses remain the working representation for feature computation; `to_row()` / `from_row()` methods on each class handle conversion at the Flink state boundary. PyFlink is imported lazily inside those methods so `state.py` remains importable without a JVM, keeping unit tests runnable without PyFlink installed.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Keep `PICKLED_BYTE_ARRAY` | Opaque to Flink's web UI, State Processor API, and savepoint migration tooling. Production migration requires a cold-start checkpoint discard with real user data. |
| Avro with schema registry | True forward/backward schema evolution and cross-language reads. Rejected for now: introduces `apache-avro`, schema `.avsc` files, and ideally a registry service. Right answer when multi-language state reads or a schema registry is already in place. |
| `msgpack` / `protobuf` with custom `TypeSerializer` | Schema-evolution safe but requires a Java-side `TypeSerializer` subclass — significant boilerplate with no advantage over `RowTypeInfo` at current scale. |

---

## Consequences

**Gets easier:**
- Flink web UI can display state size metrics per key (previously opaque bytes)
- State Processor API can read and transform state from savepoints for debugging or migrations
- Savepoint-based rolling upgrades are possible — additive field changes (new optional field with default) are handled by Flink without a checkpoint discard
- `state.py` stays importable without PyFlink installed, keeping unit tests fast

**Gets harder / trade-offs accepted:**
- Breaking state changes (rename, type change, removal) still require a checkpoint discard — RowTypeInfo gives additive evolution, not arbitrary schema changes
- `to_row()` / `from_row()` conversion methods must be kept in sync with `_WATCH_RECORD_TYPE` and `_USER_FEATURE_STATE_TYPE` in `pipeline.py`; a field added to the dataclass without updating both will silently drop or misalign that field

**Constraints this introduces:**
- Field order in `to_row()` must match the positional order in `Types.ROW_NAMED(...)` — the type descriptor and conversion methods are a paired contract
- Renaming or removing a field still requires a checkpoint discard; additive changes (new field appended at the end with a default) do not
- Any future sink or consumer of state must use `from_row()` — do not read `self._state.value()` directly as a `UserFeatureState`

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Schema evolution and forward compatibility | Ch 4 — Encoding and Evolution | RowTypeInfo gives additive forward compatibility (new optional fields); Avro/protobuf would give full bidirectional evolution |
| Fault tolerance via checkpointing | Ch 11 — Stream Processing | Typed state is a prerequisite for Flink's savepoint-based rolling upgrades and the State Processor API; opaque bytes break both |

---

## Related

- Supersedes: [ADR 0004](0004-pickled-byte-array-flink-state.md) — original pickle decision
- ADR 0005: [At-Least-Once Delivery](0005-at-least-once-checkpointing-kafka-offsets.md) — checkpointing still applies; this change makes checkpoint state inspectable
- CONTEXT.md constraint updated: yes
