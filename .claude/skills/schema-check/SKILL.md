---
name: schema-check
category: infrastructure
description: Diffs the live feature schema in Redis and Parquet against the feature schema contract registered in MLflow — catches training/serving skew before it causes silent model degradation. Triggers on phrases like "check schema", "schema drift", "training serving skew", "/schema-check", "are features consistent", or "validate feature schema".
---

# Schema Check

This skill detects training/serving feature skew by comparing three sources of truth:

1. **Redis** — what features are actually being written to the online store right now
2. **Parquet** — what features are in the offline store used for training
3. **MLflow** — what feature schema contract was locked in when the current production model was registered

Any divergence between these is a skew risk. Silent skew is one of the most common causes of model degradation in production.

---

## Step 1 — Get the Registered Feature Schema Contract from MLflow

Query MLflow for the latest production model version and its attached feature schema artifact:

```bash
# List registered models
curl -s http://localhost:5000/api/2.0/mlflow/registered-models/list

# Get latest version of the production model
curl -s "http://localhost:5000/api/2.0/mlflow/model-versions/search?filter=name%3D'personalization-model'&order_by=version_number+DESC&max_results=1"
```

From the response, find the `run_id`. Then fetch the `feature_schema.json` artifact:

```bash
curl -s "http://localhost:5000/api/2.0/mlflow/artifacts/list?run_id=<run_id>&path=feature_schema"
# Then download the artifact
curl -s "http://localhost:5000/get-artifact?run_uuid=<run_id>&path=feature_schema/schema.json"
```

Expected schema format:
```json
{
  "features": [
    {"name": "watch_count_10min",       "type": "int"},
    {"name": "category_affinity_score", "type": "float"},
    {"name": "avg_watch_duration",      "type": "float"},
    {"name": "time_of_day_bucket",      "type": "string"},
    {"name": "recency_score",           "type": "float"},
    {"name": "session_genre_vector",    "type": "list[float]"}
  ],
  "model_version": "<version>",
  "registered_at": "<timestamp>"
}
```

If no model is registered: "No production model found in MLflow. Has model training been run? See `feat/model-training` in `docs/implementation-plan.md`." — stop.

---

## Step 2 — Inspect Redis Live Features

Pick a known active user's pseudo_id (or accept one as an argument: `/schema-check <pseudo_id>`).

If no pseudo_id provided, check if any keys exist:
```bash
docker compose exec redis redis-cli KEYS "user:*:features"
```

Take the first result and inspect it:
```bash
docker compose exec redis redis-cli HGETALL "user:<pseudo_id>:features"
```

Parse the field names and infer types from the values.

If no keys found: "Redis has no feature keys. Has the feature pipeline processed any events? Run `/start-infra` and send a test event." — stop.

---

## Step 3 — Inspect Parquet Offline Store

Look for Parquet files in the offline store path (default: `data/offline-store/` or from env `PARQUET_STORE_PATH`).

```bash
# List recent partitions
ls -lt data/offline-store/ | head -5
```

Read the schema from the most recent partition using Python:

```python
import pyarrow.parquet as pq
schema = pq.read_schema('data/offline-store/<latest-partition>/features.parquet')
print(schema)
```

Extract field names and types.

If no Parquet files found: "Offline store is empty. The feature pipeline batch sink hasn't run yet." — note as a warning but continue with the Redis vs MLflow comparison.

---

## Step 4 — Three-Way Diff

Build a comparison table:

| Feature | MLflow Contract | Redis (live) | Parquet (offline) | Status |
|---|---|---|---|---|
| `watch_count_10min` | `int` | `int` | `int` | ✓ |
| `category_affinity_score` | `float` | `float` | `float` | ✓ |
| `avg_watch_duration` | `float` | `float` | — | MISSING in Parquet |
| `time_of_day_bucket` | `string` | `string` | `string` | ✓ |
| `recency_score` | `float` | — | `float` | MISSING in Redis |
| `session_genre_vector` | `list[float]` | `list[float]` | `list[float]` | ✓ |
| `new_feature_x` | — | `string` | — | EXTRA in Redis (not in contract) |

Status legend:
- ✓ = present and type matches in all available sources
- `MISSING in Redis` = feature expected by model but not in online store (inference will fail or silently get a null)
- `MISSING in Parquet` = feature not being written to offline store (training won't have it)
- `TYPE MISMATCH` = feature present but different type (silent coercion or crash at inference)
- `EXTRA` = feature in store but not in MLflow contract (harmless, but may indicate drift)

---

## Step 5 — Report and Recommend

```
Schema Check — YYYY-MM-DD HH:MM
─────────────────────────────────────────────────────
MLflow model:  personalization-model v<N> (registered: <date>)
Redis sample:  user:<pseudo_id>:features
Parquet:       data/offline-store/<partition>/

Result: SKEW DETECTED / CLEAN

Issues found:
  BLOCKING — MISSING in Redis: recency_score
    → Inference API will receive null for this feature. Fix: ensure
      feature-pipeline writes recency_score to Redis.

  WARNING — EXTRA in Redis: new_feature_x
    → Not in MLflow contract. Will be ignored at inference. Consider
      retraining model to include it, or remove it from the pipeline.

  INFO — MISSING in Parquet: avg_watch_duration
    → Training data won't include this feature. Retrain after the
      Parquet sink is fixed.
```

Severity:
- **BLOCKING:** feature expected by model is absent or wrong type in Redis → inference will fail or silently degrade
- **WARNING:** mismatch between sources that isn't immediately breaking but will cause issues on next retrain
- **INFO:** informational only, no immediate action needed

If clean: "Schema is consistent across MLflow, Redis, and Parquet — no skew detected."
