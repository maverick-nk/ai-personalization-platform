---
service: privacy
path: /services/privacy/
status: active
depends_on: [postgres*]
depended_on_by: [inference-api, tests]
last_updated: 2026-04-11
---

# Service: privacy

## Purpose
Enforces consent-aware access control for personalization. Maintains a consent table in Postgres, exposes endpoints to grant/revoke consent and retrieve audit logs. Acts as middleware interceptor in the inference-api — blocks feature access immediately on revocation.

---

## Current State

- Version: not yet implemented
- API contract: REST middleware
- Key behaviors: consent check on every inference request; immediate revocation; audit logging; fallback to non-personalized feed

---

## Architecture Notes

---

## Recent Changes

---

## Flags

---

## Interfaces

### Exposes
- `PATCH /privacy/consent/{user_id}` — grant or revoke personalization consent
- `GET /privacy/audit/{user_id}` — retrieve audit log entries for a user

### Consumes
- Postgres: consent table (read/write)

---

## Do Not
<!-- Constraints will be added as contracts are frozen during development -->
