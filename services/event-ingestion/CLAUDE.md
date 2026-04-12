# event-ingestion — Local Instructions

> You are working inside `/services/event-ingestion/`.
> Root `CLAUDE.md` still applies.

## Before Starting

1. Read `CONTEXT.md` in this directory
2. Apply context triage from root `CLAUDE.md` — load other service contexts only if this task crosses a service boundary
3. Check `_master.md` reverse map before changing any exposed interface

## Local Rules

- User IDs must be pseudonymized before any Kafka publish — never log or persist raw user_id
- Schema validation must reject malformed events before they reach Kafka

## After Your Task

```
scripts/update-context.sh event-ingestion
```
