# inference-api — Local Instructions

> You are working inside `/services/inference-api/`.
> Root `CLAUDE.md` still applies.

## Before Starting

1. Read `CONTEXT.md` in this directory
2. Apply context triage from root `CLAUDE.md` — load other service contexts only if this task crosses a service boundary
3. Check `_master.md` reverse map before changing any exposed interface

## Local Rules

- Consent check via privacy service must run before any feature fetch — never bypass
- Latency budget: <20ms model inference, <50ms end-to-end
- Cold-start fallback (Redis miss) must return non-personalized trending feed, not an error

## After Your Task

```
scripts/update-context.sh inference-api
```
