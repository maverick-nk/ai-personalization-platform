---
service: feature-pipeline
path: /services/feature-pipeline/
status: active
depends_on: [kafka*, redis*, parquet*]
depended_on_by: [inference-api, model-training]
last_updated: 2026-04-19
---

# Service: feature-pipeline

## Purpose
Consumes Kafka `user.watch.events` topic and computes 6 windowed features per user using PyFlink. Writes features to Redis (online store, <2s freshness) and Parquet (offline store, date-partitioned). Ensures training/serving consistency via identical feature schemas in both stores.

---

## Current State

- Version: 0.1.0 — implemented (Step 2 complete)
- Stack: PyFlink 1.20.3 (local embedded mode, no separate Flink cluster)
- Entry point: `uv run feature-pipeline` (requires Java 11/17/21 and `JAVA_HOME` set)
- Unit tests: `uv run pytest tests/test_features.py` — 25 passing (no infra needed)
- Integration tests: `tests/test_integration.py` — requires Kafka + Redis + Java

---

## Architecture Notes

PyFlink runs in local embedded mode (`env.set_parallelism(1)`) — no JobManager/TaskManager in docker-compose. The bundled Kafka connector JAR (`flink-sql-connector-kafka-*.jar`) is auto-discovered from the `apache-flink` wheel's `opt/` directory.

Feature computation uses a single `KeyedProcessFunction` per `pseudo_user_id` with `ValueState[UserFeatureState]` (pickled). On each event:
1. Append `WatchRecord` to `state.recent_watches`
2. Update `session_genre_counts[genre] += watch_pct`
3. Evict records older than `window_size_seconds` (600s)
4. Recompute all 6 features
5. Write to Redis (synchronous, pipeline `hset + expire`)
6. Buffer for Parquet (flush on batch_size=500 or interval=60s)

PyFlink is an optional extra in pyproject.toml (`pipeline` extra) because it requires a JVM. Unit tests (test_features.py) run without it.

---

## Recent Changes

- 2026-04-19: Initial implementation (Step 2)
  - Added `genre: str | None` to WatchEvent in event-ingestion (backward-compatible)
  - Created feature-pipeline service with all 6 features, Redis sink, Parquet sink

---

## Flags

---

## Interfaces

### Exposes
- Redis writes: `user:{pseudo_id}:features` hash (online store, TTL=3600s by default)
  - Fields: `watch_count_10min`, `category_affinity_score`, `avg_watch_duration`,
    `time_of_day_bucket`, `recency_score`, `session_genre_vector`,
    `pseudo_user_id`, `last_event_epoch`, `computed_at_epoch`
- Parquet writes: `data/parquet/year=YYYY/month=MM/day=DD/batch_*.parquet`
  - Schema identical to Redis hash fields plus `event_date` partition column
  - Compression: snappy

### Consumes
- Kafka topic: `user.watch.events` (consumer group: `feature-pipeline`)
  - Message schema: `{pseudo_user_id, content_id, watch_pct, timestamp, genre}`

---

## Do Not

- Change Redis key pattern or field names without updating inference-api and model-training — schema contract crosses both services
- Add or rename features without checking inference-api (feature fetch) and model-training (Parquet reader) dependencies
- Drop the Parquet `event_date` partition column — model-training reads by date partition
- Rename, retype, or remove fields on `UserFeatureState` or `WatchRecord` without discarding Flink checkpoints first — RowTypeInfo allows additive changes only; structural changes break deserialization (see ADR 0006)
- Add a field to `UserFeatureState` or `WatchRecord` without updating both `to_row()` / `from_row()` in `state.py` AND the corresponding `Types.ROW_NAMED(...)` descriptor in `pipeline.py` — they are a paired contract; a mismatch silently drops or misaligns fields
- Add a new sink to the pipeline that is not idempotent — at-least-once delivery means events may be replayed on restart; all sinks must tolerate duplicate writes (see ADR 0005)
- Read Parquet training data without deduplicating on `(pseudo_user_id, event_time_epoch)` — replayed events from checkpoint recovery can produce duplicate rows (see ADR 0005)
