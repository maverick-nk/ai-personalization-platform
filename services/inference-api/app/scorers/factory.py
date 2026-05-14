from __future__ import annotations

from .base import BaseScorer
from .lightgbm import LightGBMScorer

# To add XGBoost: "xgboost": XGBoostScorer — nothing else changes.
_REGISTRY: dict[str, type[BaseScorer]] = {
    "lightgbm": LightGBMScorer,
}


def get_scorer(model_type: str, model_uri: str) -> BaseScorer:
    if model_type not in _REGISTRY:
        raise ValueError(
            f"Unknown model_type '{model_type}'. "
            f"Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[model_type](model_uri)
