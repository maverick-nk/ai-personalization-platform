# 0007. Fail Closed When Privacy Service Is Unreachable

**Date:** 2026-04-30
**Status:** Accepted
**Service:** inference-api
**Decided by:** user

---

## Context

The inference-api calls the privacy service before every feature fetch. The privacy service is a network dependency — it can be slow, restarting, or unreachable during outages. The inference-api must decide what to do when it cannot get a consent answer: assume granted, assume denied, or surface the failure to the caller. This decision has direct compliance implications: treating silence as permission creates a window where a user who has revoked consent could receive personalized content during an outage.

---

## Decision

When the privacy service is unreachable (timeout, connection refused, or any error response), the inference-api treats the result as `consent_granted=false` and returns the non-personalized trending fallback. The failure is never surfaced as a 5xx to the caller — the response is always valid, just not personalized.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Fail open (treat unreachability as granted) | Compliance risk: if a user revokes consent and the privacy service then goes down, they continue receiving personalized content. Silence from the consent gate cannot be treated as permission. |
| Circuit breaker with cached last-known consent state | Directly violates the no-caching invariant — the reason consent is checked fresh on every request is precisely to prevent stale state from honoring a revoked consent. A cache reintroduces the same risk at a different layer. |
| Return hard error (5xx) to caller | Breaks the contract that inference-api always returns a valid response. Cold-start users and consent-denied users both receive the trending fallback, not an error — the service must be resilient. |

---

## Consequences

**Gets easier:**
- Compliance posture is unambiguous — privacy service unavailability cannot create a window of unauthorized personalization
- No special error-handling path needed in callers; the trending fallback is the universal safe response for any non-personalized case (cold-start, revoked consent, service down)
- Consistent with the existing opt-in default in the privacy service itself: missing record → denied; unreachable service → also denied

**Gets harder / trade-offs accepted:**
- Any privacy service outage degrades personalization for **all** users, including those who have explicitly granted consent — not just users who revoked
- From the end user's perspective the degradation is invisible (they see trending content either way); from an ops perspective it requires monitoring to distinguish "privacy service down" from "user revoked consent"
- The fallback is indistinguishable at the response level — a metric or log tag on the inference-api side must differentiate privacy-unavailable fallbacks from consent-denied fallbacks and cold-start fallbacks

**Constraints this introduces:**
- The inference-api must always have a trending fallback ready — this was already required for cold-start, so no new infrastructure is introduced
- Must not add consent caching in the inference-api to reduce the personalization degradation window — that trades compliance correctness for availability, which is the wrong direction for this system
- Timeouts on the privacy service call must be set explicitly and kept well under the 5ms budget — an unbounded wait would blow the 50ms end-to-end SLO for all requests, not just those where privacy is slow

---

## System Design Concepts

| Concept | DDIA Reference | How it applies here |
|---|---|---|
| Fail-safe defaults | Ch 8 — Trouble with Distributed Systems | When a system cannot determine state due to a partial failure, defaulting to the restrictive option (denied) avoids the compliance risk of assuming the permissive one |
| Availability vs consistency trade-off | Ch 9 — Consistency and Consensus | This decision explicitly chooses consistency (consent state is never stale or assumed) over availability (personalization degrades during outages) — a deliberate CP-side choice for a compliance boundary |
| Timeouts and partial failures in distributed systems | Ch 8 — Trouble with Distributed Systems | Network calls between microservices can hang indefinitely without explicit timeouts; the privacy check must have a hard deadline so a slow privacy service doesn't cascade into a latency breach on every inference request |

---

## Related

- Related: ADR 0006 — Audit Log Range Partitioning (same service — privacy; establishes the compliance posture this decision reinforces)
- CONTEXT.md flag added: yes — inference-api `## Do Not`: do not cache consent state; do not treat privacy service errors as granted
