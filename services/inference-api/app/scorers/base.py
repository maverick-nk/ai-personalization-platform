from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class BaseScorer(ABC):
    """Algorithm-agnostic inference interface.

    Concrete scorers encapsulate flavor-specific model loading and prediction.
    model_store.py and scorer.py depend only on this interface — adding a new
    algorithm requires no changes there.

    Intentionally narrower than BaseTrainer: models are pre-trained and loaded
    from MLflow, so fit() has no place here.
    """

    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return predicted probabilities for the positive class (shape: [n_samples])."""
        ...
