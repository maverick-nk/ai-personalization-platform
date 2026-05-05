---
service: model-training
path: /services/model-training/
status: active
depends_on: [parquet*, mlflow*]
depended_on_by: []
last_updated: 2026-05-04
---

# Service: model-training

## Purpose
Reads versioned Parquet snapshots from the offline feature store, trains a LightGBM click-probability model, evaluates it on held-out data, and registers the artifact along with its feature schema contract to MLflow. Inference-api hot-swaps to the new version on its next poll.

---

## Current State

- Version: 0.1.0
- API contract: none (batch pipeline — invoked via `uv run python -m app`)
- Key behaviors:
  - Reads date-partitioned Parquet from `/data/parquet` (configurable via `MODEL_TRAINING_PARQUET_BASE_PATH`)
  - Chronological train/val split by `event_date` (last 7 days = val, default)
  - Derives binary `engaged` label: `avg_watch_duration >= 70.0` (configurable threshold)
  - Expands `session_genre_vector` JSON into per-genre float columns; genres derived from training split only (no leakage)
  - Trainer is algorithm-agnostic via `BaseTrainer` ABC; `LightGBMTrainer` is the current implementation
  - Logs AUC, Precision@10, and per-feature importances to MLflow
  - Registers model as `personalization-click-model` in MLflow registry; tags version with `staging` alias
  - Logs `feature_schema.json` alongside model artifact — the contract inference-api validates at serving time

---

## Architecture Notes

- `BaseTrainer` ABC in `app/trainer.py` decouples the training orchestration from the algorithm. Adding XGBoost or any sklearn-compatible model requires only a new file in `app/trainers/` and one line in `app/trainers/factory.py`.
- MLflow experiment is created with explicit `artifact_location="mlflow-artifacts:/"` so artifact uploads go via HTTP proxy regardless of the server's `--default-artifact-root`. Required because the training pipeline runs on the host while MLflow artifacts are stored inside Docker volumes.
- MLflow server (`docker-compose.yml`) must be configured with `--serve-artifacts --artifacts-destination /mlflow/artifacts --default-artifact-root mlflow-artifacts:/` for host-side clients to upload artifacts.
- `feature_schema.json` lists features in the same order the inference-api reads them from Redis — any change here is a training/serving skew risk and must be coordinated with inference-api.

---

## Recent Changes

- [2026-05-04] Built end-to-end ML pipeline consuming batch data from `/data/parquet`, training LightGBM click-probability model, evaluating on chronological val split, and registering versioned model + feature schema contract to MLflow.

---

## Flags

---

## Interfaces

### Exposes
- **MLflow model registry:** registers `personalization-click-model` with version alias (`staging` / `production`)
- **MLflow artifact — `feature_schema.json`:** feature contract consumed by inference-api at model load time
  - Schema: `{ version, features: [{name, dtype, categories?}], label, label_definition, time_of_day_categories, genres }`
  - Current features: `watch_count_10min`, `category_affinity_score`, `avg_watch_duration`, `recency_score`, `time_of_day_bucket`, `genre_{name}` per genre in training data

### Consumes
- **Parquet:** date-partitioned offline feature store at `/data/parquet` (written by feature-pipeline)
  - Key pattern: `year=YYYY/month=MM/day=DD/batch_*.parquet`
  - Schema: identical to `services/feature-pipeline/app/parquet_sink.py:PARQUET_SCHEMA`

---

## Do Not

- Never register a model without a `feature_schema.json` artifact — inference-api depends on it for schema validation
- Never train on live Redis data — training must use versioned Parquet snapshots only
- Never derive genre list from the validation split — genres must come from training data only to prevent leakage
- Never add features to training that are not present in the Redis feature hash — training/serving skew
