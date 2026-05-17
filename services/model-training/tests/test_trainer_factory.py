from __future__ import annotations

import pytest
from app.trainer import BaseTrainer
from app.trainers.factory import get_trainer
from app.trainers.lightgbm import LightGBMTrainer


def test_get_trainer_lightgbm_returns_correct_type():
    trainer = get_trainer("lightgbm", {})
    assert isinstance(trainer, LightGBMTrainer)


def test_get_trainer_implements_base_interface():
    trainer = get_trainer("lightgbm", {})
    assert isinstance(trainer, BaseTrainer)


def test_get_trainer_unknown_raises_value_error():
    with pytest.raises(ValueError, match="Unknown model_type 'xgboost'"):
        get_trainer("xgboost", {})


def test_get_trainer_error_message_lists_available():
    with pytest.raises(ValueError, match="lightgbm"):
        get_trainer("random_forest", {})
