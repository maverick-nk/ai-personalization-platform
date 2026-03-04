# 🎬 Privacy-Preserving Real-Time Streaming Personalization Platform

A focused end-to-end ML systems project that simulates how platforms like Netflix and YouTube personalize content — with **real-time feature updates, low-latency inference, and privacy-by-design controls**.

Note: This project is intentionally scoped to a **single strong use case** to deeply demonstrate ML infrastructure, distributed systems, and privacy-aware engineering.

---

# Problem Space

Streaming platforms such as Netflix and YouTube personalize content using:

- Recent watch history  
- Engagement patterns  
- Session activity  
- Time-of-day behavior  

However, production systems face major challenges:

## Real-Time Constraints

- User opens the app → recommendations must load in **<50ms**
- Features must reflect **recent activity (seconds, not hours)**

## ML Systems Challenges

- Offline training features ≠ online inference features (training/serving skew)
- Feature drift over time
- Weak monitoring for model degradation
- Hard-to-debug production issues

## Privacy Challenges

- Users can revoke consent at any time
- Personalization must stop immediately
- Only allowed features should be used
- PII must not leak into logs
- System must support auditability


## 🎯 Core Problem Statement

> How can we design a small-scale real-time personalization system that updates user features in seconds, serves low-latency recommendations, and enforces consent-aware privacy controls?

This is not about building the most advanced recommender model. It is about building the **infrastructure correctly**.

---

# Solution Space (High-Level Design)

We build a minimal but realistic ML platform with:

- Real-time event ingestion
- Streaming feature computation
- Online + offline feature stores
- Low-latency model serving
- Consent-aware privacy enforcement
- Observability & monitoring

## Real-Time Data Flow

User watches video  → Event sent to Kafka  → Streaming job updates features  → Online feature store updated  → User refreshes homepage  → Inference service fetches features  → Model predicts top-N content  → Response returned (<50ms)

---

# Core Components

## Event Ingestion

- Kafka
- Watch events
- Session events
- Pseudonymized user IDs
- Schema validation

## Streaming Feature Pipeline

Using Flink (or lightweight streaming alternative):

Compute features such as:

- Recent watch count (last 10 min)
- Category affinity score
- Average watch duration
- Time-of-day engagement
- Recency score

Outputs:

- Online feature store (Redis)
- Offline training dataset (Parquet)

Ensures training-serving consistency.

## Feature Store Architecture

### Online Store
- Redis
- Keyed by `user_id`
- <5ms lookup latency

### Offline Store
- Parquet files
- Used for training
- Versioned feature definitions

## Model Training

Train a simple but realistic model:

- Logistic Regression or LightGBM
- Predict click probability for candidate content

Track:
- Feature schema
- Model version
- Evaluation metrics
- Experiment history

## Inference Service

- Go service
- gRPC
- Fetches online features
- Loads latest model
- Returns Top-N ranked videos

Latency targets:
- <20ms model inference
- <50ms end-to-end API

## Privacy Enforcement Layer

Key capabilities:

- Consent table (Postgres)
- Middleware checks before inference
- Feature filtering per user
- Pseudonymized identifiers
- Audit logging
- Fallback to non-personalized trending feed

If consent is revoked:
- Personalization disabled immediately
- No feature usage
- Fallback content served

## Observability & Monitoring

Track:

- Inference latency
- Feature freshness
- Event processing lag
- Prediction distribution shifts
- Feature drift

Use:
- Prometheus
- Grafana
- Structured logging

---

# MVP Scope

The MVP is intentionally constrained.

## ✅ Phase 1: Core System

- Kafka ingestion
- Streaming job computing 3–5 features
- Redis online store
- Parquet offline dataset
- Basic LightGBM model
- REST inference API
- Consent-check middleware

## ✅ Phase 2: Production Engineering

- Dockerize services
- Local Kubernetes (kind/minikube)
- CI/CD via GitHub Actions
- Load testing (k6)
- Metrics dashboard

## ❌ Out of Scope

- Deep learning recommenders
- Reinforcement learning
- Federated learning
- Multi-region HA
- Complex ranking systems
