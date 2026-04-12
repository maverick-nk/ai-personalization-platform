# tests — Local Instructions

> You are working inside `/tests/`.
> Root `CLAUDE.md` still applies.

## Before Starting

1. Read `CONTEXT.md` in this directory
2. Load `CONTEXT.md` for any service whose API you are adding or modifying test coverage for
3. Check `_master.md` to understand the full blast radius of a scenario change

## Local Rules

- End-to-end tests must run against real service instances — no mocking inter-service calls
- Latency assertions must use p95, not average
- Consent revocation tests must verify both the audit log entry and the fallback feed response

## After Your Task

```
scripts/update-context.sh tests
```
