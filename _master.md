# Service Relationship Graph

> Dependency lines are derived from each service's CONTEXT.md frontmatter.
> Run `scripts/sync-master.sh` to regenerate. Only edit ## Notes and ## System Overview manually.

**Last synced:** 2026-05-16

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
tests             →  [event-ingestion, inference-api, privacy, feature-pipeline]
```

> `*` = external/third-party. No CONTEXT.md — document inside the service that uses it.

---

## Reverse Map

> Shows blast radius when a service changes.

```
event-ingestion   ←  [tests]
feature-pipeline  ←  [inference-api, model-training, tests]
inference-api     ←  [tests]
privacy           ←  [inference-api, tests]
model-training    ←  []
tests             ←  []
```

---

## Data Flow Map

> Indirect dependencies through shared resources. `A → [resource] → B` means A's output is consumed by B via that resource. Changing A's output schema requires coordinating with B.

```
event-ingestion  → [kafka: user.watch.events, user.session.events] → feature-pipeline
feature-pipeline → [redis: user:{id}:features]                     → inference-api
feature-pipeline → [parquet: date-partitioned]                     → model-training
model-training   → [mlflow: model artifact + feature schema]       → inference-api
```

**Full transitive chain:**
`event-ingestion → kafka → feature-pipeline → redis → inference-api`
`event-ingestion → kafka → feature-pipeline → parquet → model-training → mlflow → inference-api`

> Any schema change at event-ingestion (Kafka payload fields) can cascade all the way to inference-api through this chain.

---

## Shared Resources

| Resource | Type | Producer | Consumer |
|---|---|---|---|
| Kafka | Message bus | event-ingestion | feature-pipeline |
| Redis | Online feature store | feature-pipeline | inference-api |
| Parquet | Offline feature store | feature-pipeline | model-training |
| MLflow | Model registry | model-training | inference-api |
| Postgres | Consent store | privacy | privacy (self) |

---

## Flags

| Flagged By | Issue | Date | Resolved |
|---|---|---|---|

---

## Notes

- All service contracts (gRPC schemas, Kafka topic names, Redis key patterns, feature schemas) will be locked as development progresses — add to each service's `## Do Not` section when frozen.
- Test harness drives all validation — no UI layer exists.
- Pseudonymized user IDs flow through all services; no PII in Kafka, Redis, or logs.
