from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from .catalog import ContentItem
from .model_store import LoadedModel

log = logging.getLogger(__name__)

# Fallback used only when the schema contract omits time_of_day_categories.
_TIME_OF_DAY_CATEGORIES = ["morning", "afternoon", "evening", "night"]


def score_and_rank(
    features: dict,
    model: LoadedModel,
    catalog: list[ContentItem],
    top_n: int,
) -> list[tuple[ContentItem, float]]:
    """Score catalog items for a user and return the top_n ranked by score.

    Scoring formula:
        item_score = model_engagement_score × genre_affinity[item.genre]

    - model_engagement_score: click-probability for this user (single value —
      the model is user-level, not user-item)
    - genre_affinity: the user's normalized genre distribution from their
      session_genre_vector; items whose genre is absent get 0.0

    A high-engagement user's genre preferences are amplified; a churned or
    cold-start user gravitates toward zero (→ trending fallback in the caller).
    """
    engagement_score = _model_score(features, model)
    genre_affinity = _parse_genre_vector(features.get("session_genre_vector", "{}"))

    scored: list[tuple[ContentItem, float]] = []
    for item in catalog:
        affinity = genre_affinity.get(item.genre, 0.0)
        scored.append((item, float(engagement_score * affinity)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]


def _model_score(features: dict, model: LoadedModel) -> float:
    """Build the feature vector expected by the model and return click probability."""
    schema = model.schema
    features_schema = schema.get("features")
    if not features_schema:
        raise ValueError(f"Model schema is missing 'features' key: {schema}")

    feature_names = [f["name"] for f in features_schema]
    tod_categories = schema.get("time_of_day_categories", _TIME_OF_DAY_CATEGORIES)

    genre_vector = _parse_genre_vector(features.get("session_genre_vector", "{}"))

    row: dict = {}
    for feat in features_schema:
        name = feat["name"]
        dtype = feat["dtype"]
        if name.startswith("genre_"):
            genre_key = name[len("genre_"):]
            row[name] = genre_vector.get(genre_key, 0.0)
        elif dtype == "categorical":
            categories = feat.get("categories", tod_categories)
            row[name] = features.get(name, categories[0])
        elif dtype == "int32":
            row[name] = int(features.get(name, 0))
        else:
            row[name] = float(features.get(name, 0.0))

    df = pd.DataFrame([row], columns=feature_names)

    if "time_of_day_bucket" in df.columns:
        df["time_of_day_bucket"] = pd.Categorical(
            df["time_of_day_bucket"], categories=tod_categories
        )

    prob = model.scorer.predict_proba(df)
    return float(np.clip(prob[0], 0.0, 1.0))


def _parse_genre_vector(raw: str) -> dict[str, float]:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
