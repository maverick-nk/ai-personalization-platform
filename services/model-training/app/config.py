from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODEL_TRAINING_", env_nested_delimiter="__")

    parquet_base_path: str = "/data/parquet"
    mlflow_tracking_uri: str = "http://localhost:5001"
    mlflow_experiment_name: str = "click-probability-model"
    mlflow_model_name: str = "personalization-click-model"
    training_date_range_days: int = 30
    validation_split_days: int = 7
    model_alias: str = "staging"
    # Label threshold: avg_watch_duration (percentage) >= this → label 1 (engaged)
    engaged_threshold: float = 70.0
    # Algorithm selection — swap here; nothing else changes
    model_type: str = "lightgbm"
    model_params: dict = {
        "num_leaves": 31,
        "n_estimators": 200,
        "learning_rate": 0.05,
    }
