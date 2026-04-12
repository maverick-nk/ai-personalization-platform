# Implementation Plan

> Status: In progress — architecture fully designed, implementation not started.
> Last updated: 2026-04-11

---

## Phases Overview

| Phase | Scope | Goal |
|---|---|---|
| Phase 1 | Core system | All services running, end-to-end data flow verified by test harness |
| Phase 2 | Production engineering | Dockerized, Kubernetes, CI/CD, load tested |

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

**Stack:** Go + gRPC

| Task | Detail |
|---|---|
| `GetRecommendations(user_id, top_n)` RPC | Core inference endpoint |
| Privacy middleware | gRPC interceptor → consent check → block if revoked |
| Redis feature fetch | `user:{id}:features` hash; target <5ms |
| Model loading | Load LightGBM model from MLflow artifact path |
| Model hot-swap | Background goroutine polls MLflow every N seconds; atomic model swap |
| Scoring | Score each candidate content item; rank by click probability |
| Cold-start fallback | Return trending feed (hardcoded or from config) if Redis miss |
| HTTP gateway | Optional REST wrapper over gRPC for test harness compatibility |

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

### Step 7 — Observability Stack

**Branch:** `feat/observability`

**Stack:** Prometheus + Grafana

| Metric | Instrument In | Purpose |
|---|---|---|
| `inference_latency_ms` (p50/p95/p99) | Inference API | Latency SLO |
| `feature_age_seconds` | Feature pipeline / Redis | Freshness alert |
| `kafka_consumer_lag` | Feature pipeline | Processing lag |
| `prediction_score_distribution` | Inference API | Model drift |
| `consent_revocations_total` | Privacy service | Audit signal |
| `cold_start_fallback_rate` | Inference API | Cold start prevalence |

Deliverables:
- Prometheus scrape endpoints in each Python and Go service
- `docker-compose` includes Prometheus + Grafana containers
- Grafana dashboard JSON checked into `infra/grafana/`
- Alert rule for `feature_age_seconds > 5`

**Done when:** Grafana dashboard shows all 6 metrics populated after running the test harness.

---

## Phase 2: Production Engineering

**Prerequisite:** All Phase 1 test harness scenarios pass.

| Task | Branch | Detail |
|---|---|---|
| Dockerize all services | `infra/dockerize-services` | Dockerfile per service, multi-stage builds |
| Local Kubernetes | `infra/kubernetes` | kind/minikube manifests; health/readiness probes |
| GitHub Actions CI/CD | `ci/github-actions` | lint → test → build → push on PR merge |
| k6 load testing | `test/load-testing-k6` | Ramp test for `GetRecommendations`; validate <50ms p95 under load |

---

## Branch Naming Convention

| Prefix | Use for |
|---|---|
| `feat/` | New service or feature implementation |
| `infra/` | Infrastructure, Docker, Kubernetes, config |
| `ci/` | CI/CD pipelines, GitHub Actions |
| `fix/` | Bug fixes |
| `test/` | Test harness, load tests |
| `docs/` | Documentation only |
| `chore/` | Dependency bumps, cleanup, tooling |

---

## Key Design Constraints (Do Not Violate)

- Pseudonymized user IDs throughout — no PII in Kafka, Redis, logs, or Parquet
- Feature schema contract registered with every MLflow model version — prevents training/serving skew
- Inference API must hot-swap models without downtime
- Cold-start users always get a valid (non-error) response — trending fallback
- Consent revocation must block personalization on the **next request** — no stale consent cache
