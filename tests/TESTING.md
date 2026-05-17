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

The `model_hotswap` test requires a model registered in MLflow before it can run (it skips with a clear message if none is found). The model-training pipeline is not in docker-compose — use the wrapper script:

```bash
./scripts/train-model.sh
```

The script checks MLflow reachability, seeds synthetic Parquet data if the store is empty, trains the model, registers it under the `staging` alias, and waits for the inference-api to confirm it loaded. Options:

```bash
# Use real Flink-written Parquet data instead of seeded data
./scripts/train-model.sh --parquet-path /path/to/parquet

# Register under 'production' alias instead of 'staging'
./scripts/train-model.sh --alias production
```

Then run the hot-swap test:

```bash
PSEUDONYMIZE_SECRET=<secret> uv run pytest scenarios/test_model_hotswap.py -v
```

---

## 7. Test Isolation

Tests generate UUID-based user IDs (`e2e-<12 hex chars>`). No cleanup is needed after a test run:

- **Redis**: Orphaned keys expire after their TTL (1 hour by default). The HMAC digest is unguessable from outside the test, so old keys do not pollute subsequent runs.
- **Privacy / Postgres**: Consent and audit records for test users persist across runs but are keyed by the pseudonymized ID, which is unique per test invocation.

---

## 8. User Simulation Tests (Locust)

The simulation framework (`tests/simulation/`) uses [Locust](https://locust.io) to drive realistic multi-user journeys (watch → recommend → consent) against the live stack. These tests are **not run in CI** — they require a running stack and are executed manually.

### Install simulation dependencies

```bash
cd tests
uv sync --extra simulation
```

### Suite files

| Suite | Type | Peak users | Duration | When to run |
|---|---|---|---|---|
| `baseline.yaml` | load | 10 | 5m | Local smoke test after any change |
| `prod_baseline.yaml` | load | 10 | 5m | Production SLO validation (deployed stack only) |
| `stress.yaml` | stress | 500 | 20m | Find the breaking point — step-ramp to 500 |
| `soak.yaml` | soak | 50 | 60m | Surface memory leaks or slow degradation |
| `spike.yaml` | spike | 500 | 10m | Validate recovery after a sudden traffic burst |

### Headless mode (batch / CI-equivalent)

Results are saved as JSON to `tests/simulation/results/<suite-name>/<timestamp>.json`. Exit code is `0` if all assertions pass, `1` if any threshold is breached.

```bash
# Local smoke test
PSEUDONYMIZE_SECRET=<secret> tests/.venv/bin/python -m tests.simulation.runner \
  --suite tests/simulation/suites/baseline.yaml

# Stress test
PSEUDONYMIZE_SECRET=<secret> tests/.venv/bin/python -m tests.simulation.runner \
  --suite tests/simulation/suites/stress.yaml
```

Override service URLs if not running on localhost defaults:

```bash
PSEUDONYMIZE_SECRET=<secret> \
EVENT_INGESTION_URL=http://my-host:8000 \
INFERENCE_URL=http://my-host:8002 \
PRIVACY_URL=http://my-host:8001 \
  tests/.venv/bin/python -m tests.simulation.runner \
  --suite tests/simulation/suites/prod_baseline.yaml
```

### Web UI mode (interactive)

Omit `--headless` and get real-time charts at **http://localhost:8089**. The suite config (user behavior, ramp profile) is still loaded from the YAML file. Results are **not** saved to JSON in this mode.

```bash
PSEUDONYMIZE_SECRET=<secret> tests/.venv/bin/python -m tests.simulation.runner \
  --suite tests/simulation/suites/baseline.yaml \
  --web
```

Then open **http://localhost:8089**. Key UI tabs:
- **Charts** — live requests/s, response time, failure rate graphs
- **Statistics** — per-endpoint p50/p95/p99 table updating every second
- **Failures** — error details and HTTP status codes
- **Download Data** — on-demand CSV export

You can adjust user count and spawn rate from the UI without restarting the runner.

### Interpreting results

```json
{
  "suite": "baseline",
  "test_type": "load",
  "total_requests": 241,
  "error_rate_pct": 0.0,
  "latency_ms": { "p50": 8.0, "p95": 40.0, "p99": 160.0 },
  "endpoints": {
    "watch":         { "p95_ms": 21.0, "count": 170, "errors": 0 },
    "recommend":     { "p95_ms": 64.0, "count": 61,  "errors": 0 },
    "consent_grant": { "p95_ms": 170.0, "count": 10, "errors": 0 }
  },
  "assertions": {
    "latency_p95_ms": { "threshold": 500.0, "actual": 170.0, "passed": true },
    "error_rate_pct": { "threshold": 5.0,   "actual": 0.0,   "passed": true }
  },
  "passed": true
}
```

**High p95 on `consent_grant`** — expected on a cold local stack; consent_grant is a database write to Postgres and fires only once per virtual user at startup. It does not represent steady-state traffic.

**High p95 on `recommend`** — the inference-api performs a Redis lookup, a privacy check, and model inference. If p95 is consistently above the suite threshold, check Redis latency (`redis-cli ping`), privacy-service logs, and whether a model is loaded in MLflow.

**Low request count** — controlled by `session_length_mean_s` in the suite YAML (mean sleep between actions). Lower it to generate higher throughput for throughput-focused tests.

### Thresholds

| Suite | `latency_p95_ms` | `error_rate_pct` | Notes |
|---|---|---|---|
| `baseline.yaml` | 500 | 5 | Relaxed for local dev — cold services, no JVM warmup |
| `prod_baseline.yaml` | 50 | 1 | Matches the production SLO from `CLAUDE.md` |
| `stress.yaml` | 200 | 5 | Expects degradation; focus is finding the break point |
| `soak.yaml` | 100 | 1 | Steady-state; alert on gradual latency increase |
| `spike.yaml` | 500 | 10 | Focus is recovery speed, not peak latency |

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
