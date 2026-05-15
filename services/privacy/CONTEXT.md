---
service: privacy
path: /services/privacy/
status: active
depends_on: [postgres*]
depended_on_by: [inference-api, tests]
last_updated: 2026-05-15
---

# Service: privacy

## Purpose
Enforces consent-aware access control for personalization. Maintains a consent table in Postgres, exposes endpoints to grant/revoke consent and retrieve audit logs. Acts as middleware interceptor in the inference-api — blocks feature access immediately on revocation.

---

## Current State

- Version: 0.1.0
- API contract: REST (FastAPI + uvicorn, port 8001)
- Stack: Python 3.11, FastAPI, SQLAlchemy async + asyncpg, Alembic, pydantic-settings
- Deployment: Docker container via docker-compose; startup managed by `entrypoint.sh`
- Key behaviors:
  - Consent upsert + audit log entry written atomically in one transaction
  - Internal consent check is a primary-key lookup (no joins) — must stay under 5ms
  - Opt-in model: missing consent record → `consent_granted=false` by default
  - `audit_log` is RANGE-partitioned by `timestamp` (monthly child tables); partitions created/dropped at startup
  - Audit history retained for `AUDIT_RETENTION_MONTHS` months (default: 3); consent table never purged
  - OpenAPI spec exported to `docs/api/privacy.openapi.json`

---

## Architecture Notes

- `audit_log` uses `GENERATED ALWAYS AS IDENTITY` (not `SERIAL`) because SERIAL sequences don't propagate to PostgreSQL child partitions. Composite PK `(id, timestamp)` is required — partition key must be part of every unique constraint. See ADR 0006.
- `Base.metadata.create_all()` cannot emit `PARTITION BY RANGE` DDL — schema setup must use the Alembic migration or raw SQL. Integration test fixture creates schema directly with a catch-all partition for test coverage.
- `expire_on_commit=False` on `AsyncSessionLocal` is required in async SQLAlchemy — without it, attribute access after `commit()` triggers lazy loads that raise `MissingGreenlet` in an async context.
- Public endpoints (`PATCH /consent`, `GET /audit`) accept raw `user_id` and pseudonymize internally. Internal endpoint (`GET /internal/consent/check`) accepts `pseudo_id` directly — the inference-api already holds the pseudonymized form from Redis keys.

---

## Docker

Container startup is handled by `entrypoint.sh`:
```sh
uv run alembic upgrade head
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```
`exec` replaces the shell with uvicorn, making uvicorn PID 1 so Docker SIGTERM is delivered directly (clean shutdown, no orphan processes).

Alembic runs migrations before uvicorn starts on every container boot — idempotent and safe; skips if schema is already current.

`.dockerignore` excludes `tests/`, `.venv/`, `__pycache__/`, `*.pyc`, `.env` to keep the image layer clean.

---

## Recent Changes

- [2026-05-15] Dockerized service — added `entrypoint.sh` (Alembic migrations + `exec uvicorn` for PID 1), refactored Dockerfile from CMD shell string to `ENTRYPOINT ["./entrypoint.sh"]`, added `.dockerignore`
- [2026-04-30] Implemented privacy service v0.1.0: FastAPI + SQLAlchemy async + asyncpg + Alembic; consent table (upsert) and audit_log (append-only, monthly RANGE partitioning, 3-month TTL via startup partition manager); 3 endpoints wired; HMAC-SHA256 pseudonymization; OpenAPI spec enriched with Field descriptions and exported; 10 unit tests + 10 integration tests (skip without infra)

---

## Flags

---

## Interfaces

### Exposes
- `PATCH /privacy/consent/{user_id}` — grant or revoke personalization consent; pseudonymizes raw user_id; atomic upsert + audit log; returns updated record
- `GET /privacy/audit/{user_id}` — retrieve consent change history (newest-first); pseudonymizes raw user_id; returns entries within retention window
- `GET /internal/consent/check/{pseudo_id}` — consent gate called by inference-api before every feature fetch; accepts pseudo_id directly; PK lookup only; returns `{consent_granted: bool}`; opt-in default (missing record → false)

### Consumes
- Postgres `privacy` database: `consent` table (read/write), `audit_log` partitioned table (append + partition DDL at startup)

---

## Do Not
- Do not revert `audit_log.id` from `GENERATED ALWAYS AS IDENTITY` to `SERIAL` — SERIAL sequences are not inherited by child partitions (see ADR 0006)
- Do not add a unique constraint on `audit_log` that excludes `timestamp` — PostgreSQL rejects it on a partitioned table
- Do not use `Base.metadata.create_all()` for `audit_log` schema setup — use the Alembic migration or raw DDL; SQLAlchemy cannot emit `PARTITION BY RANGE`
- Do not cache consent state in inference-api — always check privacy service before every feature fetch (no stale cache)
- Do not pseudonymize `pseudo_id` again in the internal check endpoint — it receives an already-pseudonymized ID from inference-api; double-hashing would miss every record
- Do not log raw user_id in audit entries — pseudo_user_id only
