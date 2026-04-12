---
service: tests
path: /tests/
status: active
depends_on: [event-ingestion, inference-api, privacy]
depended_on_by: []
last_updated: 2026-04-11
---

# Service: tests

## Purpose
Test harness that drives all system validation. No UI exists — all user behavior is simulated via API calls. Covers end-to-end flows: event propagation, consent revocation, cold start, feature freshness, model hot-swap, and latency SLOs.

---

## Current State

- Version: not yet implemented
- API contract: pytest
- Key behaviors: scenario runner, configurable user behavior simulator (cold/active/churned), Precision@K relevance scoring, latency assertions

---

## Architecture Notes

---

## Recent Changes

---

## Flags

---

## Interfaces

### Exposes
- pytest test suite

### Consumes
- `POST /events/watch`, `POST /events/session` (event-ingestion)
- `GET /recommend/{user_id}` (inference-api)
- `PATCH /privacy/consent/{user_id}`, `GET /privacy/audit/{user_id}` (privacy)

---

## Do Not
- Do not mock inter-service calls in end-to-end scenarios — tests must run against real services
