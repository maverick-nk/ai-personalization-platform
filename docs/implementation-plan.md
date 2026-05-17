# Implementation Plan

> Status: Phase 1 complete. Phase 2 in progress.
> Last updated: 2026-05-16

---

## Phases Overview

| Phase | Scope | Status |
|---|---|---|
| Phase 1 | Core system — all services, end-to-end data flow verified by test harness | ✅ Complete (Steps 0–6) |
| Phase 2 | Production engineering — CI/CD, user simulation framework | 🔄 In progress |
| Phase 3 | Cloud deployment (GCP) + Observability | Deferred |

---

## Phase 1: Core System

Services are ordered by data flow dependency — each unblocks the next.

```
Infra Bootstrap
     │
     ▼
Event Ingestion API
     │ (produces to Kafka)
     ▼
Streaming Feature Pipeline ──► Redis (online store)
                            └──► Parquet (offline store)
                                      │
                                      ▼
                               Model Training Pipeline
                                      │
                                      ▼
                               Model Registry (MLflow)
                                      │
                               ┌──────┘
                               ▼
Privacy Service ──────────► Inference API
                                      │
                                      ▼
                               Test Harness
                                      │
                                      ▼
                               Observability Stack
```

---

### Step 0 — Infrastructure Bootstrap

**Branch:** `infra/docker-compose-baseline`

| Task | Detail |
|---|---|
| `docker-compose.yml` | Kafka + Zookeeper, Redis, Postgres, MLflow |
| Health checks | All services have `/healthz` or equivalent |
| Shared network | Single Docker network for inter-service DNS |
| Volume mounts | Persistent Postgres, Redis, MLflow artifact store |
| Scripts | `scripts/start-infra.sh`, `scripts/reset-infra.sh` |

**Done when:** `docker-compose up` brings all infra healthy; services can connect to Kafka, Redis, Postgres, and MLflow.

---

### Step 1 — Event Ingestion API

**Branch:** `feat/event-ingestion`

**Stack:** Python + FastAPI

| Task | Detail |
|---|---|
| `POST /events/watch` | Payload: `user_id`, `content_id`, `watch_pct`, `timestamp` |
| `POST /events/session` | Payload: `user_id`, `session_id`, `device`, `start_time` |
| Schema validation | Pydantic models; reject malformed events before Kafka publish |
| Pseudonymization | HMAC-SHA256 of `user_id` with a secret; original never stored |
| Kafka producer | confluent-kafka; publish to `user.watch.events` / `user.session.events` |
| Unit tests | Schema validation, pseudonymization correctness |
| Integration test | Real Kafka — confirm messages land in topic |

**Done when:** POST events reach Kafka topics with pseudonymized IDs; malformed events are rejected 4xx.

---

### Step 2 — Streaming Feature Pipeline

**Branch:** `feat/feature-pipeline`

**Stack:** Python + PyFlink (fallback: Python + Kafka consumer with sliding window logic)

| Task | Detail |
|---|---|
| Kafka consumer | Consume `user.watch.events` and `user.session.events` |
| Feature computation | See feature table below |
| Redis sink | Write `user:{pseudo_id}:features` hash within ~2s of event |
| Parquet sink | Batch sink, date-partitioned, schema-identical to Redis |
| Feature TTL | Configurable per feature via env/config |

**Features computed:**

| Feature | Logic |
|---|---|
| `watch_count_10min` | Rolling count of watch events in last 10 minutes |
| `category_affinity_score` | Weighted score per content genre (decay on older events) |
| `avg_watch_duration` | Mean `watch_pct` across recent events |
| `time_of_day_bucket` | `morning` / `afternoon` / `evening` / `night` from timestamp |
| `recency_score` | Decay-weighted engagement score |
| `session_genre_vector` | Genre distribution in current session (normalized) |

**Done when:** Watch event → Redis key updated within 2s; Parquet files written with correct schema.

---

### Step 3 — Privacy Service

**Branch:** `feat/privacy-service`

**Stack:** Python + FastAPI + SQLAlchemy + Postgres + Alembic

| Task | Detail |
|---|---|
| `PATCH /privacy/consent/{user_id}` | Grant or revoke personalization consent |
| `GET /privacy/audit/{user_id}` | Retrieve full audit log for a user |
| Consent table | `user_pseudo_id`, `consent_granted` (bool), `updated_at` |
| Audit log table | `user_pseudo_id`, `action`, `timestamp`, `reason` |
| Migrations | Alembic for both tables |
| Internal endpoint | HTTP or gRPC consent check callable by Inference API |

**Revocation flow:**
1. `PATCH /consent` → Postgres record updated immediately
2. Inference API consent check hits this service before feature fetch
3. On revocation: feature fetch blocked, fallback returned, audit log written

**Done when:** Consent grant/revoke persists; audit log records each state change; internal check endpoint returns correct status.

---

### Step 4 — Model Training Pipeline

**Branch:** `feat/model-training`

**Stack:** Python + LightGBM + MLflow

| Task | Detail |
|---|---|
| Parquet reader | Read date-partitioned offline store; reconstruct training DataFrame |
| Feature schema contract | Lock feature names and types at training time |
| LightGBM training | Click-probability model; train/validation split |
| Evaluation | Log AUC, precision@K, feature importance to MLflow |
| MLflow registration | Log model artifact + feature schema contract as artifact |
| Version tagging | Tag as `staging` or `production` in MLflow registry |

**Done when:** Running the pipeline produces a registered MLflow model version with a feature schema contract attached.

---

### Step 5 — Inference API

**Branch:** `feat/inference-api`

**Stack:** Python + FastAPI (REST)

> **Deviation from original design:** The original plan specified Go + gRPC. Switched to
> Python + FastAPI REST for two reasons: (1) LightGBM has no first-class Go binding —
> loading a native artifact requires CGO or an ONNX export step, both of which add
> significant build complexity for no latency benefit at this scale; (2) a REST gateway
> over gRPC would have been required anyway for the pytest test harness, making the
> gRPC layer pure overhead. The <50ms latency target is still achievable in Python with
> async I/O and a tight privacy-service timeout.

| Task | Detail |
|---|---|
| `GET /recommend/{user_id}?top_n=N` | Core inference endpoint |
| Pseudonymization | HMAC-SHA256 of `user_id` internally; raw ID never leaves the service |
| Privacy check | `httpx` call to `GET /internal/consent/check/{pseudo_id}`; 3ms timeout; fail-closed (ADR 0007) |
| Redis feature fetch | `HGETALL user:{pseudo_id}:features`; typed cast back from strings |
| Scorer factory | `model_type` read from MLflow run params → `get_scorer(model_type, uri)` → `BaseScorer`; adding a new algorithm requires no changes outside `scorers/` |
| Model hot-swap | Background `asyncio` task polls MLflow every N seconds; swaps under `asyncio.Lock` |
| Scoring | `item_score = engagement_score × genre_affinity[item.genre]`; model is user-level, genre affinity ranks items |
| Cold-start fallback | Trending feed from config on Redis miss, consent denial, or model not loaded |
| Content catalog | 20 items across 8 genres, configurable via env |
| OpenAPI spec | Auto-generated from FastAPI; saved to `docs/api/inference-api.openapi.json` |

**Done when:** Inference returns ranked Top-N; cold start returns fallback; consent revocation blocks personalization; model hot-swap works without dropped requests.

---

### Step 6 — Test Harness

**Branch:** `feat/test-harness`

**Stack:** Python + pytest

| Scenario | Key Assertion |
|---|---|
| Watch event propagation | New genre appears in Top-N within 5s of event |
| Consent revocation | Fallback feed returned; audit log entry written |
| Cold start | Generic feed returned; shifts to personalized after 3 watches |
| Feature freshness | Redis key age < 5s post-event (check `feature_age_seconds` metric) |
| Model hot-swap | New model loads within poll interval; no dropped requests during swap |
| Latency SLO | p95 end-to-end < 50ms; Redis fetch < 5ms at p99 |
| Privacy middleware overhead | Consent check adds < 5ms to request |

User behavior profiles:
- `cold_start_user` — no prior history
- `active_user` — 20+ events, full feature vector
- `churned_user` — stale features, old events

**Done when:** All 7 scenario tests pass with assertions met.

---

## Phase 2: Production Engineering

**Prerequisite:** All Phase 1 test harness scenarios pass. ✅

**Scope for this phase:** Automated CI/CD and a user simulation framework. Cloud deployment (GCP) and observability are deferred to Phase 3.

### Step 2.1 — GitHub Actions CI/CD

**Branch:** `ci/github-actions`

**Pipeline: `.github/workflows/ci.yml`**

```
PR opened / push to main
├── lint     ruff check + bandit (all Python services)
├── test     docker-compose up -d → uv run pytest -m "not slow"
└── build    docker build for each service image (no push — deferred to Phase 3)
```

| Task | Detail |
|---|---|
| Lint | `ruff check services/` + `bandit -r services/` |
| Test | Bring up stack via docker-compose; run fast test suite; teardown |
| GitHub Secret | `PSEUDONYMIZE_SECRET` — required by `conftest.py` skip gate |
| Build | Docker build for all 5 service images; fail fast on build errors |

**Done when:** Test PR → all three jobs green.

---

### Step 2.2 — User Simulation Framework

**Branch:** `test/simulation-framework`

**Why Locust instead of k6:** The platform requires stateful user journeys (watch → recommendation → watch → consent revocation), not just endpoint hammering. Locust defines `UserBehavior` classes in Python, handles configurable spawn rate and ramp profiles, and reports p50/p95/p99 latency — covering both simulation and SLO validation in one tool. When deployed on GCP, Locust workers scale as GKE pods using the same YAML configs.

**Directory layout:**

```
tests/simulation/
├── behaviors/
│   └── user.py              # Locust UserBehavior: watch, consent, recommendation journeys
├── suites/
│   ├── baseline.yaml        # Smoke: 10 users, 5m
│   ├── peak_traffic.yaml    # 500 peak users, 20m
│   └── consent_storm.yaml   # Consent-revocation heavy
├── runner.py                # Reads YAML suite, drives Locust headlessly
└── results/                 # Per-run result snapshots (JSON); large files gitignored
```

**YAML suite format:**

```yaml
name: peak_traffic
users: 200
peak_users: 500
duration: 20m
ramp_profile:
  - {from: 0, to: 500, over: 5m}
  - {hold: 10m}
  - {from: 500, to: 0, over: 5m}
user_behavior:
  watch_probability: 0.7
  genre_distribution: {action: 0.3, drama: 0.4, comedy: 0.3}
  session_length_mean_s: 45
assertions:
  latency_p95_ms: 50
  error_rate_pct: 1
```

**Replayability:** Each YAML suite is the replayable record. Re-running the same file against the updated system validates that the system still meets the same SLOs. Each run writes a results snapshot to `results/<suite-name>/<timestamp>.json` (p50/p95/p99, error rate, assertion pass/fail) for cross-run comparison.

**Assertions:** `events.test_stop` hook reads YAML assertions; exits non-zero if any threshold is breached — picked up by CI.

**Done when:** `python tests/simulation/runner.py --suite tests/simulation/suites/baseline.yaml` exits 0 with p95 < 50ms.

---

## Phase 3: Cloud Deployment + Observability (Deferred)

**Prerequisite:** Phase 2 complete.

| Task | Branch | Detail |
|---|---|---|
| GCP deployment | `infra/gcp` | GKE for orchestration; Memorystore (Redis); Cloud SQL (Postgres); GCS (Parquet + Flink checkpoints); Artifact Registry (images); self-managed Kafka/Flink/MLflow on GKE |
| Observability | `feat/observability` | Step 7 (see above) — Prometheus + Grafana deployed to GKE |
| Cloud cost dashboard | `infra/cost-dashboard` | GCP Billing → BigQuery export; Grafana BigQuery datasource; per-service cost panels via resource labels |
| Locust on GKE | `test/simulation-gke` | Locust master + worker pods; same YAML suites, cloud-scale spawn |

---

## Branch Naming Convention

| Prefix | Use for |
|---|---|
| `feat/` | New service or feature implementation |
| `infra/` | Infrastructure, Docker, Kubernetes, config |
| `ci/` | CI/CD pipelines, GitHub Actions |
| `fix/` | Bug fixes |
| `test/` | Test harness, load tests, simulation framework |
| `sim/` | Simulation suite configs and behaviors |
| `docs/` | Documentation only |
| `chore/` | Dependency bumps, cleanup, tooling |

---

## Key Design Constraints (Do Not Violate)

- Pseudonymized user IDs throughout — no PII in Kafka, Redis, logs, or Parquet
- Feature schema contract registered with every MLflow model version — prevents training/serving skew
- Inference API must hot-swap models without downtime
- Cold-start users always get a valid (non-error) response — trending fallback
- Consent revocation must block personalization on the **next request** — no stale consent cache
