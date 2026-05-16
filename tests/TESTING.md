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

This starts **all 8 services** via docker-compose: Kafka, Redis, Postgres, MLflow, Privacy, Event Ingestion, Inference API, and the Feature Pipeline (Flink). The script polls until every service reports healthy, then creates the required Kafka topics.

> **Critical:** The `<your-secret>` value is the shared HMAC key that makes pseudonymized IDs consistent across all services. It must be the **exact same string** both when you start the containers and when you run the tests — a mismatch causes the inference-api and the test runner to compute different pseudonyms for the same user, producing `consent_denied` instead of `cold_start` and breaking event-propagation assertions.

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
| `FEATURE_PIPELINE_ENABLED` | No | — | Set to `true` to run feature-freshness and event-propagation tests (feature-pipeline runs in docker-compose via `start-infra.sh`) |
| `MLFLOW_URL` | No | `http://localhost:5001` | MLflow tracking server URL (used by the hot-swap test to register new versions) |
| `INFERENCE_MLFLOW_MODEL_NAME` | No | `personalization-click-model` | MLflow registered model name (must match `INFERENCE_MLFLOW_MODEL_NAME` in docker-compose) |

---

## 3. Install Test Dependencies

```bash
cd tests
uv sync
```

---

## 4. Run Commands

```bash
# All e2e tests (feature-pipeline gates skipped unless FEATURE_PIPELINE_ENABLED=true)
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -v

# All tests including feature pipeline scenarios
PSEUDONYMIZE_SECRET=<secret> FEATURE_PIPELINE_ENABLED=true uv run pytest . -v

# By scenario category
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m consent -v            # consent revocation + audit
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m cold_start -v         # cold-start fallback
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m latency -v            # p95 SLO assertions
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m feature_freshness -v  # Redis freshness
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m model_hotswap -v      # model hot-swap

# Fast feedback — skip anything with long wait loops
PSEUDONYMIZE_SECRET=<secret> uv run pytest . -m "not slow" -v

# Single scenario file
PSEUDONYMIZE_SECRET=<secret> uv run pytest scenarios/test_consent.py -v
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

## 6. Running the Model Hot-swap Test

The `model_hotswap` test requires a model registered in MLflow before it can run (it skips with a clear message if none is found). The model-training pipeline is not in docker-compose — run it manually once:

```bash
cd services/model-training

# Generate synthetic Parquet training data (if real Flink data isn't available)
uv run python scripts/seed_parquet.py

# Train and register a model to MLflow
MODEL_TRAINING_PARQUET_BASE_PATH=/tmp/parquet_sample \
MODEL_TRAINING_MLFLOW_TRACKING_URI=http://localhost:5001 \
uv run python -m app
```

The pipeline registers the model under the `staging` alias by default. The inference-api will load it within 30s (its poll interval). Confirm with:

```bash
curl http://localhost:8002/health
# {"status":"ok","model_version":"1"}
```

Then run the hot-swap test:

```bash
PSEUDONYMIZE_SECRET=<secret> uv run pytest scenarios/test_model_hotswap.py -v
```

---

## 8. Test Isolation

Tests generate UUID-based user IDs (`e2e-<12 hex chars>`). No cleanup is needed after a test run:

- **Redis**: Orphaned keys expire after their TTL (1 hour by default). The HMAC digest is unguessable from outside the test, so old keys do not pollute subsequent runs.
- **Privacy / Postgres**: Consent and audit records for test users persist across runs but are keyed by the pseudonymized ID, which is unique per test invocation.

---

## 9. Scenario Coverage

| Scenario | Marker | Services Required | Notes |
|---|---|---|---|
| Cold start | `cold_start` | inference-api, privacy | No feature data in Redis → trending fallback |
| Consent revocation | `consent` | inference-api, privacy | Verifies audit log entry + fallback response |
| Watch event propagation | `e2e`, `slow` | event-ingestion, feature-pipeline, Redis | Requires `FEATURE_PIPELINE_ENABLED=true`; waits ≤5s for Redis update |
| Feature freshness | `feature_freshness`, `slow` | event-ingestion, feature-pipeline, Redis | Requires `FEATURE_PIPELINE_ENABLED=true`; checks `computed_at_epoch` age |
| Latency SLO | `latency` | inference-api, privacy | p95 end-to-end <50ms for consent-denied and cold-start paths |
| Model hot-swap | `model_hotswap`, `slow` | inference-api, MLflow | Requires a registered model in MLflow (run model-training pipeline first); registers a new version and waits ≤60s for the background poller to swap |
