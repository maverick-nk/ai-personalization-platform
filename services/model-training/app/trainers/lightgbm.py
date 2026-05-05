from __future__ import annotations

import logging

import mlflow.lightgbm
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from app.trainer import BaseTrainer

log = logging.getLogger(__name__)

_CATEGORICAL_FEATURES = ["time_of_day_bucket"]


class LightGBMTrainer(BaseTrainer):
    def __init__(self, params: dict) -> None:
        self._params = params
        self._model: LGBMClassifier | None = None

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
    ) -> None:
        self._model = LGBMClassifier(objective="binary", **self._params)
        cat_cols = [c for c in _CATEGORICAL_FEATURES if c in X_train.columns]
        self._model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            categorical_feature=cat_cols,
        )
        log.info("LightGBM training complete. Best iteration: %s", self._model.best_iteration_)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        assert self._model is not None, "call fit() before predict_proba()"
        return self._model.predict_proba(X)[:, 1]

    def log_to_mlflow(self, artifact_path: str) -> None:
        assert self._model is not None, "call fit() before log_to_mlflow()"
        mlflow.lightgbm.log_model(self._model.booster_, artifact_path=artifact_path)

    def feature_importances(self) -> dict[str, float]:
        assert self._model is not None, "call fit() before feature_importances()"
        names = self._model.feature_name_
        scores = self._model.feature_importances_
        return dict(zip(names, scores.tolist()))
