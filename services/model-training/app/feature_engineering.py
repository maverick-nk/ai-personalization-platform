from __future__ import annotations

import json
import logging

import pandas as pd

log = logging.getLogger(__name__)

# Base feature columns that map 1-to-1 from Parquet → training matrix.
# Order is intentional: schema contract preserves this ordering.
BASE_FEATURE_COLS = [
    "watch_count_10min",
    "category_affinity_score",
    "avg_watch_duration",
    "recency_score",
]

TIME_OF_DAY_CATEGORIES = ["morning", "afternoon", "evening", "night"]


def get_known_genres(df: pd.DataFrame) -> list[str]:
    """Return sorted unique genre keys seen across all session_genre_vector values."""
    genres: set[str] = set()
    for raw in df["session_genre_vector"]:
        try:
            genres.update(json.loads(raw).keys())
        except (json.JSONDecodeError, TypeError):
            pass
    return sorted(genres)


def build_feature_matrix(
    df: pd.DataFrame,
    genres: list[str],
    engaged_threshold: float,
) -> tuple[pd.DataFrame, pd.Series, dict]:
    """Transform raw Parquet rows into a training-ready feature matrix.

    Returns (X, y, schema_contract):
    - X: feature DataFrame
    - y: binary engaged label Series
    - schema_contract: dict describing every feature (persisted to MLflow as artifact)

    genres must be derived from the training split only to prevent data leakage.
    """
    df = df.copy()

    # Expand session_genre_vector JSON → genre_{name} float columns
    genre_rows: list[dict] = []
    for raw in df["session_genre_vector"]:
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            parsed = {}
        genre_rows.append({f"genre_{g}": parsed.get(g, 0.0) for g in genres})

    genre_df = pd.DataFrame(genre_rows, index=df.index)

    # Encode time_of_day_bucket as pandas Categorical so LightGBM (and future
    # trainers that support categoricals natively) get the right dtype signal.
    df["time_of_day_bucket"] = pd.Categorical(
        df["time_of_day_bucket"], categories=TIME_OF_DAY_CATEGORIES
    )

    feature_cols = BASE_FEATURE_COLS + ["time_of_day_bucket"] + list(genre_df.columns)
    X = pd.concat([df[BASE_FEATURE_COLS + ["time_of_day_bucket"]], genre_df], axis=1)
    X = X[feature_cols]

    y = (df["avg_watch_duration"] >= engaged_threshold).astype(int).rename("engaged")

    schema_contract = _build_schema_contract(feature_cols, genres, engaged_threshold)
    return X, y, schema_contract


def _build_schema_contract(
    feature_cols: list[str],
    genres: list[str],
    engaged_threshold: float,
) -> dict:
    """Build the feature schema contract dict to be registered alongside the model."""
    features = []
    for col in feature_cols:
        if col == "watch_count_10min":
            features.append({"name": col, "dtype": "int32"})
        elif col == "time_of_day_bucket":
            features.append({
                "name": col,
                "dtype": "categorical",
                "categories": TIME_OF_DAY_CATEGORIES,
            })
        elif col.startswith("genre_"):
            features.append({"name": col, "dtype": "float64"})
        else:
            features.append({"name": col, "dtype": "float64"})

    return {
        "version": "1.0",
        "features": features,
        "label": "engaged",
        "label_definition": f"avg_watch_duration >= {engaged_threshold}",
        "time_of_day_categories": TIME_OF_DAY_CATEGORIES,
        "genres": genres,
    }
