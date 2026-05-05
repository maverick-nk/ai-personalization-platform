# 0008. Model-Agnostic Trainer Abstraction

**Date:** 2026-05-04
**Status:** Accepted
**Service:** model-training
**Decided by:** user

---

## Context

The initial training pipeline was written with LightGBM-specific settings embedded in `Settings` (e.g. `lgbm_num_leaves`) and called `mlflow.lightgbm.log_model` directly in the orchestration layer. This made the pipeline impossible to extend to a different algorithm without editing the core training logic.

---

## Decision

Introduce a `BaseTrainer` ABC (`app/trainer.py`) with a factory registry (`app/trainers/factory.py`). Algorithm-specific concerns — hyperparameters, categorical feature handling, MLflow flavour — live inside each concrete trainer class. The orchestration in `train.py` calls only the four abstract methods: `fit`, `predict_proba`, `log_to_mlflow`, `feature_importances`.

---

## Alternatives Considered

| Option | Why rejected |
|---|---|
| LightGBM-only, no abstraction | Simplest, but makes algorithm swap a cross-cutting refactor |
| sklearn `Pipeline` as the abstraction | Adds sklearn coupling; LightGBM categorical handling doesn't fit cleanly into sklearn's API |

---

## Consequences

**Gets easier:**
- Adding a new algorithm (XGBoost, CatBoost) requires one new file in `app/trainers/` and one line in `factory.py`
- `Settings.model_type` + `model_params: dict` keep config generic — no algorithm-specific key prefixes

**Gets harder / trade-offs accepted:**
- Each new trainer must handle its own categorical encoding strategy (LightGBM supports native categoricals; XGBoost would require one-hot encoding in the trainer)
- Four abstract methods must be implemented per trainer — small but real overhead for each new algorithm

**Constraints this introduces:**
- Algorithm-specific logic must never leak into `train.py` — it belongs inside the trainer class

---

## System Design Concepts

| Concept | Reference | How it applies here |
|---|---|---|
| Encapsulation / separation of concerns | OOP fundamentals | Isolating algorithm details inside trainer classes prevents the orchestration layer from needing to know which model is in use |
| Strategy pattern | Design Patterns (GoF) | `BaseTrainer` is a textbook strategy interface; `factory.py` is the factory that selects the concrete strategy at runtime |

---

## Related

- Supersedes: none
- CONTEXT.md constraint added: yes — "Algorithm-specific concerns must stay inside the trainer class, never leak into `train.py`"
