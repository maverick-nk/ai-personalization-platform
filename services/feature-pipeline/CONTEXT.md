---
service: feature-pipeline
path: /services/feature-pipeline/
status: active
depends_on: [kafka*, redis*, parquet*]
depended_on_by: [inference-api, model-training]
last_updated: 2026-04-11
---

# Service: feature-pipeline

## Purpose
Consumes Kafka event topics and computes windowed features per user using Apache Flink. Writes features to Redis (online store, <2s freshness) and Parquet (offline store, for training). Ensures training/serving consistency via identical feature schemas in both stores.

---

## Current State

- Version: not yet implemented
- API contract: none (stream processor)
- Key behaviors: windowed aggregation, dual-sink to Redis + Parquet, schema consistency enforced

---

## Architecture Notes

---

## Recent Changes

---

## Flags

---

## Interfaces

### Exposes
- Redis writes: `user:{id}:features` (online store, TTL per feature)
- Parquet writes: date-partitioned offline store

### Consumes
- Kafka topics: `user.watch.events`, `user.session.events` (consumer)

---

## Do Not
<!-- Constraints will be added as contracts are frozen during development -->
