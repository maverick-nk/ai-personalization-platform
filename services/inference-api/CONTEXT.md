---
service: inference-api
path: /services/inference-api/
status: active
depends_on: [redis*, mlflow*, privacy]
depended_on_by: [tests]
last_updated: 2026-04-11
---

# Service: inference-api

## Purpose
Serves real-time personalized recommendations. Checks consent via privacy service, fetches user features from Redis, scores candidate content using the latest model from MLflow, and returns a ranked Top-N list — all within a <50ms latency budget.

---

## Current State

- Version: not yet implemented
- API contract: gRPC (Go)
- Key behaviors: consent check → feature fetch → model score → rank → Top-N response; hot-swaps models by polling MLflow registry

---

## Architecture Notes

---

## Recent Changes

---

## Flags

---

## Interfaces

### Exposes
- `GET /recommend/{user_id}?top_n=10` — returns ranked content list with scores

### Consumes
- Redis: `user:{id}:features` key pattern (<5ms lookup)
- MLflow: polls for latest model version; hot-swaps without downtime
- privacy service: consent check middleware on every request

---

## Do Not
- Do not cache consent state — always call the privacy service fresh on every request; a cache reintroduces stale-consent risk (see ADR 0007)
- Do not treat privacy service errors or timeouts as granted — fail closed: return the trending fallback, not a 5xx (see ADR 0007)
- Do not leave the privacy service HTTP call without an explicit timeout — an unbounded wait cascades into a latency breach on every request
- Do not bypass the consent check before feature fetch — even for performance reasons; compliance requires the gate runs first
