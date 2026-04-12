---
service: model-training
path: /services/model-training/
status: active
depends_on: [parquet*, mlflow*]
depended_on_by: []
last_updated: 2026-04-11
---

# Service: model-training

## Purpose
Reads versioned Parquet snapshots from the offline feature store, trains a LightGBM click-probability model, evaluates it on held-out data, and registers the artifact along with its feature schema contract to MLflow. Inference-api hot-swaps to the new version on its next poll.

---

## Current State

- Version: not yet implemented
- API contract: none (batch pipeline)
- Key behaviors: versioned training runs, feature schema contract registered alongside model artifact

---

## Architecture Notes

---

## Recent Changes

---

## Flags

---

## Interfaces

### Exposes
- MLflow: registers model artifact + feature schema contract per version

### Consumes
- Parquet: date-partitioned offline feature store (read)

---

## Do Not
<!-- Constraints will be added as contracts are frozen during development -->
