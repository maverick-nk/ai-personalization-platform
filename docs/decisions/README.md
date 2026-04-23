# Architecture Decision Records

> Permanent record of non-trivial design decisions made during this project.
> Each ADR captures: decision, alternatives considered, trade-offs, and relevant DDIA concepts.
> Created by `/adr`. Retrospectives also live here per service.

| # | Title | Service | Date | Status |
|---|---|---|---|---|
| 0001 | [KRaft Single-Broker Kafka for Local Development](shared/0001-kraft-single-broker-local-kafka.md) | shared | 2026-04-12 | Accepted |
| 0002 | [Shared Postgres Instance for MLflow Tracking Backend](shared/0002-shared-postgres-mlflow-tracking.md) | shared | 2026-04-12 | Accepted |
| 0003 | [Fire-and-Forget Kafka Delivery for Event Ingestion](event-ingestion/0003-fire-and-forget-kafka-delivery.md) | event-ingestion | 2026-04-18 | Accepted |
| 0004 | [RowTypeInfo for Flink Per-User State Serialization](feature-pipeline/0004-flink-state-serialization.md) | feature-pipeline | 2026-04-22 | Accepted |
| 0005 | [At-Least-Once Delivery via Flink Checkpointing + Kafka Latest Offsets](feature-pipeline/0005-at-least-once-checkpointing-kafka-offsets.md) | feature-pipeline | 2026-04-22 | Accepted |
| 0005 | [At-Least-Once Delivery via Flink Checkpointing + Kafka Latest Offsets](feature-pipeline/0005-at-least-once-checkpointing-kafka-offsets.md) | feature-pipeline | 2026-04-22 | Accepted |
