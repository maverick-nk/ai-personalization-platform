---
service: inference-api
path: /services/inference-api/
status: active
depends_on: [redis*, mlflow*, privacy]
depended_on_by: [tests]
last_updated: 2026-05-13
---

# Service: inference-api

## Purpose
Serves real-time personalized recommendations. Checks consent via privacy service, fetches user features from Redis, scores candidate content using the latest model from MLflow, and returns a ranked Top-N list — all within a <50ms latency budget.

---

## Current State

- Version: implemented (Step 5 complete, 2026-05-13)
- API contract: REST (Python + FastAPI) — switched from Go + gRPC; see ADR 0010
- Key behaviors: pseudonymize user_id → fail-closed consent check (3ms timeout) → Redis feature fetch → scorer factory → Top-N ranking; trending fallback on consent denial, cold start, or model unavailable; model hot-swap via background asyncio task polling MLflow

---

## Architecture Notes

- Scorer factory (`scorers/factory.py`) maps `model_type` MLflow run param → `BaseScorer` subclass; new algorithm = one new file, no changes elsewhere
- `asyncio.Lock` guards model reads and hot-swap writes — prevents a request from seeing a partially-loaded model mid-swap
- Blocking MLflow I/O (`_load()`) offloaded via `asyncio.to_thread()` to avoid stalling the event loop during artifact downloads
- `response_model_exclude_none=True` — field presence is semantic: absent `score` means "not scored", absent `model_version` means "model not invoked"
- Scoring formula: `item_score = engagement_score × genre_affinity[item.genre]` — model outputs a user-level engagement score; genre affinity from `session_genre_vector` differentiates items

---

## Recent Changes

- [2026-05-13] Implemented inference-api in Python + FastAPI REST (pivoted from Go + gRPC per ADR 0010): consent check → Redis feature fetch → scorer factory → Top-N ranking; model hot-swap without blocking request path; fail-closed privacy; trending fallback for cold start, consent denied, and model unavailable

---

## Flags

---

## Interfaces

### Exposes
- `GET /recommend/{user_id}?top_n=10` — returns ranked content list with scores; `top_n` 1–100, default 10
- `GET /health` — returns `{"status": "ok", "model_version": "<version> | null"}`

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
- Do not switch to gRPC without first resolving LightGBM artifact loading — CGO or ONNX export was explicitly rejected; the language/protocol choice is downstream of the artifact loading constraint (see ADR 0010)
- Do not add synchronous Parquet point-lookups on Redis miss — Parquet is a batch scan store; per-request access violates the 50ms SLO; Redis miss is cold-start, trending fallback is the correct response (see ADR 0011)
- Do not remove asyncio.Lock from model_store.get() — even in the single-threaded asyncio model, get() contains an await point; removing the lock allows a concurrent caller to be scheduled between version-check and set in _poll_loop (see ADR 0012)
