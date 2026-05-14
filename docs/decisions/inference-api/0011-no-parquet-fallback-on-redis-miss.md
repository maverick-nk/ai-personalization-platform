# 0011. No Parquet Fallback on Redis Miss — Trending Feed as Cold-Start Response

**Date:** 2026-05-13  
**Status:** Accepted  
**Service:** inference-api  
**Decided by:** user

---

## Context

When a user's feature vector is not found in Redis (`HGETALL` returns empty), the inference-api must decide how to respond. The user's features may exist in the Parquet offline store — the feature pipeline writes both Redis and Parquet — so a point-lookup against Parquet is technically possible. The question is whether doing so preserves the 50ms end-to-end SLO and is architecturally appropriate.

---

## Decision

On Redis miss, the inference-api immediately returns the non-personalized trending fallback. It does not query Parquet. The Redis miss is classified as a cold-start condition regardless of whether Parquet may contain the user's features.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Synchronous Parquet point-lookup on Redis miss | Parquet is a columnar batch store optimised for analytical scans, not point lookups; a synchronous read on the hot path would add hundreds of milliseconds and violate the 50ms SLO |
| Async Parquet lookup with a tight timeout | Even with a 10ms timeout, Parquet file I/O is not designed for per-request access patterns; this adds complexity and a new failure mode (timeout → fallback anyway) for marginal latency budget |
| Pre-warm Redis from Parquet at startup for known users | Shifts the problem to startup time, creates a dependency between the inference-api and Parquet partition layout, and still leaves a window where new users are cold-start until the pipeline updates Redis |
| Accept a slower SLO for users with Parquet features but no Redis entry | The SLO is a system-wide contract, not per-user; relaxing it for a subset of users is not operationally measurable and sets a precedent for creep |

---

## Consequences

**Gets easier:**
- Redis miss handling is a single code path: return trending fallback, set `fallback_reason: cold_start`, done
- No Parquet dependency in the inference-api — it reads only Redis and MLflow; the offline store stays strictly a training-side concern
- The 50ms SLO is unconditional — no tail latency risk from Parquet I/O on the hot path

**Gets harder / trade-offs accepted:**
- A user whose features are in Parquet but whose Redis key has expired (TTL elapsed, pipeline lag) will receive the trending fallback rather than personalized content, even though their feature history exists
- Cold-start window is defined by the feature pipeline's Redis write latency (~2s), not by feature history age; a user with 6 months of Parquet history re-enters cold-start if their Redis key expires
- Monitoring must differentiate true cold-start (no history) from stale-Redis cold-start (history exists, key expired) — the `fallback_reason: cold_start` field alone cannot distinguish them

**Constraints this introduces:**
- Do not add synchronous Parquet point-lookups to the inference-api hot path — Parquet is a batch scan store; per-request access violates the latency contract
- Parquet remains a training-only data source; the feature pipeline is the sole authority for writing user features to Redis

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Online vs offline store separation | Ch 12 — The Future of Data Systems | Redis is the online store (low-latency point lookups); Parquet is the offline store (high-throughput batch scans); mixing access patterns across the boundary breaks the latency guarantee of the online store |
| Cache-aside pattern | Ch 5 — Replication | The inference-api checks Redis first and does not populate the cache on miss — cache population is the feature pipeline's responsibility; the inference-api falls back rather than bypassing the cache layer |
| Tail latency design | Ch 1 — Reliable, Scalable, Maintainable Applications | SLOs are defined at the tail (p95/p99), not the median; a Parquet lookup that is fast at p50 but slow at p99 still breaks the SLO for the users who matter most operationally |

---

## Related

- Related: ADR 0007 — Fail Closed When Privacy Service Is Unreachable (same graceful-degradation philosophy: all non-personalized paths return trending, never an error)
- Related: ADR 0005 — At-Least-Once Checkpointing (feature pipeline writes to both Redis and Parquet; Redis is the inference-time source of truth)
- CONTEXT.md flag added: yes — inference-api `## Do Not`: do not add Parquet point-lookups on Redis miss
