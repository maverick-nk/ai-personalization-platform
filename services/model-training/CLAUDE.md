# model-training — Local Instructions

> You are working inside `/services/model-training/`.
> Root `CLAUDE.md` still applies.

## Before Starting

1. Read `CONTEXT.md` in this directory
2. Apply context triage from root `CLAUDE.md` — if changing the feature schema contract, also load `feature-pipeline` and `inference-api` CONTEXT.md
3. Check `_master.md` before modifying the MLflow artifact structure

## Local Rules

- Feature schema contract must be registered alongside every model artifact in MLflow — never register a model without it
- Training data must come from versioned Parquet snapshots — never train on live Redis data

## After Your Task

```
scripts/update-context.sh model-training
```
