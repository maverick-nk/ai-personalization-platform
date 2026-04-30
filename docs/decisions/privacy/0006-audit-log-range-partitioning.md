# 0006. Audit Log Range Partitioning with Monthly TTL

**Date:** 2026-04-29  
**Status:** Accepted  
**Service:** privacy  
**Decided by:** user

---

## Context

The `audit_log` table is append-only — one row per GRANT or REVOKE per user — and grows without bound. The `consent` table has no bloat risk (one row per user, updated in place). Any TTL enforcement on audit history needs to be efficient at scale: millions of users each changing consent a handful of times produces a table that cannot be cleaned up cheaply with row-level DELETE operations.

A secondary question surfaced during design: what happens to users who have been inactive for more than the retention window? The answer matters for both compliance reasoning and implementation correctness.

---

## Decision

Partition `audit_log` by `timestamp` using PostgreSQL RANGE partitioning with monthly child tables. Retain 3 months of history (configurable via `AUDIT_RETENTION_MONTHS`). Monthly partition creation and TTL enforcement run idempotently at service startup via `app/partitions.py` — no external cron job required at this scale.

The consent table is **not** partitioned. Audit TTL applies only to change history, never to consent state. An inactive user's current consent is always preserved in the consent table; `consent.updated_at` acts as a single-record audit trail for the most recent change.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Plain `DELETE WHERE timestamp < cutoff` + cron | O(N rows): holds row-level locks, generates WAL proportional to deleted rows, requires VACUUM to reclaim space — unacceptable at scale |
| MongoDB (document store) | Audit entries are flat records; document model adds no semantic value. Write path is not faster than Postgres for simple inserts. Loses the single-transaction commit between `consent` and `audit_log` — a hard compliance requirement |
| Cassandra | Excellent write scalability and per-row TTL, but splits the consent + audit write across two stores, removing the atomicity guarantee. Heavyweight infrastructure for a 2-table service; only worthwhile if audit became a dedicated microservice |
| Hot/cold tiering (Postgres → Parquet/S3) | Correct for production (see industry note below) — rejected here because it adds an archival pipeline, a cold-read query router, and cold storage infrastructure that exceeds the scope of this learning project |

---

## Consequences

**Gets easier:**
- TTL enforcement: `DROP TABLE audit_log_YYYY_MM` is O(1) DDL — no locks on the parent table, no WAL bloat, instant regardless of row count
- Write performance improves over time: the current month's partition is smaller and more cache-friendly than a single unbounded table
- Future capacity planning: partition sizes are predictable and inspectable directly in `pg_class`

**Gets harder / trade-offs accepted:**
- `SERIAL` does not propagate to child partitions in PostgreSQL — must use `GENERATED ALWAYS AS IDENTITY` instead; this is a schema constraint future migrations must preserve
- PostgreSQL requires the partition key (`timestamp`) to be part of every unique/PK constraint — the primary key is composite `(id, timestamp)` rather than a simple serial
- SQLAlchemy has no ORM-level API for `PARTITION BY RANGE` — the migration uses `op.execute(raw SQL)` rather than the standard `op.create_table()`, and `Base.metadata.create_all()` cannot replicate the schema (integration tests create the schema directly)
- Queries on `audit_log` without a timestamp filter scan all active partitions (one index scan per partition). Acceptable because audit reads are infrequent (compliance checks, debugging) and not in the hot path. The internal consent-check endpoint hits the `consent` table — zero impact from partitioning

**Constraints this introduces:**
- Do not revert `audit_log.id` from `GENERATED ALWAYS AS IDENTITY` to `SERIAL` — SERIAL sequences are not inherited by child partitions
- Do not add a unique constraint on `audit_log` that excludes `timestamp` — PostgreSQL will reject it on a partitioned table
- Do not use `Base.metadata.create_all()` for schema setup in contexts where the partitioned table must exist — use the Alembic migration or raw DDL

---

## Inactive Users

Partitioning and TTL apply to audit **history** only. The `consent` table is never purged. After 3 months, the audit entries for an inactive user are dropped, but their current consent state (`consent_granted`, `updated_at`) is fully preserved. Personalization is gated on the consent table, not the audit log — functionality is unaffected.

---

## Industry-Level Note

This project uses `DROP TABLE` on expired partitions for simplicity. A production compliance system should **archive rather than delete**:

- **CCPA** (California): consumers can request data access for the past 12 months — audit logs must survive that window
- **GDPR Article 7(1)**: controllers must be able to demonstrate consent was given for as long as data is processed on that basis — the audit log proves when consent was granted or revoked
- **Recommended production pattern:**
  - Hot tier: 12 months in Postgres (fast operational reads)
  - Cold tier: monthly Parquet files on S3/GCS, queryable via Athena or BigQuery (cheap storage, slow compliance reads)
  - Archival job runs before DROP — never delete without writing to cold first
- The `AUDIT_RETENTION_MONTHS` config is designed to be extended; the partition-drop logic in `app/partitions.py` can be replaced with an archive-then-drop step without changing the partition structure

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Range partitioning by key | Ch 6 — Partitioning | Monthly child tables partition `audit_log` by `timestamp`; expired partitions are dropped in O(1) DDL rather than O(N) row-level DELETE |
| Write-optimised append-only logs | Ch 3 — Storage and Retrieval | Audit log is an append-only structure — writes always go to the current month's partition (the "active segment"), analogous to LSM-tree memtable flushes |
| Derived data vs event log | Ch 12 — The Future of Data Systems | `audit_log` is the immutable event log (source of truth for history); `consent` table is the derived materialised view of current state — the two serve different query patterns and have different retention needs |

---

## Related

- Supersedes: none
- Related: ADR 0002 — Shared Postgres Instance (privacy and MLflow share one Postgres; audit_log partitioning must not impact MLflow's I/O budget)
- CONTEXT.md flag added: yes (see below)
