from __future__ import annotations

import json
import logging
import tempfile
from datetime import date, timedelta
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from app.config import Settings
from app.data_loader import load_parquet
from app.feature_engineering import build_feature_matrix, get_known_genres
from app.trainers.factory import get_trainer

log = logging.getLogger(__name__)

_PRECISION_AT_K = 10


def _precision_at_k(y_true: pd.Series, y_prob: np.ndarray, k: int) -> float:
    top_k_idx = np.argsort(y_prob)[::-1][:k]
    return float(y_true.iloc[top_k_idx].mean())


def _chronological_split(
    df: pd.DataFrame, validation_split_days: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sorted_dates = sorted(df["event_date"].unique())
    if len(sorted_dates) <= validation_split_days:
        raise ValueError(
            f"Not enough distinct event_dates for a {validation_split_days}-day "
            f"validation split (only {len(sorted_dates)} dates available)"
        )
    cutoff = sorted_dates[-validation_split_days]
    train_df = df[df["event_date"] < cutoff]
    val_df = df[df["event_date"] >= cutoff]
    log.info(
        "Split: %d train rows (%s → %s), %d val rows (%s → %s)",
        len(train_df), sorted_dates[0], sorted_dates[-validation_split_days - 1],
        len(val_df), cutoff, sorted_dates[-1],
    )
    return train_df, val_df


def _get_or_create_experiment(client: mlflow.tracking.MlflowClient, name: str) -> str:
    """Return the experiment ID, creating it with mlflow-artifacts:/ if absent.

    Explicit artifact_location ensures the experiment always uses the proxy artifact
    store regardless of the server's --default-artifact-root setting, so the
    experiment works correctly when running both inside and outside Docker.
    """
    from mlflow.entities import LifecycleStage
    experiment = client.get_experiment_by_name(name)
    if experiment is not None and experiment.lifecycle_stage == LifecycleStage.ACTIVE:
        return experiment.experiment_id
    if experiment is not None and experiment.lifecycle_stage == LifecycleStage.DELETED:
        # Restore the deleted experiment so we can reuse it; its artifact_location
        # is already set correctly in the DB from when it was first created.
        client.restore_experiment(experiment.experiment_id)
        log.info("Restored deleted experiment '%s' (id=%s)", name, experiment.experiment_id)
        return experiment.experiment_id
    return client.create_experiment(name, artifact_location="mlflow-artifacts:/")


def train_and_register(settings: Settings) -> str:
    """Full training pipeline: load → split → engineer → fit → evaluate → register.

    Returns the MLflow run ID.
    """
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    client = mlflow.tracking.MlflowClient()
    experiment_id = _get_or_create_experiment(client, settings.mlflow_experiment_name)

    today = date.today()
    date_from = today - timedelta(days=settings.training_date_range_days)

    log.info("Loading Parquet from %s → %s", date_from, today)
    df = load_parquet(settings.parquet_base_path, date_from, today)

    train_df, val_df = _chronological_split(df, settings.validation_split_days)

    # Genres derived from training split only — prevents val genre leakage into schema
    genres = get_known_genres(train_df)
    log.info("Known genres in training data: %s", genres)

    X_train, y_train, schema_contract = build_feature_matrix(
        train_df, genres, settings.engaged_threshold
    )
    X_val, y_val, _ = build_feature_matrix(val_df, genres, settings.engaged_threshold)

    trainer = get_trainer(settings.model_type, settings.model_params)

    with mlflow.start_run(experiment_id=experiment_id) as run:
        mlflow.log_params({
            "model_type": settings.model_type,
            "training_date_range_days": settings.training_date_range_days,
            "validation_split_days": settings.validation_split_days,
            "engaged_threshold": settings.engaged_threshold,
            "train_rows": len(X_train),
            "val_rows": len(X_val),
            "positive_rate_train": float(y_train.mean()),
            **{f"model_param_{k}": v for k, v in settings.model_params.items()},
        })

        trainer.fit(X_train, y_train, X_val, y_val)

        y_prob = trainer.predict_proba(X_val)
        auc = roc_auc_score(y_val, y_prob)
        p_at_k = _precision_at_k(y_val, y_prob, _PRECISION_AT_K)

        mlflow.log_metrics({
            "auc": auc,
            f"precision_at_{_PRECISION_AT_K}": p_at_k,
        })

        importances = trainer.feature_importances()
        mlflow.log_metrics({f"importance_{k}": v for k, v in importances.items()})

        log.info("Evaluation — AUC: %.4f, Precision@%d: %.4f", auc, _PRECISION_AT_K, p_at_k)

        trainer.log_to_mlflow(artifact_path="model")

        # Feature schema contract — logged by its canonical name so inference-api
        # can reliably download it by artifact path "feature_schema.json".
        schema_path = Path(tempfile.mkdtemp()) / "feature_schema.json"
        schema_path.write_text(json.dumps(schema_contract, indent=2))
        mlflow.log_artifact(str(schema_path), artifact_path="")

        run_id = run.info.run_id

    # Register and alias the model version
    model_uri = f"runs:/{run_id}/model"
    mv = mlflow.register_model(model_uri=model_uri, name=settings.mlflow_model_name)
    client = mlflow.tracking.MlflowClient()
    client.set_registered_model_alias(
        name=settings.mlflow_model_name,
        alias=settings.model_alias,
        version=mv.version,
    )
    log.info(
        "Registered model '%s' version %s with alias '%s'",
        settings.mlflow_model_name, mv.version, settings.model_alias,
    )

    return run_id
