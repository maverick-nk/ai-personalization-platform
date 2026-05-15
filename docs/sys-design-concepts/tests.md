# System Design Concepts — tests

> Quiz log for the `tests` (e2e test harness) service.
> Reference: "Designing Data-Intensive Applications" — Martin Kleppmann
> Concepts scored ≥ 80% are deprioritised in future sessions.

---

## Concept Coverage

| Concept | Times Tested | Best Score | Last Tested |
|---|---|---|---|
| Polling with deadline vs fixed sleep | 1 | 100% | 2026-05-14 |
| Skip gate strategy — env var vs health probing | 1 | 100% | 2026-05-14 |
| Session vs function fixture scope | 1 | 100% | 2026-05-14 |
| Test isolation without teardown | 1 | 100% | 2026-05-14 |
| p95 as the SLO metric | 1 | 100% | 2026-05-14 |
| Sync client in async test context | 1 | 100% | 2026-05-14 |
| Standalone project with duplicated helper | 1 | 100% | 2026-05-14 |

---

## Sessions

### 2026-05-14 · E2E test harness infrastructure — conftest, clients, helpers, TESTING.md

**Score: 7/7 (100%)**
**Concepts tested:** Polling with deadline vs fixed sleep, Skip gate strategy, Session vs function fixture scope, Test isolation without teardown, p95 as the SLO metric, Sync client in async context, Standalone project with duplicated helper

---

**Q1 · [Trade-off] · Polling with deadline vs fixed sleep**
The `wait_for_redis_key` helper uses a `time.monotonic() + timeout` deadline loop rather than a fixed `time.sleep(5)` before checking Redis. What does this design guarantee that `time.sleep(5)` does not?

- A) It guarantees the test fails immediately when Redis is unreachable, because the exception propagates on the first poll attempt
- B) It returns as soon as the key appears, so tests that pass do not pay the full wait time — and it returns a clear `None` on genuine timeout rather than passing with stale data
- C) It prevents the event loop from blocking during the wait because `time.monotonic()` is non-blocking
- D) It retries the Redis connection on network errors, whereas `time.sleep(5)` would leave a broken connection open

**User answered:** B · **Correct:** B · ✓

> A fixed `time.sleep(5)` always waits the full 5 seconds, making the test suite slow even when Redis writes land in 300ms. The deadline loop checks every 100ms and returns the moment the key exists — fast tests stay fast. On failure it returns `None`, which the test converts into a clear assertion failure with a message. A fixed sleep with an immediate check after could also return stale data if the key happened to exist from a previous test run; the polling loop is checking for the *current* write to arrive.
> DDIA ref: Chapter 8 — Trouble with Distributed Systems (bounded wait times, avoiding unbounded blocking)

---

**Q2 · [Trade-off] · Skip gate strategy — env var vs health probing**
The `conftest.py` skip gate checks `PSEUDONYMIZE_SECRET` rather than probing `/health` on each service at collection time. What is the primary reason for this choice?

- A) Health check probing at collection time adds latency to every test run, even when all services are healthy
- B) `PSEUDONYMIZE_SECRET` is a hard requirement shared by all services — if it is absent, no test can produce correct HMAC digests and every test is meaningless regardless of service reachability; a missing env var is also a cleaner operator signal than a network error at collection time
- C) FastAPI's `/health` endpoint is not guaranteed to return 200 immediately after startup, making health probing unreliable
- D) Health check probing requires async fixtures, which are incompatible with `pytestmark.skipif`

**User answered:** B · **Correct:** B · ✓

> `PSEUDONYMIZE_SECRET` is the single shared HMAC key that threads through every service — event-ingestion pseudonymizes before Kafka publish, inference-api computes `pseudo_id` for Redis lookup, privacy stores `user_pseudo_id` in Postgres. If the secret is absent, a test could POST a watch event and look up the wrong Redis key (different digest), making it impossible to tell whether a failure is a real bug or a configuration error. The env var gate catches this before any service is called. Health check probing, by contrast, only tells you a port is reachable — not that the services share the same secret.
> DDIA ref: Chapter 12 — The Future of Data Systems (end-to-end correctness; a partial configuration is worse than no configuration)

---

**Q3 · [Concept] · Session vs function fixture scope**
`event_client`, `inference_client`, and `privacy_client` are session-scoped. `unique_user_id` is function-scoped. What is the correct reason for this difference?

- A) Session-scoped clients share a single TCP connection pool across all tests, reducing connection overhead; function-scoped user IDs give each test a fresh identity with no teardown logic, keeping tests independent at the data level
- B) Session-scoped fixtures are required for async fixtures in pytest-asyncio; function-scoped fixtures cannot be async
- C) HTTP clients maintain per-user state that would bleed between tests if session-scoped; function scope is needed to isolate that state
- D) Function-scoped clients would open too many concurrent connections to the service, exceeding the server's connection limit

**User answered:** A · **Correct:** A · ✓

> `httpx.AsyncClient` maintains an internal connection pool — creating one per test would repeatedly open and close TCP connections to the same services, adding overhead that accumulates across dozens of tests. The clients themselves hold no per-user state (they are thin wrappers around an HTTP client), so sharing them across tests is safe. `unique_user_id` is function-scoped for the opposite reason: test independence lives at the data layer, not the client layer. Each test gets a fresh UUID-based ID whose HMAC digest produces a unique Redis key and consent record, so no test can accidentally read or pollute another test's data — without any explicit cleanup.
> DDIA ref: Chapter 1 — Reliable, Scalable, Maintainable Applications (operability: keeping tests fast and deterministic)

---

**Q4 · [Trade-off] · Test isolation without teardown**
Tests generate `e2e-<12 hex chars>` user IDs per test with no cleanup of Redis keys or Postgres consent records after the run. What property of this design makes cleanup unnecessary?

- A) The test framework automatically deletes Redis keys when the session fixture is torn down
- B) HMAC is deterministic — the same user ID always produces the same `pseudo_id`, so the next test run simply overwrites the previous run's Redis key
- C) Each test's `pseudo_id` is derived from a cryptographically unique UUID, so orphaned Redis keys expire via TTL and are effectively invisible to other users or tests — the digest cannot be guessed from outside, eliminating cross-test interference
- D) Redis is flushed at the start of each test session by a session-scoped autouse fixture

**User answered:** C · **Correct:** C · ✓

> The `e2e-<uuid>` prefix produces a unique raw `user_id` per test invocation. HMAC-SHA256 of a unique input produces a unique digest — the resulting Redis key `user:{pseudo_id}:features` and the Postgres `user_pseudo_id` are collision-free across all past and future test runs. An attacker or another test would need to know the original UUID *and* the shared HMAC secret to compute the same key — which is impossible without both. Redis TTL handles eventual cleanup automatically (1 hour by default from the feature pipeline). Option B describes the opposite scenario: determinism is what makes HMAC *useful for lookups across services*, not a property that creates isolation.
> DDIA ref: Chapter 12 — The Future of Data Systems (data privacy by design; one-way functions as isolation boundaries)

---

**Q5 · [Trade-off] · p95 as the SLO metric**
`assert_p95` is the only public latency assertion in `helpers/latency.py` — there is no `assert_mean`. Why must the 50ms SLO be defined at p95 rather than the mean?

- A) p95 is simpler to compute than the mean without importing numpy
- B) A mean that looks acceptable can hide a long tail where 5% of users receive unacceptably slow responses — SLOs must be defined at the tail because real users experience individual requests, not averages
- C) The mean of HTTP latency samples is not statistically meaningful because HTTP latency distributions are non-normal
- D) p95 guarantees that exactly 95% of requests complete within budget, which is the minimum legally required for GDPR compliance

**User answered:** B · **Correct:** B · ✓

> If 95 out of 100 requests complete in 10ms but 5 complete in 500ms, the mean is approximately 34ms — well under the 50ms target — but 5% of real users are experiencing 10× the SLO. In a recommendation system serving millions of requests per day, that "5%" represents hundreds of thousands of degraded user experiences. This is why DDIA frames latency design around percentiles: the mean is a property of the distribution, not of any individual user's experience. The `assert_p95`-only API enforces this structurally — a test author cannot accidentally use the wrong metric without going out of their way to bypass the helper.
> DDIA ref: Chapter 1 — Reliable, Scalable, Maintainable Applications (percentile latency, tail at scale)

---

**Q6 · [Concept] · Sync client in async test context**
The `redis_client` fixture creates a synchronous `redis.Redis` client even though tests are `async def` functions. The `poll_redis_key` helper calls `r.hgetall(key)` synchronously inside an `async def` function, but uses `await asyncio.sleep(interval)` between checks. Why is the synchronous `hgetall` call safe here, and what would go wrong if `asyncio.sleep` were replaced with `time.sleep`?

- A) Synchronous Redis calls are safe because pytest-asyncio runs each test in its own thread; `time.sleep()` inside async would pause all concurrent tests sharing that thread pool
- B) A synchronous `hgetall()` completes and returns before the event loop can schedule anything else — there is no await point during the call, so the event loop is not running during it. Replacing `asyncio.sleep` with `time.sleep` would block the event loop for the entire interval, preventing any other coroutines from progressing during the wait
- C) Synchronous calls acquire the GIL, which prevents the asyncio event loop from running concurrently; `time.sleep` inside async is fine as long as no other coroutines are concurrently awaiting
- D) The synchronous client is safe only because there is a single Redis call per test; multiple sequential synchronous calls would deadlock the event loop

**User answered:** B · **Correct:** B · ✓

> asyncio is cooperative — a coroutine runs uninterrupted until it hits an `await` point. A synchronous `hgetall()` call has no `await`, so it runs to completion and returns without ever yielding to the event loop scheduler. The event loop simply isn't running during that call. `asyncio.sleep(interval)`, by contrast, *is* an await point — it yields control back to the event loop, allowing other coroutines (or pytest-asyncio internals) to run during the wait interval. Replacing it with `time.sleep` would block the OS thread for the full interval, freezing the entire event loop — no other coroutines could be scheduled, no I/O callbacks could fire, and in a test suite with session-scoped async fixtures the teardown logic could stall.
> DDIA ref: Chapter 11 — Stream Processing (event-driven systems must never block the main loop)

---

**Q7 · [Trade-off] · Standalone project with duplicated helper**
`helpers/pseudonymize.py` duplicates the 2-line HMAC implementation from the service packages rather than importing it from a service's `app/pseudonymize.py`. What is the core reason for this duplication?

- A) The services use different versions of the `hmac` stdlib module that are incompatible with the test harness's Python interpreter
- B) The test harness is a standalone uv project with its own `pyproject.toml` and no declared dependency on any service package — importing from a service's `app/` package would require installing that package into the test environment, coupling test infrastructure to service build state and creating a version dependency the harness is designed not to have
- C) The HMAC implementation in the services uses a non-stdlib library that would introduce a circular dependency if imported into the test harness
- D) pytest-asyncio does not support importing from packages located outside the test directory

**User answered:** B · **Correct:** B · ✓

> Each service in this repo is an independent uv project — `services/inference-api/` has its own `pyproject.toml`, `uv.lock`, and `.venv`. There is no workspace-level setup that would make service packages importable from other projects. Installing a service package into the test harness would mean the harness's `uv.lock` pins service dependencies (FastAPI, LightGBM, MLflow, etc.) that have nothing to do with test execution, making the environment heavier and coupling the test harness to service versioning decisions. The `pseudonymize` function is 2 lines of Python stdlib — the duplication cost is near zero, and the isolation benefit is real.
> DDIA ref: Chapter 4 — Encoding and Evolution (service boundaries; avoid tight coupling through shared libraries when the shared surface is minimal)

---
