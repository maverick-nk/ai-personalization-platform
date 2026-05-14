# 0012. In-Process asyncio.Lock Model Hot-Swap

**Date:** 2026-05-14  
**Status:** Accepted — with known gap  
**Service:** inference-api  
**Decided by:** user

---

## Context

The inference-api must serve recommendations continuously while the model registry is updated with new versions. A naive approach — restarting the process on a new model version — causes downtime and drops in-flight requests. The service needs a mechanism to load a new model version and swap it into the serving path without interrupting requests. In a single-process async application, any swap that is not atomic risks a request reading a half-loaded model mid-swap.

---

## Decision

Model hot-swap is implemented entirely in-process. A background `asyncio` task polls MLflow every N seconds (configurable via `INFERENCE_MLFLOW_POLL_INTERVAL`). When a new model version is detected under the configured alias, it loads the artifact via `asyncio.to_thread()` (offloading blocking MLflow I/O off the event loop), then acquires `asyncio.Lock` to atomically update the `_current` model reference. Request handlers acquire the same lock before reading `_current`, ensuring they always see a fully-loaded model and never a partially-swapped one.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Process restart on new model version | Causes downtime and drops in-flight requests; defeats the purpose of hot-swap |
| Blue-green pod swap at Kubernetes level | Valid for production — all traffic shifts to new pods atomically — but requires orchestration infrastructure not yet present (Phase 2); overkill for Phase 1 local development |
| Shared external swap signal via Redis pub/sub | Adds a new cross-replica coordination dependency; all replicas swap simultaneously, which eliminates version skew but introduces a coordination failure mode (what if one replica misses the signal?) |
| No hot-swap — rolling pod restarts via Kubernetes | Correct production pattern, but requires Kubernetes (Phase 2); also causes brief per-pod downtime during restart |

---

## Consequences

**Gets easier:**
- Within a single replica, model swaps are zero-downtime — no request is ever served by a partially-loaded model
- The lock also protects against concurrent poll iterations: two poll cycles cannot race to swap `_current` simultaneously
- No external coordination infrastructure required — the entire mechanism is self-contained in `model_store.py`

**Gets harder / trade-offs accepted:**
- **Known gap — multi-replica version skew:** In a multi-replica deployment (e.g. Kubernetes with N pods), each replica polls MLflow independently and swaps at a different time. During the rollout window, requests load-balanced across replicas may be served by different model versions simultaneously. The length of this skew window is directly proportional to the poll interval — a 60s poll interval means up to 60s of version skew across replicas.
- **Polling interval is a lever with two competing concerns:** A shorter interval reduces the version skew window but increases MLflow load and artifact download frequency. A longer interval reduces MLflow load but widens the window during which replicas diverge.
- **No swap signal to callers:** The response includes `model_version` but there is no mechanism to notify callers that a swap occurred mid-session — a user's recommendations may shift between two requests if a swap happens between them.

**Constraints this introduces:**
- Poll interval must be set explicitly — defaulting to a long interval in production widens the multi-replica skew window unacceptably
- Do not remove the `asyncio.Lock` from `get()` — even though the asyncio model is single-threaded, `get()` contains an `await` point; without the lock a concurrent call could be scheduled between a version-check and a set in `_poll_loop`

---

## Known Gap — Deployment Strategy Exploration

The multi-replica skew problem has several candidate mitigations worth evaluating before Phase 2:

| Strategy | How it works | Trade-off |
|---|---|---|
| Shorten poll interval during deployments | Deployment tooling (CI/CD hook or Kubernetes lifecycle hook) reduces `INFERENCE_MLFLOW_POLL_INTERVAL` before promoting a new model alias, then restores it after all replicas have swapped | Requires deployment pipeline awareness of the inference-api poll interval; adds operational complexity |
| Kubernetes rolling update with readiness probe | Deploy new model version as a new pod image (model baked in or fetched at startup); Kubernetes drains old pods only after new ones pass readiness | Eliminates the polling mechanism entirely for major model updates; polling becomes useful only for minor updates between deployments |
| Coordinated alias promotion window | MLflow alias is promoted only during a defined low-traffic window; poll interval is short enough that all replicas pick it up before traffic ramps | Operationally simple but restricts when models can be promoted; incompatible with continuous deployment of models |
| Sticky sessions during swap window | Load balancer routes a user to the same replica for the duration of a session | Prevents within-session version skew but not across-session; adds load balancer complexity |

No decision made yet. This should be revisited when Kubernetes infrastructure is introduced in Phase 2.

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Atomic pointer swap / in-process versioning | Ch 1 — Reliable, Scalable, Maintainable Applications | asyncio.Lock makes the version-check-and-assign atomic within one event loop — no request sees a partially-swapped state |
| Consistency vs availability under replica divergence | Ch 9 — Consistency and Consensus | Multiple replicas independently polling and swapping is an eventually-consistent system: all replicas converge on the new version, but there is a window of divergence; the width of that window is the poll interval |
| Replication lag analogy | Ch 5 — Replication | The per-replica swap delay is structurally analogous to replication lag — the replica is "behind" the authoritative state (MLflow alias) by up to one poll interval |

---

## Related

- Related: ADR 0009 — Alias-Only Model Promotion Gate (MLflow alias is the trigger for hot-swap; the alias promotion decision shapes how hot-swap behaves)
- Related: ADR 0010 — Python + FastAPI REST over Go + gRPC (single-process asyncio model enables in-process locking; a Go multi-threaded model would require a mutex instead)
- CONTEXT.md flag added: yes — inference-api `## Do Not`: do not remove asyncio.Lock from model_store.get()
