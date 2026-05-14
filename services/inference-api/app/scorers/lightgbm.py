from __future__ import annotations

import numpy as np
import pandas as pd
import mlflow.lightgbm

from .base import BaseScorer


class LightGBMScorer(BaseScorer):
    def __init__(self, model_uri: str) -> None:
        # mlflow.lightgbm.load_model handles the artifact path resolution and
        # returns a native lgb.Booster — more robust than hardcoding a file name.
        self._booster = mlflow.lightgbm.load_model(model_uri)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        # lgb.Booster.predict() returns probabilities directly for binary classification.
        return self._booster.predict(X)
