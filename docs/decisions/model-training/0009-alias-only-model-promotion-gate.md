# 0009. Alias-Only Model Promotion Gate (No Automated Quality Threshold)

**Date:** 2026-05-04
**Status:** Accepted — with known gap
**Service:** model-training
**Decided by:** user

---

## Context

When a new model version is registered in MLflow, the training pipeline sets the `staging` alias via `set_registered_model_alias`. The inference API polls for the latest `staging` model and hot-swaps to it within one poll cycle (~30s). There is currently no automated check that validates model quality (e.g. AUC > threshold, Precision@K > threshold) before the alias is set. A model trained on corrupted or low-quality data would be promoted and served to users within seconds of registration.

---

## Decision

Accept alias promotion as the only gate for now. The training pipeline logs AUC and Precision@10 to MLflow but does not enforce a minimum threshold before calling `set_registered_model_alias`. Promotion is a manual or CI-driven decision.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Enforce AUC > threshold inside `train_and_register()` before setting the alias | Correct approach — deferred to a future CI step rather than hardcoding a threshold that may need tuning |
| Require a human approval step in MLflow UI before alias promotion | Adds friction that makes automated retraining pipelines impractical |
| Shadow mode — serve both old and new model, compare live metrics before promoting | Correct for production; out of scope for Phase 1 |

---

## Consequences

**Gets easier:**
- Pipeline is simple — register, alias, done. No threshold configuration to maintain during early development.

**Gets harder / trade-offs accepted:**
- A corrupted or degraded model is promoted and served within one inference-api poll cycle (~30s) with no automated safeguard
- The only recovery path is manually re-pointing the alias to the previous version in the MLflow UI or via CLI

**Constraints this introduces:**
- Any future CI/CD step that calls `set_registered_model_alias` **must** first assert `auc > min_threshold` (and optionally `precision_at_10 > min_threshold`) from the logged run metrics before promoting
- The threshold values should be registered as MLflow model tags or as environment config — not hardcoded

---

## System Design Concepts

| Concept | Reference | How it applies here |
|---|---|---|
| End-to-end correctness | DDIA Ch 12 | Valid data at one layer (correct features) does not guarantee correct output without a quality gate at the promotion boundary |
| Fail-safe defaults | DDIA Ch 8 — Distributed Systems Trouble | Failing open (promoting any registered model) is expedient but unsafe; a quality gate is the fail-safe equivalent for ML promotion |

---

## Related

- ADR 0008 — Model-Agnostic Trainer Abstraction
- Follow-up: add a CI quality gate step before `set_registered_model_alias` when the inference-api (Step 5) or observability stack (Step 7) is built
- CONTEXT.md constraint added: yes — added to `## Do Not` section
