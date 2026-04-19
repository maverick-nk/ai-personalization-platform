---
service: event-ingestion
path: /services/event-ingestion/
status: active
depends_on: [kafka*]
depended_on_by: [tests]
last_updated: 2026-04-18
---

# Service: event-ingestion

## Purpose
Accepts raw user watch and session events via REST, validates schema, pseudonymizes user IDs, and publishes to Kafka. Acts as the entry point for all behavioral data flowing into the platform.

---

## Current State

- Version: 0.1.0
- API contract: REST (FastAPI)
- Key behaviors: schema validation, user ID pseudonymization before publish
- Stack: Python 3.11, FastAPI, pydantic-settings, confluent-kafka
- Entry point: `uv run uvicorn app.main:app`

---

## Architecture Notes

- `app/config.py` — pydantic-settings reads `KAFKA_BOOTSTRAP_SERVERS` (default `localhost:29092`, EXTERNAL listener) and `PSEUDONYMIZE_SECRET` (required)
- `app/pseudonymize.py` — HMAC-SHA256; raw `user_id` is never stored, logged, or published to Kafka
- `app/producer.py` — fire-and-forget (`poll(0)`); delivery failures logged via callback, do not fail the HTTP request
- Kafka messages carry `pseudo_user_id` (hex digest), never `user_id`
- HTTP responses: 202 Accepted on success, 422 on schema violation

---

## Recent Changes

- 2026-04-18: Initial implementation — POST /events/watch, POST /events/session, GET /health, unit + integration tests

---

## Flags

⚑ `producer.py` — `produce()` is called without a message key. With a single partition this is fine, but scaling to multiple partitions will distribute events round-robin, breaking per-user ordering. Fix: pass `key=pseudo_user_id.encode()` so Kafka routes all events for the same user to the same partition.

---

## Interfaces

### Exposes
- `POST /events/watch` — payload: user_id, content_id, watch_pct, timestamp
- `POST /events/session` — payload: user_id, session_id, device, start_time

### Consumes
- Kafka topics: `user.watch.events`, `user.session.events` (producer)

---

## Do Not

- Do not wait for Kafka broker acknowledgement in the HTTP request path — delivery is fire-and-forget by design (see ADR 0003)
- Do not use this publish path for any event that requires guaranteed delivery (billing, audit) — add a separate ack-confirmed producer for those
