# feature-pipeline — Local Instructions

> You are working inside `/services/feature-pipeline/`.
> Root `CLAUDE.md` still applies.

## Before Starting

1. Read `CONTEXT.md` in this directory
2. Apply context triage from root `CLAUDE.md` — if changing feature schema, also load `inference-api` and `model-training` CONTEXT.md (schema contract crosses both)
3. Check `_master.md` reverse map before changing any feature definition

## Local Rules

- Feature schema in Redis and Parquet must always be identical — changing one requires changing both
- Redis writes must complete within 2s of the source Kafka event
- Never drop or rename an existing feature without checking `inference-api` and `model-training` dependencies first

## After Your Task

```
scripts/update-context.sh feature-pipeline
```
