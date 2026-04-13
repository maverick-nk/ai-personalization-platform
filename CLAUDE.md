# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A privacy-preserving real-time streaming personalization platform — simulating how Netflix/YouTube personalize content with real-time feature updates, low-latency inference, and consent-aware privacy controls. The focus is ML infrastructure correctness, not model sophistication.

> **Status:** Architecture is fully designed (see `docs/`). Implementation is in progress.

## Architecture

The system is **test-driven** — no UI layer. All user behavior is simulated via API calls and validated through a pytest test harness.

### Data Flow

```
User event → Event Ingestion API → Kafka → Flink (streaming features) → Redis (online store)
                                                                      → Parquet (offline store) → LightGBM training → MLflow registry
Recommendation request → Inference API (Go/gRPC) → Privacy middleware (Postgres) → Redis → Model → Top-N response
```

End-to-end latency target: **<50ms**. Redis feature lookup: **<5ms**. Feature freshness: **<2s** after event.

### Services

| Service | Stack | Role |
|---|---|---|
| Event Ingestion API | REST | Accepts watch/session events, pseudonymizes user IDs, publishes to Kafka |
| Inference / Recommendation API | Go, gRPC | Consent check → feature fetch → model score → ranked Top-N |
| Streaming Feature Pipeline | Apache Flink | Consumes Kafka, computes windowed features, writes to Redis + Parquet |
| Privacy Enforcement Layer | Middleware + Postgres | Consent table, audit logging, blocks feature access on revocation |
| Model Training Pipeline | LightGBM | Reads Parquet offline store, trains click-probability model |
| Model Registry | MLflow | Versioned model artifacts + feature schema contracts; Inference API hot-swaps on poll |
| Observability | Prometheus + Grafana | Latency, feature freshness, Kafka lag, prediction drift, consent metrics |

### Feature Store Design

- **Online (Redis):** Key pattern `user:{id}:features`, <5ms lookup, TTL per feature
- **Offline (Parquet):** Date-partitioned, schema-identical to online store (training/serving consistency)

### Features Computed by Flink

`watch_count_10min`, `category_affinity_score`, `avg_watch_duration`, `time_of_day_bucket`, `recency_score`, `session_genre_vector`

### Privacy Enforcement

Consent is stored in Postgres. On revocation: consent check fails immediately → Redis fetch blocked → fallback non-personalized trending feed returned → audit log written.

### Key Design Constraints

- Pseudonymized user IDs throughout (no PII in Kafka, Redis, or logs)
- Feature schema contract is registered alongside each model version in MLflow (prevents training/serving skew)
- Inference API hot-swaps models without downtime by polling the registry
- Cold-start users receive a generic trending feed; shifts to personalized after sufficient events

## Test Scenarios

The test harness (`pytest`) validates:

| Scenario | Assertion |
|---|---|
| Watch event propagation | New genre appears in Top-N within 5s |
| Consent revocation | Fallback feed returned; audit log written |
| Cold start | Generic feed → shifts after 3 watches |
| Feature freshness | Redis key age < 5s post-event |
| Model hot-swap | New model loads within poll interval; no dropped requests |
| Latency SLO | p95 end-to-end < 50ms; Redis fetch < 5ms at p99 |
| Privacy middleware overhead | Consent check adds < 5ms |

## Infrastructure (Phase 2)

Docker + local Kubernetes (kind/minikube), CI/CD via GitHub Actions, load testing via k6.

## Python Tooling Convention

All Python services in this repo use **[uv](https://github.com/astral-sh/uv)** as the package manager and script runner. Do not use pip, pip-tools, poetry, or conda.

| Context | Convention |
|---|---|
| Dependency management | `pyproject.toml` + `uv.lock` — no `requirements.txt` |
| Installing deps | `uv sync` (dev) · `uv sync --frozen --no-dev` (Docker/CI) |
| Running services/scripts | `uv run <command>` |
| Adding a dependency | `uv add <package>` |
| Dockerfiles | Copy uv binary from `ghcr.io/astral-sh/uv:latest`; use `uv sync --frozen --no-dev` |

**Does not apply to:** External images we don't control (e.g. `ghcr.io/mlflow/mlflow`) — use pip there.

Dockerfile pattern for every Python service:
```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0"]
```

---

## Out of Scope

Deep learning recommenders, RL, federated learning, multi-region HA, complex ranking systems.

---

## Context System

This repo uses a graph-aware context system. Read `_master.md` first on any task, then apply this triage:

**Always load:** `CONTEXT.md` of the service(s) directly named in the task.

**Load a dependency's `CONTEXT.md` only if the task involves:**
- Adding/changing/removing a call to its API, queue, or data source
- Changing a contract that dependency relies on (endpoint, event schema, feature schema)
- Modifying shared config or data structures used across both services

**Skip a dependency's `CONTEXT.md` if the task is:**
- Refactoring or optimizing logic inside a single service
- Fixing a bug confirmed to be within one service
- Adding/modifying unit tests that don't cross service boundaries

**Decision rule:** Would this change break or require awareness from another service? If no → skip. If yes → load.

| Task example | Load |
|---|---|
| Optimize Redis lookup in inference-api | inference-api only |
| Change feature schema in feature-pipeline | feature-pipeline + inference-api + model-training |
| Fix null check in privacy service | privacy only |
| Add new Kafka topic in event-ingestion | event-ingestion + feature-pipeline |

**After every task**, run `scripts/update-context.sh <service-name>` for each service touched.
