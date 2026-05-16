---
service: tests
path: /tests/
status: active
depends_on: [event-ingestion, inference-api, privacy, feature-pipeline]
depended_on_by: []
last_updated: 2026-05-16
---

# Service: tests

## Purpose
End-to-end test harness that drives all system validation. No UI exists — all user behavior is simulated via API calls against real running services. Covers: consent revocation, cold start, watch event propagation, feature freshness, and latency SLOs.

---

## Current State

- Version: v0.1.1 — Step 6 complete + model_hotswap scenario added (2026-05-16)
- Stack: Python + pytest (async via pytest-asyncio)
- Key behaviors:
  - UUID-based user isolation per test (`e2e-<hex>`) — no cleanup needed
  - Skip gate: all tests skip when `PSEUDONYMIZE_SECRET` is not set
  - Feature-pipeline tests gated by `FEATURE_PIPELINE_ENABLED=true`
  - Latency assertions use p95, not average

---

## Architecture Notes

### Directory Layout

```
tests/
  clients/          # Thin async httpx wrappers per service
    event_ingestion.py
    inference.py
    privacy.py
  helpers/
    latency.py      # assert_p95() helper
    pseudonymize.py # HMAC-SHA256 matching event-ingestion logic
    redis_helpers.py # poll_redis_key() with configurable timeout
  scenarios/        # One file per test scenario
    test_cold_start.py
    test_consent.py
    test_event_propagation.py
    test_feature_freshness.py
    test_latency.py
    test_model_hotswap.py
  conftest.py       # Fixtures: clients, redis, unique_user_id
  TESTING.md        # Operator guide (how to run, env vars, markers)
```

### pytest Markers

| Marker | Meaning |
|---|---|
| `consent` | Consent revocation + audit log |
| `cold_start` | Cold-start fallback behaviour |
| `latency` | p95 SLO assertions |
| `feature_freshness` | Redis key age < 5s (requires feature pipeline) |
| `e2e` | Full streaming path (requires feature pipeline) |
| `model_hotswap` | Model hot-swap under concurrent load (requires MLflow + trained model) |
| `slow` | Tests with wait loops (≤10s); skippable for fast feedback |

### Service URLs (env-configurable)

| Variable | Default |
|---|---|
| `EVENT_INGESTION_URL` | `http://localhost:8000` |
| `PRIVACY_URL` | `http://localhost:8001` |
| `INFERENCE_URL` | `http://localhost:8002` |
| `REDIS_HOST` | `localhost` |
| `REDIS_PORT` | `6379` |

---

## Recent Changes
- [2026-05-16] Added model_hotswap scenario test, mlflow dependency, TESTING.md updates for model hot-swap workflow

- [2026-05-14] Step 6 complete — all scenario files implemented; CONTEXT.md updated from stale scaffold

---

## Flags

---

## Interfaces

### Exposes
- pytest test suite with markers: `consent`, `cold_start`, `latency`, `feature_freshness`, `e2e`, `slow`

### Consumes
- `POST /events/watch`, `POST /events/session` (event-ingestion)
- `GET /recommend/{user_id}` (inference-api)
- `PATCH /privacy/consent/{user_id}`, `GET /privacy/audit/{user_id}` (privacy)
- Redis directly via `HGETALL user:{pseudo_id}:features` (feature freshness assertions)

---

## Do Not
- Do not mock inter-service calls in end-to-end scenarios — tests must run against real services
- Do not assert latency using average — always use p95 (`helpers/latency.assert_p95`)
- Do not add `PSEUDONYMIZE_SECRET` fallback defaults — absence must skip, not silently pass
