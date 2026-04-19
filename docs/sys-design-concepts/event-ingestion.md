# System Design Concepts — event-ingestion

> Quiz log for the `event-ingestion` service.
> Reference: "Designing Data-Intensive Applications" — Martin Kleppmann
> Concepts scored ≥ 80% are deprioritised in future sessions.

---

## Concept Coverage

| Concept | Times Tested | Best Score | Last Tested |
|---|---|---|---|
| Pseudonymisation vs anonymisation | 1 | 0% | 2026-04-18 |
| Kafka delivery semantics (at-most-once) | 1 | 100% | 2026-04-18 |
| Kafka producer buffer / backpressure | 1 | 100% | 2026-04-18 |
| Log-structured storage in Kafka | 1 | 100% | 2026-04-18 |
| Synchronous vs asynchronous communication | 1 | 100% | 2026-04-18 |
| Idempotency | 1 | 100% | 2026-04-18 |
| Kafka partitioning and ordering | 1 | 0% | 2026-04-18 |
| Schema evolution | 1 | 100% | 2026-04-18 |
| Hash functions and key management | 1 | 100% | 2026-04-18 |
| Consumer offset management | 1 | 100% | 2026-04-18 |
| app.state vs module-level globals | 1 | 100% | 2026-04-18 |
| Kafka topic pre-creation | 1 | 100% | 2026-04-18 |
| pydantic-settings fail-fast config | 1 | 100% | 2026-04-18 |

---

## Sessions

### 2026-04-18 · event-ingestion full service bootstrap

**Score: 11/13 (85%)**
**Concepts tested:** Pseudonymisation vs anonymisation, Kafka delivery semantics, Kafka producer buffer/backpressure, Log-structured storage, Synchronous vs asynchronous communication, Idempotency, Kafka partitioning and ordering, Schema evolution, Hash functions and key management, Consumer offset management, app.state vs module-level globals, Kafka topic pre-creation, pydantic-settings fail-fast config

---

**Q1 · [Trade-off] · Pseudonymisation vs anonymisation**
We use HMAC-SHA256 to replace raw `user_id` before publishing to Kafka. This is pseudonymisation, not anonymisation. What is the practical difference?

- A) Pseudonymisation is reversible with the secret key; anonymisation is irreversible — we chose pseudonymisation so we can re-identify users for debugging if needed
- B) Pseudonymisation replaces the identifier with a token derived from a secret; it is reversible only by someone with the key. Anonymisation removes or generalises data so re-identification is impossible even with additional information
- C) There is no meaningful difference — both techniques prevent re-identification by downstream systems
- D) Anonymisation requires hashing; pseudonymisation requires encryption — we use hashing because it is faster

**User answered:** A · **Correct:** B · ✗

> HMAC-SHA256 is a one-way function — you cannot reverse it to recover the original user_id even with the secret key. What the secret enables is *consistency*: the same user_id + same secret always produces the same pseudo_user_id, so records can be correlated across time without ever exposing the raw ID. Anonymisation goes further — it removes or generalises data so that re-identification is impossible even with additional information. The key distinction is that pseudonymisation preserves a deterministic link (useful for feature lookups), while anonymisation severs it entirely.
> DDIA ref: Chapter 12 — Privacy and data protection, pseudonymisation as a technique for reducing re-identification risk without losing analytical utility.

---

**Q2 · [Concept] · Kafka delivery semantics (at-most-once)**
We publish to Kafka with `poll(0)` and return 202 immediately — no broker ack is awaited. Which delivery guarantee does this implement?

- A) Exactly-once — Kafka deduplicates messages automatically on the broker side
- B) At-least-once — the producer retries until it gets an ack, so duplicates are possible
- C) At-most-once — the message is sent without waiting for ack; if the broker doesn't receive it, it is silently lost
- D) Best-effort — Kafka's internal retry policy upgrades this to at-least-once transparently

**User answered:** C · **Correct:** C · ✓

> Fire-and-forget with poll(0) means the producer hands the message to its internal buffer and moves on. If the broker never acknowledges receipt — due to a network blip, buffer overflow, or broker crash — the message is gone with no retry and no error surfaced to the caller. This is at-most-once: each event is delivered zero or one times. We accepted this trade-off deliberately because a missed watch event has negligible impact on recommendation quality, and eliminating the ack round-trip keeps API latency low.
> DDIA ref: Chapter 11 — at-most-once, at-least-once, exactly-once delivery semantics and their trade-offs in stream processing.

---

**Q3 · [Scenario] · Kafka producer buffer / backpressure**
The event ingestion service is under heavy load — 10,000 requests/sec are hitting POST /events/watch. The confluent-kafka producer's internal buffer fills up faster than the broker can drain it. Under our fire-and-forget implementation, what happens to new incoming events?

- A) The producer blocks the FastAPI request handler until buffer space is free, adding latency but preserving all events
- B) The producer raises an exception that FastAPI catches and returns 503
- C) Events are silently dropped — the produce() call discards messages when the buffer is full and poll(0) never retries them
- D) Kafka automatically increases partition count to absorb the extra throughput

**User answered:** C · **Correct:** C · ✓

> With fire-and-forget and poll(0), there is no backpressure mechanism wired to the HTTP layer. When the producer buffer is full, produce() silently drops the message — the delivery callback fires with an error, which we log, but the 202 has already been returned to the caller. This is the hidden cost of at-most-once: the loss is silent and the client never knows. In a higher-stakes pipeline you'd either block on flush(), return 503 when the buffer exceeds a threshold, or use a separate queue with backpressure.
> DDIA ref: Chapter 11 — backpressure in stream systems; producers must either drop, block, or buffer when consumers are slow.

---

**Q4 · [Concept] · Log-structured storage in Kafka**
Kafka stores events in an append-only, partitioned log. What is the key consequence of this design for consumers?

- A) Consumers must process events in the order they were produced across all partitions globally
- B) Consumers can replay events by seeking to any offset — the log is immutable and historical events are not overwritten
- C) Each consumer group gets its own physical copy of the log, so one slow consumer cannot affect another
- D) Kafka automatically deletes events once all consumer groups have read them, keeping storage bounded

**User answered:** B · **Correct:** B · ✓

> Kafka's append-only log means the broker never modifies or deletes records on consumption — consumers track their own offset and can seek backwards to replay. This is exactly what our integration tests exploit: setting auto.offset.reset=earliest lets the test consumer re-read from the start of the partition to find the UUID-matched message even if older messages are present. Retention is controlled by time or size policy on the broker, not by whether consumers have read the data — so multiple independent consumer groups can each maintain their own position in the same log without interference.
> DDIA ref: Chapter 11 — the log as a data structure; Kafka's storage model and consumer offset management.

---

**Q5 · [Trade-off] · Synchronous vs asynchronous communication**
The ingestion API returns 202 Accepted rather than waiting for the downstream feature pipeline to confirm it processed the event. What is the primary trade-off this introduces?

- A) The API becomes stateless, which means it cannot be horizontally scaled
- B) The caller gets lower latency and the API stays available even if Kafka or Flink is slow — but the caller cannot know whether the event was ultimately processed
- C) Using 202 instead of 200 violates REST semantics and will confuse API clients
- D) Asynchronous publish requires exactly-once delivery to prevent the feature store from double-counting events

**User answered:** B · **Correct:** B · ✓

> 202 Accepted is the correct HTTP semantic for "I've accepted your request but haven't finished processing it yet." The caller gets a fast response regardless of Kafka or Flink health, which is exactly what keeps p99 latency low at the ingestion boundary. The accepted trade-off is observability: the caller has no way to know if the event reached the feature store, which is fine for watch/session events but would be unacceptable for anything requiring confirmation (e.g. a consent change).
> DDIA ref: Chapter 11 — decoupling producers from consumers via a message broker; async communication and its effect on system availability.

---

**Q6 · [Concept] · Idempotency**
A client retries POST /events/watch after a network timeout — the original request actually succeeded and the event was already published to Kafka. The retry publishes a duplicate. Under our current design, what happens?

- A) Kafka deduplicates the message using the event's timestamp field
- B) The duplicate is published as a second message — downstream consumers will see the same event twice with no way to detect it
- C) Pydantic validation rejects the duplicate at the schema layer before it reaches the producer
- D) The HMAC pseudo_user_id acts as a deduplication key and Kafka drops the second message automatically

**User answered:** B · **Correct:** B · ✓

> Our current design has no idempotency key — there is nothing in the payload or producer config that lets Kafka or the downstream pipeline detect a duplicate. The feature pipeline would increment watch_count_10min twice for the same event, skewing the feature value. Fixing this properly requires either a client-supplied idempotency key or deduplication logic in the Flink consumer keyed on (pseudo_user_id, content_id, timestamp).
> DDIA ref: Chapter 11 — idempotent producers, exactly-once semantics, and end-to-end deduplication strategies in stream pipelines.

---

**Q7 · [Concept] · Kafka partitioning and ordering**
Our topics are created with a single partition (`--partitions 1`). If we later scale to 4 partitions, what ordering guarantee changes?

- A) No change — Kafka guarantees global ordering across all partitions by default
- B) Ordering is guaranteed within a partition but not across partitions — events for the same user may land in different partitions and be processed out of order by consumers
- C) Ordering is lost entirely — partitioned Kafka topics provide no ordering guarantees at all
- D) The producer automatically routes all events for the same user to the same partition using the pseudo_user_id, preserving per-user order

**User answered:** C · **Correct:** B · ✗

> Kafka guarantees strict ordering within a single partition. Across partitions, there is no global ordering. With one partition, all events are ordered. With 4 partitions and no explicit partition key, our producer distributes messages across partitions (round-robin or random), so two consecutive events from the same user can land in different partitions and be consumed out of order. The fix is to produce with pseudo_user_id as the message key — Kafka hashes the key and routes all messages with the same key to the same partition, preserving per-user ordering. Our current produce() call omits a key, so this is a latent ordering bug if we scale beyond one partition.
> DDIA ref: Chapter 11 — partitioning and ordering in Kafka; partition keys as the mechanism for co-locating related events.

---

**Q8 · [Scenario] · Schema evolution**
Six months from now, the product team wants to add a `quality_score: float` field to WatchEvent. Under our current Pydantic-only schema design, what is the safest way to roll this out?

- A) Add the field as required in Pydantic — old clients will get a 422 until they update, forcing a coordinated cutover
- B) Add the field as optional with a default in Pydantic — new events include it, old consumers ignore unknown fields, no coordinated cutover needed
- C) Create a new topic user.watch.events.v2 and migrate all consumers before touching the original topic
- D) Schema changes are blocked until Avro is introduced — Pydantic models cannot be evolved safely

**User answered:** B · **Correct:** B · ✓

> Adding an optional field with a default is a backward-compatible change — existing producers that don't send the field still pass validation, and existing consumers that don't read the field safely ignore it. Making it required would be a breaking change. The deeper issue is that with Pydantic-only schemas, this compatibility contract is implicit and unenforced — that's the gap Avro + Schema Registry closes.
> DDIA ref: Chapter 4 — schema evolution, forward and backward compatibility, and the role of schema registries in enforcing contracts across services.

---

**Q9 · [Concept] · Hash functions and key management**
The `PSEUDONYMIZE_SECRET` must stay consistent across all deployments. What breaks if it is rotated mid-operation?

- A) Nothing — HMAC is stateless, so new and old pseudo_user_ids are interchangeable
- B) The HMAC digest changes for every user_id — historical pseudo_user_ids in Redis, Parquet, and Kafka no longer match new ones, breaking feature lookups and recommendation continuity
- C) Kafka rejects messages signed with a new secret until brokers are restarted
- D) Only new events are affected — existing Redis keys are automatically re-keyed to the new secret on next access

**User answered:** B · **Correct:** B · ✓

> HMAC is deterministic — change the secret and every user gets a new pseudo_user_id. Historical records carry the old digest; new events carry the new one. Feature lookups fail, Redis returns cache misses, and the model loses all historical signal. This is why the secret is treated as a deployment invariant — it is keying material, not a password.
> DDIA ref: Chapter 12 — data privacy, pseudonymisation, and the operational risks of key management in long-lived data pipelines.

---

**Q10 · [Scenario] · Consumer offset management**
Our integration tests use auto.offset.reset=earliest and match messages by pseudo_user_id. A previous test run left 500 old messages in the topic. When a new test subscribes and polls, what happens?

- A) The consumer starts at the latest offset and only sees messages produced after it subscribed
- B) The consumer reads all 500 old messages first, then the new test message — it scans through them and matches on pseudo_user_id to find the right one
- C) Kafka delivers only the message matching the test's pseudo_user_id — the broker filters on payload content
- D) The 500 old messages cause the test to fail with a duplicate message error

**User answered:** B · **Correct:** B · ✓

> With auto.offset.reset=earliest and a fresh consumer group, the consumer begins at offset 0 and reads every message. Kafka has no content-based filtering — filtering happens client-side. Our poll loop scans each message and checks pseudo_user_id, ignoring old ones until it finds the UUID-unique match. This is why we generate a unique user_id per test with uuid.uuid4().
> DDIA ref: Chapter 11 — consumer offsets, log replay, and the distinction between broker-side and consumer-side filtering in Kafka.

---

**Q11 · [Trade-off] · app.state vs module-level globals**
We attach the KafkaProducer to app.state in the lifespan context manager rather than initialising it as a module-level global. What problem does this solve?

- A) Module-level globals are not thread-safe; app.state uses a lock internally
- B) A module-level global is initialised at import time — if Settings() fails (missing secret), the import fails. app.state defers initialisation to startup, and tests can inject a different producer without patching globals
- C) FastAPI requires all shared resources to be on app.state — module-level globals cause a 500 error
- D) app.state serialises all requests through a single producer instance; module-level globals would create one producer per request

**User answered:** B · **Correct:** B · ✓

> Module-level initialisation runs at import time — before any request is handled and before the test fixture can intercept it. app.state solves both problems: the producer is created in the lifespan context manager, and tests can assign app.state.producer = KafkaProducer(TEST_KAFKA) directly before making requests — no monkeypatching needed.
> DDIA ref: Chapter 1 — maintainability; making dependencies explicit reduces coupling and makes systems easier to test.

---

**Q12 · [Scenario] · Kafka topic pre-creation**
start-infra.sh pre-creates user.watch.events before any service starts. Without this, topics would be auto-created on first produce. What race condition does pre-creation prevent?

- A) The producer crashes if the topic doesn't exist — auto-create is disabled in our Kafka config
- B) A consumer subscribing before the topic exists gets no partition assignment. If the producer then auto-creates the topic, the consumer misses all messages published before its next rebalance
- C) Auto-created topics default to 0 partitions, causing the producer to block indefinitely
- D) Kafka's auto-create adds a 30-second delay before the topic becomes writable

**User answered:** B · **Correct:** B · ✓

> This is the exact race our integration tests hit before the fix. A consumer subscribes to a topic that doesn't exist — Kafka gives it no partition assignment. The producer then publishes (triggering auto-create), but the consumer misses the message under auto.offset.reset=latest. Pre-creating topics ensures partitions exist before any consumer subscribes.
> DDIA ref: Chapter 11 — consumer group rebalancing, partition assignment, and ordering guarantees that depend on a stable partition topology.

---

**Q13 · [Trade-off] · pydantic-settings fail-fast config**
`pseudonymize_secret` has no default value in Settings. What is the deliberate consequence of this design?

- A) The app silently uses an empty string as the secret if the env var is missing
- B) The app fails to start with a validation error if PSEUDONYMIZE_SECRET is not set — there is no safe fallback for a required secret
- C) FastAPI catches the missing field and returns 503 on the first request that triggers pseudonymization
- D) pydantic-settings falls back to reading the value from the system keychain if the env var is absent

**User answered:** B · **Correct:** B · ✓

> A missing required field in pydantic-settings raises a ValidationError at import time — the process exits before serving a single request. A silent empty-string fallback would produce pseudo_user_ids that appear valid but are cryptographically worthless. Failing loud and early forces the operator to set the secret before deployment.
> DDIA ref: Chapter 1 — reliability through fail-fast design; catching configuration errors at startup rather than at runtime under load.

---
