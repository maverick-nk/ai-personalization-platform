# Service Relationship Graph

> Dependency lines are derived from each service's CONTEXT.md frontmatter.
> Run `scripts/sync-master.sh` to regenerate. Only edit ## Notes and ## System Overview manually.

**Last synced:** 2026-04-11

---

## System Overview

Privacy-preserving real-time streaming personalization platform — simulates Netflix/YouTube-style content personalization with real-time feature updates (<2s), low-latency inference (<50ms), and consent-aware privacy controls.

---

## Service Index

| Service | Path | Status | CONTEXT.md |
|---|---|---|---|
| event-ingestion | /services/event-ingestion/ | active | ✓ |
| feature-pipeline | /services/feature-pipeline/ | active | ✓ |
| inference-api | /services/inference-api/ | active | ✓ |
| privacy | /services/privacy/ | active | ✓ |
| model-training | /services/model-training/ | active | ✓ |
| tests | /tests/ | active | ✓ |

> Status values: `active` · `deprecated` · `experimental` · `external`

---

## Dependency Map

> `service` → depends on → `[list]`

```
event-ingestion   →  [kafka*]
feature-pipeline  →  [kafka*, redis*, parquet*]
inference-api     →  [redis*, mlflow*, privacy]
privacy           →  [postgres*]
model-training    →  [parquet*, mlflow*]
tests             →  [event-ingestion, inference-api, privacy]
```

> `*` = external/third-party. No CONTEXT.md — document inside the service that uses it.

---

## Reverse Map

> Shows blast radius when a service changes.

```
event-ingestion   ←  [tests]
feature-pipeline  ←  [inference-api, model-training]
inference-api     ←  [tests]
privacy           ←  [inference-api, tests]
model-training    ←  []
tests             ←  []
```

---

## Shared Resources

| Resource | Type | Used By |
|---|---|---|
| Kafka | Message bus | event-ingestion (producer), feature-pipeline (consumer) |
| Redis | Online feature store | feature-pipeline (writer), inference-api (reader) |
| Parquet | Offline feature store | feature-pipeline (writer), model-training (reader) |
| MLflow | Model registry | model-training (writer), inference-api (reader) |
| Postgres | Consent store | privacy |

---

## Flags

| Flagged By | Issue | Date | Resolved |
|---|---|---|---|

---

## Notes

- All service contracts (gRPC schemas, Kafka topic names, Redis key patterns, feature schemas) will be locked as development progresses — add to each service's `## Do Not` section when frozen.
- Test harness drives all validation — no UI layer exists.
- Pseudonymized user IDs flow through all services; no PII in Kafka, Redis, or logs.
