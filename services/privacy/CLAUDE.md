# privacy — Local Instructions

> You are working inside `/services/privacy/`.
> Root `CLAUDE.md` still applies.

## Before Starting

1. Read `CONTEXT.md` in this directory
2. Apply context triage from root `CLAUDE.md` — consent check is called by inference-api; load its context if changing the middleware interface
3. Check `_master.md` reverse map before changing any exposed endpoint

## Local Rules

- Consent revocation must take effect on the very next inference request — no caching of consent state
- Every consent change must produce an audit log entry — this is a hard compliance requirement
- Never expose raw user PII in audit logs

## After Your Task

```
scripts/update-context.sh privacy
```
