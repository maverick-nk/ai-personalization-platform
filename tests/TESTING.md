# E2E Test Harness — Operator Guide

End-to-end tests for the personalization platform. All tests run against **real service instances** — no mocking. Tests are automatically skipped when services are not running.

---

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) installed (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker Desktop running
- Repository checked out with all service source available

---

## 1. Start Infrastructure

From the repository root:

```bash
export PSEUDONYMIZE_SECRET=<your-secret>
./scripts/start-infra.sh
```

This starts **all 7 services** via docker-compose: Kafka, Redis, Postgres, MLflow, Privacy, Event Ingestion, and Inference API. The script polls until every service reports healthy, then creates the required Kafka topics.

> The `<your-secret>` value is the shared HMAC key that makes pseudonymized IDs consistent across all services. It must be the **same string** when you set `PSEUDONYMIZE_SECRET` for the tests.

To stop all services:

```bash
docker compose down
```

---

## 2. Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PSEUDONYMIZE_SECRET` | **Yes** | — | Shared HMAC secret; tests skip if absent |
| `EVENT_INGESTION_URL` | No | `http://localhost:8000` | event-ingestion base URL |
| `INFERENCE_URL` | No | `http://localhost:8002` | inference-api base URL |
| `PRIVACY_URL` | No | `http://localhost:8001` | privacy service base URL |
| `REDIS_HOST` | No | `localhost` | Redis hostname |
| `REDIS_PORT` | No | `6379` | Redis port |
| `FEATURE_PIPELINE_ENABLED` | No | — | Set to `true` to run feature-freshness and event-propagation tests (requires the Flink pipeline to be running separately) |

---

## 3. Install Test Dependencies

```bash
cd tests
uv sync
```

---

## 4. Run Commands

```bash
# All e2e tests
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -v

# By scenario category
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m consent -v         # consent revocation + audit
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m cold_start -v      # cold-start fallback
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m latency -v         # p95 SLO assertions
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m feature_freshness -v  # Redis freshness

# Fast feedback — skip anything with long wait loops
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m "not slow" -v

# Single scenario file
PSEUDONYMIZE_SECRET=<secret> uv run pytest scenarios/test_consent_revocation.py -v
```

---

## 5. Interpreting Results

**`SKIPPED`** — `PSEUDONYMIZE_SECRET` is not set, or a per-scenario skip condition was not met (e.g. the feature-pipeline is not running). Check that all services from Step 1 are healthy (`docker compose ps`).

**Latency assertion failure** — The failure message shows the actual p95 and the SLO:
```
AssertionError: p95 latency for end-to-end recommendation: 68.3ms exceeds 50ms SLO
```
This means at least 5% of requests took longer than the target. Check service logs for slow paths (Redis timeout, privacy service latency, model inference time).

**`fallback_reason` values in recommendations:**
| Value | Meaning |
|---|---|
| `consent_denied` | User has revoked consent, or privacy service was unreachable |
| `cold_start` | No feature vector found in Redis for this user |
| `model_unavailable` | inference-api has not yet loaded a model from MLflow |

---

## 6. Test Isolation

Tests generate UUID-based user IDs (`e2e-<12 hex chars>`). No cleanup is needed after a test run:

- **Redis**: Orphaned keys expire after their TTL (1 hour by default). The HMAC digest is unguessable from outside the test, so old keys do not pollute subsequent runs.
- **Privacy / Postgres**: Consent and audit records for test users persist across runs but are keyed by the pseudonymized ID, which is unique per test invocation.

---

## 7. Scenario Coverage

| Scenario | Marker | Services Required | Notes |
|---|---|---|---|
| Cold start | `cold_start` | inference-api, privacy | No feature data in Redis → trending fallback |
| Consent revocation | `consent` | inference-api, privacy | Verifies audit log entry + fallback response |
| Watch event propagation | `slow`, `e2e` | event-ingestion, feature-pipeline, inference-api | Waits ≤5s for Redis update |
| Feature freshness | `feature_freshness`, `slow` | event-ingestion, feature-pipeline, Redis | Checks `computed_at_epoch` age |
| Cold start → personalized shift | `cold_start`, `slow` | event-ingestion, feature-pipeline, inference-api | 3+ watches → personalized |
| Latency SLO | `latency` | inference-api | p95 end-to-end <50ms |
| Model hot-swap | `slow` | inference-api, MLflow | New alias → swap within poll interval |
