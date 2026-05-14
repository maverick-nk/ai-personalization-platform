# System Design Concepts — inference-api

> Quiz log for the `inference-api` service.
> Reference: "Designing Data-Intensive Applications" — Martin Kleppmann
> Concepts scored ≥ 80% are deprioritised in future sessions.

---

## Concept Coverage

| Concept | Times Tested | Best Score | Last Tested |
|---|---|---|---|
| Fail-closed vs fail-open | 1 | 100% | 2026-05-13 |
| Timeouts in distributed systems | 1 | 100% | 2026-05-13 |
| asyncio.Lock and concurrency model | 1 | 100% | 2026-05-13 |
| Cache-aside pattern | 1 | 100% | 2026-05-13 |
| Graceful degradation | 1 | 100% | 2026-05-13 |
| REST vs gRPC trade-offs | 1 | 100% | 2026-05-13 |
| Training/serving skew prevention | 1 | 100% | 2026-05-13 |
| Blocking I/O in async systems | 1 | 100% | 2026-05-13 |
| Latency budget allocation | 1 | 100% | 2026-05-13 |
| Pseudonymization consistency | 1 | 100% | 2026-05-13 |
| Schema design — field presence as signal | 1 | 100% | 2026-05-13 |
| Strategy pattern / scorer factory | 1 | 100% | 2026-05-13 |

---

## Sessions

### 2026-05-13 · Full inference API — consent check → Redis feature fetch → scorer factory → Top-N ranking; asyncio hot-swap; fail-closed privacy; cold-start fallback; REST over gRPC

**Score: 12/12 (100%)**
**Concepts tested:** Fail-closed/fail-open, Timeouts in distributed systems, asyncio.Lock and concurrency model, Cache-aside pattern, Graceful degradation, REST vs gRPC trade-offs, Training/serving skew prevention, Blocking I/O in async systems, Latency budget allocation, Pseudonymization consistency, Schema design (field presence as signal), Strategy pattern / scorer factory

---

**Q1 · [Trade-off] · Fail-closed vs fail-open**
The privacy client returns False (consent denied) whenever the privacy service is unreachable — timeout, connection refused, or 5xx. What is the primary reason to prefer fail-closed over fail-open here?

- A) Fail-closed avoids network round-trips on error paths, reducing inference latency
- B) Fail-closed ensures a user who has revoked consent cannot receive personalized content even during a privacy service outage
- C) Fail-open would require caching consent state, which is complex to implement
- D) Fail-closed prevents the privacy service from becoming a single point of failure

**User answered:** B · **Correct:** B · ✓

> Fail-closed treats silence from the consent gate as denial — the restrictive safe default. If the inference API treated unreachability as "granted," a user who revoked consent during an outage would continue receiving personalized content. That's a compliance failure, not just a technical one. The trending fallback is the universal safe response for any non-personalized case, so failing closed costs nothing in terms of response validity — only in personalization quality.
> DDIA ref: Chapter 8 — Trouble with Distributed Systems (fail-safe defaults)

---

**Q2 · [Scenario] · Timeouts in distributed systems**
The privacy client has a 3ms timeout. The privacy service responds in 8ms. What happens to the request?

- A) The request succeeds — 8ms is within the 50ms SLO
- B) The privacy client raises a timeout exception; the request fails closed and returns the trending fallback within the 50ms budget
- C) The Redis fetch is skipped to compensate, and the model scores with default feature values
- D) FastAPI returns a 504 Gateway Timeout to the caller

**User answered:** B · **Correct:** B · ✓

> The 3ms timeout fires before the 8ms response arrives. The handler immediately returns the trending fallback — no Redis fetch or model inference needed. Total request time stays well within 50ms. This is why the timeout is set tightly: an unbounded wait would blow the SLO for every request when privacy is slow.
> DDIA ref: Chapter 8 — Trouble with Distributed Systems

---

**Q3 · [Concept] · asyncio.Lock and concurrency model**
get() and the swap logic in _poll_loop both acquire asyncio.Lock. What does the lock guarantee that the single-threaded asyncio model alone does not?

- A) It prevents thread contention from asyncio.to_thread() accessing _current concurrently
- B) It makes the version-check and assignment in _poll_loop atomic across the event loop — without it, a get() call could be scheduled between the check and the set
- C) It serializes model downloads so two concurrent poll iterations never call MLflow simultaneously
- D) It guarantees LoadedModel construction is atomic under the GIL

**User answered:** B · **Correct:** B · ✓

> The `async with self._lock` in get() is itself an await point. If _poll_loop holds the lock during its version-check + swap block, any concurrent get() call suspends at the lock boundary until the swap completes — ensuring a reader always sees a complete model. The lock also signals intent: this is a critical section protected against future changes that add await points.
> DDIA ref: Chapter 7 — Transactions (serializability)

---

**Q4 · [Concept] · Cache-aside pattern**
On a Redis miss the inference API returns the trending fallback instead of reading from Parquet. Which caching pattern is this, and what is the deliberate trade-off?

- A) Write-through — the API writes missing features to Redis on miss
- B) Cache-aside — the application checks Redis first; on miss falls back to a non-personalized response rather than reading from the slower Parquet store
- C) Read-through — the cache automatically fetches from Parquet on miss
- D) Write-behind — a miss means the async write hasn't landed yet, so the API retries

**User answered:** B · **Correct:** B · ✓

> Cache-aside means the application owns cache population decisions. The trade-off is deliberate: Parquet is a batch store optimised for analytical scans, not point lookups — a synchronous read would add hundreds of milliseconds and violate the 50ms SLO. Cold-start users get a trending fallback immediately instead.
> DDIA ref: Chapter 5 — Replication / Chapter 12 — Future of Data Systems

---

**Q5 · [Trade-off] · Graceful degradation**
The inference API returns 200 (trending feed) instead of 5xx across three failure scenarios. What principle does this implement and what trade-off is accepted?

- A) Circuit breaker — stops calling failing dependencies after a threshold
- B) Graceful degradation — always returns a usable response by falling back to a safe default, trading response quality for availability
- C) Bulkhead isolation — each failure mode handled in a separate thread pool
- D) Idempotency — trending fallback can be safely retried unlike personalized responses

**User answered:** B · **Correct:** B · ✓

> Graceful degradation means providing some value even when components fail. The trade-off accepted is observability: a caller gets 200 OK regardless of failure mode. The `personalized: false` and `fallback_reason` fields surface degradation without breaking the caller's experience.
> DDIA ref: Chapter 1 — Reliable, Scalable, Maintainable Applications

---

**Q6 · [Trade-off] · REST vs gRPC**
The original plan specified Go + gRPC. Why was the latency advantage of gRPC insufficient to justify it here?

- A) gRPC is not supported in Python
- B) HTTP/2 multiplexing only helps with many concurrent connections from a single client
- C) A gRPC-only API would require either a generated gRPC client in pytest or a REST-to-gRPC gateway — adding a second protocol surface and negating the latency advantage
- D) FastAPI is faster than gRPC because it uses async I/O natively

**User answered:** C · **Correct:** C · ✓

> Protobuf encoding savings (10–20% at the payload level) are dwarfed by Redis and model inference time. The decisive factor was test harness compatibility: httpx speaks HTTP natively, not gRPC framing. Maintaining two protocol surfaces introduces a class of bugs where gateway behaviour differs from the gRPC endpoint under edge cases.
> DDIA ref: Chapter 4 — Encoding and Evolution

---

**Q7 · [Concept] · Training/serving skew prevention**
The scorer factory reads model_type and the feature schema from the same MLflow run ID. What failure mode does this prevent?

- A) Model versioning drift — guarantees scorer and feature contract were validated together
- B) Feature store corruption — prevents the feature pipeline from writing unexpected fields
- C) Hot-swap failures — the lock prevents a partially-loaded model from being served
- D) Cold-start bias — ensures cold-start users receive genre-appropriate trending content

**User answered:** A · **Correct:** A · ✓

> Training/serving skew is a silent failure: the model at inference sees different features than it was trained on, producing wrong predictions with no error signal. Tying scorer and schema to the same run ID guarantees they are always in sync. The run ID is the binding key that makes the pairing tamper-proof.
> DDIA ref: Chapter 4 — Encoding and Evolution (schema evolution and reader/writer agreement)

---

**Q8 · [Concept] · Blocking I/O in async systems**
Why is asyncio.to_thread used for self._load() instead of calling it directly as a coroutine?

- A) self._load() performs synchronous blocking I/O that would stall the entire event loop if called directly, preventing other requests from being served
- B) asyncio.to_thread releases the GIL for true parallel execution with request handlers
- C) MLflow's Python client requires thread-local state that coroutines can't maintain
- D) asyncio.to_thread automatically retries on transient network errors

**User answered:** A · **Correct:** A · ✓

> asyncio is cooperative — a coroutine runs until it hits an await point. mlflow.artifacts.download_artifacts() and file reads are synchronous blocking calls with no await points. Calling them directly would freeze the event loop for the entire download duration. asyncio.to_thread() offloads to a ThreadPoolExecutor, keeping the event loop free for requests.
> DDIA ref: Chapter 11 — Stream Processing (event-driven systems must never block the main loop)

---

**Q9 · [Scenario] · Latency budget allocation**
A new requirement adds a remote catalog refresh call (typically 2ms, p99 40ms) on every request. What is the correct response?

- A) Accept it — 2ms typical keeps p50 well under 50ms
- B) Cache the catalog in app.state at startup and refresh in a background task, keeping it off the hot path
- C) Add the call with a 5ms timeout to cap p99 spikes
- D) Move the catalog call before the privacy check to run in parallel with pseudonymization

**User answered:** B · **Correct:** B · ✓

> SLOs are defined at the tail, not the average. A 40ms p99 spike consumes 80% of the entire budget. The content catalog changes infrequently; a background refresh task (same pattern as ModelStore) gives requests a pre-warmed local copy with zero network cost. A 5ms timeout only partially helps — it still adds 5ms to every p99 request and returns stale data silently when it fires.
> DDIA ref: Chapter 1 — Reliable, Scalable, Maintainable Applications (percentile latency design)

---

**Q10 · [Concept] · Pseudonymization consistency**
Why must the inference API use the same HMAC secret as event-ingestion?

- A) Without the same pseudo_id, consent records and Redis keys written by upstream services won't be found by the inference API
- B) The same key allows the inference API to reverse the pseudonym for debugging
- C) HMAC consistency prevents replay attacks via guessed pseudo_ids
- D) The same pseudo_id aligns Redis TTLs between pipeline writes and inference reads

**User answered:** A · **Correct:** A · ✓

> The pseudo_id is the single shared identifier threading through the entire system. A different secret produces a different pseudo_id — Redis keys won't exist (cold start for every user) and consent records won't be found (denied for every user). The HMAC secret is a shared credential; the one-way property is what makes pseudonymization a privacy guarantee.
> DDIA ref: Chapter 12 — The Future of Data Systems (data privacy by design)

---

**Q11 · [Trade-off] · Schema design — field presence as signal**
Why use response_model_exclude_none=True rather than always including all fields with null?

- A) Reduces JSON serialization time on the critical path
- B) Field presence carries semantic meaning — absent score means "not scored", absent model_version means "model not invoked" — rather than requiring clients to distinguish null-as-absent from null-as-error
- C) Prevents client libraries from deserializing null as default types like 0.0
- D) Reduces payload size, meaningfully improving throughput at high volume

**User answered:** B · **Correct:** B · ✓

> The key benefit is semantic clarity. A score field present with null is ambiguous; a score field that is simply absent means unambiguously "this item was not scored." The schema encodes business rules structurally rather than via runtime null-checking conventions that can drift.
> DDIA ref: Chapter 4 — Encoding and Evolution (make illegal states unrepresentable)

---

**Q12 · [Concept] · Strategy pattern / scorer factory**
scorers/factory.py maps model_type → BaseScorer subclass. model_store.py and scorer.py depend only on BaseScorer.predict_proba(). Which design pattern is this?

- A) Observer — factory notifies registered scorers of new model versions
- B) Strategy — scoring algorithm encapsulated behind a common interface, allowing implementations to swap without changes outside scorers/
- C) Factory method — factory creates model artifacts at training time
- D) Adapter — factory wraps each ML framework's native predict API

**User answered:** B · **Correct:** B · ✓

> The Strategy pattern encapsulates a family of algorithms behind a shared interface and makes them interchangeable. Neither model_store.py nor scorer.py imports from lightgbm. Adding XGBoost requires one new file and one registry entry — nothing else changes. This mirrors BaseTrainer on the training side, giving both pipelines the same extension seam at the algorithm boundary.
> DDIA ref: Chapter 2 — Data Models and Query Languages (abstraction hides implementation details behind clean interfaces)

---
