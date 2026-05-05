from __future__ import annotations

from app.trainer import BaseTrainer
from app.trainers.lightgbm import LightGBMTrainer

_REGISTRY: dict[str, type[BaseTrainer]] = {
    "lightgbm": LightGBMTrainer,
    # To add XGBoost: "xgboost": XGBoostTrainer — nothing else changes.
}


def get_trainer(model_type: str, model_params: dict) -> BaseTrainer:
    if model_type not in _REGISTRY:
        raise ValueError(
            f"Unknown model_type '{model_type}'. "
            f"Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[model_type](model_params)
