# 0001. KRaft Single-Broker Kafka for Local Development

**Date:** 2026-04-12  
**Status:** Accepted  
**Service:** shared (infra)  
**Decided by:** user

---

## Context

The implementation plan specified "Kafka + Zookeeper" for the local docker-compose stack. In production (Phase 2), Kafka will run as a multi-broker cluster on Kubernetes for fault tolerance. For local development, the goal is simply to have Kafka available so services can produce and consume messages — replication and broker failover are not needed.

---

## Decision

Use Apache Kafka 3.7 in KRaft mode (no Zookeeper) as a single-broker instance in docker-compose. This is local dev only — Phase 2 will replace this with a production-grade deployment.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Kafka + Zookeeper (as in original plan) | Two containers for the same outcome; Zookeeper is deprecated in Kafka 3.x and adds startup ordering complexity |
| Confluent Platform (cp-kafka image) | Heavier image, requires license for some features; unnecessary for local dev |
| Multi-broker KRaft (3 nodes) | Mirrors production topology but adds overhead with no dev benefit — all test scenarios require only message delivery, not broker failover |

---

## Consequences

**Gets easier:**
- Single container to manage; no Zookeeper dependency ordering in docker-compose
- Faster cold start and lower memory footprint locally
- Kafka 3.x KRaft is the forward-compatible path — aligns with where production will go anyway

**Gets harder / trade-offs accepted:**
- Local topology diverges from a multi-broker production cluster
- Broker failover behaviour cannot be tested locally (not a Phase 1 requirement)

**Constraints this introduces:**
- `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR` and `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR` must stay at `1` — increasing these requires additional brokers
- Do not add Zookeeper back without a documented reason; KRaft is the path forward

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Log-based message brokers | Ch 11 — Stream Processing | Kafka is a durable, append-only log; single broker preserves this guarantee locally with replication factor 1 |
| Consensus without external coordinator | Ch 9 — Consistency and Consensus | KRaft embeds Raft consensus inside Kafka itself, eliminating the need for Zookeeper as a separate coordination service |
| Replication and fault tolerance | Ch 5 — Replication | Replication factor 1 means no fault tolerance — an explicit and acceptable trade-off for a local dev environment |

---

## Related

- Supersedes: none
- Related: Phase 2 infra will replace this with a multi-broker Kubernetes deployment
- CONTEXT.md flag added: no (infra only — no service-level constraint introduced)
