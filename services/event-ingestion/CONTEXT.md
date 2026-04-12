---
service: event-ingestion
path: /services/event-ingestion/
status: active
depends_on: [kafka*]
depended_on_by: [tests]
last_updated: 2026-04-11
---

# Service: event-ingestion

## Purpose
Accepts raw user watch and session events via REST, validates schema, pseudonymizes user IDs, and publishes to Kafka. Acts as the entry point for all behavioral data flowing into the platform.

---

## Current State

- Version: not yet implemented
- API contract: REST
- Key behaviors: schema validation, user ID pseudonymization before publish

---

## Architecture Notes

---

## Recent Changes

---

## Flags

---

## Interfaces

### Exposes
- `POST /events/watch` — payload: user_id, content_id, watch_pct, timestamp
- `POST /events/session` — payload: user_id, session_id, device, start_time

### Consumes
- Kafka topics: `user.watch.events`, `user.session.events` (producer)

---

## Do Not
<!-- Constraints will be added as contracts are frozen during development -->
