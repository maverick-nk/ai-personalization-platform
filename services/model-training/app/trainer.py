from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class BaseTrainer(ABC):
    """Algorithm-agnostic training interface.

    Concrete trainers encapsulate all algorithm-specific concerns (hyperparameter
    names, categorical handling, MLflow flavour). The orchestration in train.py
    calls only these methods — adding a new algorithm requires no changes there.
    """

    @abstractmethod
    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
    ) -> None: ...

    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return predicted probabilities for the positive class (shape: [n_samples])."""
        ...

    @abstractmethod
    def log_to_mlflow(self, artifact_path: str) -> None:
        """Log the fitted model to the active MLflow run using the appropriate flavour."""
        ...

    @abstractmethod
    def feature_importances(self) -> dict[str, float]:
        """Return a mapping of feature name → importance score."""
        ...
