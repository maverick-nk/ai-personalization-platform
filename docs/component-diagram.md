# Streaming Personalization Platform — Component Diagram

> Test-driven architecture: all user behavior is simulated via API calls and validated through a test framework. No UI layer.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        TEST HARNESS                             │
│  Scenario Runner · User Behavior Simulator · Validator          │
└───────────────┬──────────────────────────┬──────────────────────┘
                │ POST /events/*           │ GET /recommend/{id}
                ▼                          ▼
┌──────────────────────┐    ┌──────────────────────────────────────┐
│  Event Ingestion API │    │       Inference / Rec API            │
│  (REST)              │    │       (gRPC · Go · <50ms)            │
└────────┬─────────────┘    └────────┬──────────────┬─────────────┘
         │ produce                   │ consent check │ fetch features
         ▼                           ▼               ▼
┌──────────────────┐   ┌─────────────────────┐  ┌──────────────────┐
│      KAFKA       │   │  Privacy Enforcement │  │  Online Feature  │
│  (Message Bus)   │   │  Layer (Middleware)  │  │  Store (Redis)   │
│                  │   │  Postgres · Audit Log│  │  <5ms lookup     │
└────────┬─────────┘   └─────────────────────┘  └──────────────────┘
         │ consume                                        ▲
         ▼                                                │ write <2s
┌─────────────────────────────────────────────────────────┴──────┐
│              Streaming Feature Pipeline (Flink)                 │
│   watch_count_10min · category_affinity · avg_watch_duration    │
│   time_of_day_bucket · recency_score · session_genre_vector     │
└──────────────────────────────┬─────────────────────────────────┘
                                │ batch sink
                                ▼
                  ┌─────────────────────────┐
                  │  Offline Feature Store  │
                  │  (Parquet · versioned)  │
                  └────────────┬────────────┘
                               │ training data
                               ▼
                  ┌─────────────────────────┐
                  │  Model Training Pipeline│
                  │  (LightGBM)             │
                  └────────────┬────────────┘
                               │ register artifact
                               ▼
                  ┌─────────────────────────┐
                  │     Model Registry      │
                  │  (MLflow · versioned)   │◄──── Inference API polls
                  └─────────────────────────┘
```

---

## Components

### 🧪 Test Harness

| Sub-component | Role |
|---|---|
| Scenario Runner | Orchestrates test flows end-to-end via pytest |
| User Behavior Simulator | Configurable profiles: cold start / active / churned users |
| Validation & Assertions | Relevance scoring (Precision@K), latency checks, privacy compliance |

---

### 📡 Event Ingestion API

**Type:** REST  
**Responsibility:** Accept raw user events, validate schema, pseudonymize user IDs, publish to Kafka.

| Endpoint | Payload |
|---|---|
| `POST /events/watch` | user_id, content_id, watch_pct, timestamp |
| `POST /events/session` | user_id, session_id, device, start_time |

---

### 🎯 Inference / Recommendation API

**Type:** gRPC · Go  
**Latency target:** <50ms end-to-end

| Endpoint | Behaviour |
|---|---|
| `GET /recommend/{user_id}?top_n=10` | Consent check → feature fetch → model score → rank → return top-N |

Internal steps:
1. Privacy middleware checks consent (Postgres)
2. Fetch user features from Redis (<5ms)
3. Load latest model from registry
4. Score candidate content items
5. Return ranked list with scores

---

### 📨 Kafka (Message Bus)

| Topic | Producer | Consumer |
|---|---|---|
| `user.watch.events` | Event Ingestion API | Flink pipeline |
| `user.session.events` | Event Ingestion API | Flink pipeline |

Properties: durable, ordered, replay-capable, pseudonymized payloads.

---

### ⚡ Streaming Feature Pipeline (Flink)

Consumes Kafka topics and computes windowed features per user.

| Feature | Description |
|---|---|
| `watch_count_10min` | Rolling count of watches in last 10 minutes |
| `category_affinity_score` | Weighted score per content genre |
| `avg_watch_duration` | Mean watch completion % |
| `time_of_day_bucket` | Morning / afternoon / evening / night |
| `recency_score` | Decay-weighted engagement score |
| `session_genre_vector` | Genre distribution in current session |

**Outputs:**
- → Redis (online store) within ~2 seconds
- → Parquet (offline store) as batch sink

---

### 🗄️ Feature Stores

#### Online Store — Redis
| Property | Value |
|---|---|
| Key pattern | `user:{id}:features` |
| Lookup latency | <5ms |
| TTL | Configurable per feature |
| Consumer | Inference API at serving time |

#### Offline Store — Parquet
| Property | Value |
|---|---|
| Partitioning | By date |
| Schema | Identical to online store (training/serving consistency) |
| Consumer | Model training pipeline |

---

### 🧠 Model Training Pipeline

- Reads versioned Parquet snapshots from offline store
- Trains LightGBM click-probability model
- Evaluates against held-out data
- Registers artifact + feature schema contract to Model Registry

---

### 📦 Model Registry (MLflow)

- Stores versioned model artifacts
- Stores **feature schema contract** alongside each version
- Inference API polls for new versions and hot-swaps without downtime

---

### 🔒 Privacy Enforcement Layer

**Type:** Middleware (interceptor in Inference API)  
**Backend:** Postgres consent table

| Endpoint | Action |
|---|---|
| `PATCH /privacy/consent/{user_id}` | Grant or revoke personalization consent |
| `GET /privacy/audit/{user_id}` | Retrieve audit log for a user |

**Revocation flow:**
1. Consent record updated in Postgres immediately
2. Next inference request hits middleware → consent check fails
3. Redis feature fetch is blocked entirely
4. Fallback non-personalized trending feed returned
5. Audit log entry written

---

### 📊 Observability Stack (Prometheus + Grafana)

| Metric | Purpose |
|---|---|
| `inference_latency_ms` (p50/p95/p99) | Latency SLO validation |
| `feature_age_seconds` | Feature freshness (staleness alert) |
| `kafka_consumer_lag` | Pipeline processing lag |
| `prediction_score_distribution` | Model drift detection |
| `consent_revocations_total` | Privacy audit signal |
| `cold_start_fallback_rate` | Cold start prevalence |

---

## Key Interaction Flows

### Flow 1 — Watch Event → Updated Recommendations

```
Test                  Ingestion API     Kafka       Flink       Redis      Rec API
 │                         │              │            │            │           │
 │─ POST /events/watch ───►│              │            │            │           │
 │                         │─ publish ───►│            │            │           │
 │                         │              │─ consume ─►│            │           │
 │                         │              │            │─ write ───►│           │
 │                         │              │            │  (~2s)     │           │
 │─ GET /recommend ────────────────────────────────────────────────────────────►│
 │                         │              │            │            │◄─ fetch ──│
 │◄── ranked list (updated genre) ────────────────────────────────────────────│
```

### Flow 2 — Consent Revocation

```
Test                  Privacy API     Postgres     Rec API     Redis
 │                         │              │            │           │
 │─ PATCH /consent revoke ►│              │            │           │
 │                         │─ update ────►│            │           │
 │                         │              │            │           │
 │─ GET /recommend ────────────────────────────────────►│           │
 │                         │              │◄─ check ───│           │
 │                         │              │ (revoked)  │           │
 │                         │              │            │ ✗ blocked │
 │◄── fallback trending feed (non-personalized) ───────│           │
```

### Flow 3 — Cold Start User

```
Test                  Rec API        Redis        Fallback
 │                       │              │              │
 │─ GET /recommend ──────►│              │              │
 │                        │─ fetch ─────►│              │
 │                        │             (miss)          │
 │                        │─────────────────────────────►│
 │◄── generic trending ───│◄─────────────────────────────│
 │                        │              │              │
 │─ POST /events/watch x3 ► (watch 3 videos)            │
 │─ GET /recommend ──────►│              │              │
 │◄── genre-shifted recs ─│ (Redis now populated)
```

---

## Test Assertion Reference

| Test Scenario | Key Assertion |
|---|---|
| Watch event propagation | New genre appears in top-N within 5s of event |
| Consent revocation | Response is fallback feed; audit log written |
| Cold start | Generic feed returned; shifts after 3 watches |
| Feature freshness | Redis key age < 5s post-event (Prometheus metric) |
| Model hot-swap | New model loaded within poll interval; no dropped requests |
| Latency SLO | p95 end-to-end < 50ms; Redis fetch < 5ms at p99 |
| Privacy middleware overhead | Consent check adds < 5ms to request |