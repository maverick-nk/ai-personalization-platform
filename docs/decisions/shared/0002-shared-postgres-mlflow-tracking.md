# 0002. Shared Postgres Instance for MLflow Tracking Backend

**Date:** 2026-04-12  
**Status:** Accepted  
**Service:** shared (infra)  
**Decided by:** user

---

## Context

MLflow requires a tracking backend to persist experiment runs, model versions, and metrics across container restarts. Its default backend is SQLite, which writes to a file inside the container — data is lost whenever the container is recreated. Postgres is already in the stack for the privacy service, making it a natural candidate for MLflow's backend without adding another container.

---

## Decision

MLflow uses a dedicated `mlflow` database on the shared Postgres instance. The privacy service uses a separate `privacy` database on the same instance. Both databases are created automatically at first startup via an init script.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| SQLite (MLflow default) | Data lost on container restart; not suitable even for local dev where experiment history matters |
| Dedicated Postgres container for MLflow | Adds a second Postgres process with no benefit — two unrelated schemas on one instance is standard practice |
| File-based artifact store only (no tracking DB) | MLflow needs the tracking store for model registry; artifact-only mode doesn't support versioning or stage promotion |

---

## Consequences

**Gets easier:**
- Model experiment history and registry state survive `docker compose restart`
- One fewer container; single Postgres health check covers both concerns
- `scripts/reset-infra.sh` wipes both databases cleanly via a single volume deletion

**Gets harder / trade-offs accepted:**
- Two unrelated concerns (consent data + ML tracking) share a single DB process — a noisy-neighbour risk that is acceptable at local dev scale
- `init-multiple-dbs.sh` must be kept in sync if new databases are added to the shared instance

**Constraints this introduces:**
- MLflow and privacy service must use separate connection strings pointing to their respective databases (`mlflow` vs `privacy`)
- Do not co-locate application data from other services on this Postgres instance without updating `POSTGRES_MULTIPLE_DATABASES` in docker-compose and the init script

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Durability and crash recovery | Ch 7 — Transactions | Postgres write-ahead log (WAL) ensures MLflow experiment data survives crashes; SQLite's fsync behaviour offers weaker guarantees under container restarts |
| Multi-tenancy via logical database separation | Ch 1 — Reliable, Scalable, Maintainable Systems | Two logical databases on one Postgres instance isolate schemas and permissions without the overhead of separate processes |
| Storage engine trade-offs | Ch 3 — Storage and Retrieval | SQLite is an embedded B-tree store optimised for single-writer local access; Postgres is a client-server store designed for concurrent access — the latter fits MLflow's concurrent read/write pattern better |

---

## Related

- Supersedes: none
- Related: ADR 0001 (same docker-compose bootstrap)
- CONTEXT.md flag added: no (infra only — privacy and model-training CONTEXT.md files will reference their respective DB connection strings when those services are implemented)
