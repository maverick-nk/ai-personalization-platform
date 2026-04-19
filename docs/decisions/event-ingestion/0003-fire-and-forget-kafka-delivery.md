# 0003. Fire-and-Forget Kafka Delivery for Event Ingestion

**Date:** 2026-04-18
**Status:** Accepted
**Service:** event-ingestion
**Decided by:** user

---

## Context

The event ingestion API receives high-volume watch and session events. Waiting for Kafka broker acknowledgement on every request would add latency to each API call. Watch and session events are observational signals — a small number of lost events does not meaningfully degrade downstream recommendation quality, and the platform can tolerate eventual consistency between the event stream and the feature store.

---

## Decision

Publish events to Kafka using `poll(0)` (non-blocking) and return HTTP 202 immediately, without waiting for broker delivery confirmation. Delivery failures are logged via a callback but do not fail the HTTP request.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| At-least-once (wait for broker ack) | Adds latency to every API call; overkill for observational data where occasional loss is acceptable |
| Exactly-once (Kafka transactions) | Significant complexity and latency overhead; not justified when missing a watch event has near-zero impact on recommendations |

---

## Consequences

**Gets easier:**
- API latency stays low — no blocking on Kafka round-trip
- Producer code is simple; no transaction management or retry coordination

**Gets harder / trade-offs accepted:**
- Events can be silently lost if the broker is unavailable or the producer buffer fills; this is accepted
- No per-request delivery guarantee — callers cannot know if their event reached Kafka

**Constraints this introduces:**
- Downstream systems (Flink, feature pipeline) must treat the event stream as best-effort; they must not assume every event will arrive
- Any future use case that requires guaranteed delivery (e.g. billing, audit) must use a different publish path with explicit acks

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| At-most-once vs at-least-once vs exactly-once delivery | Ch 11 — Stream Processing | Fire-and-forget is at-most-once; the decision was made explicit rather than accidental |
| Backpressure and producer buffering | Ch 11 — Stream Processing | `poll(0)` services the delivery callback queue without blocking; buffer overflow is a silent loss vector |
| Loose coupling via message queue | Ch 11 — Stream Processing | 202 Accepted decouples the HTTP caller from Kafka availability; the API stays up even if Kafka is slow |

---

## Related

- Supersedes or related to: none
- CONTEXT.md constraint added: yes — downstream services must treat the stream as best-effort
