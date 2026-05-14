from __future__ import annotations

import json
import numpy as np
import pandas as pd
import pytest

from app.catalog import ContentItem
from app.model_store import LoadedModel
from app.scorer import _parse_genre_vector, score_and_rank
from app.scorers.base import BaseScorer


class _FixedScorer(BaseScorer):
    """Test double — always returns a fixed probability."""
    def __init__(self, prob: float = 0.8) -> None:
        self._prob = prob

    def predict_proba(self, X):
        return np.array([self._prob] * len(X))


def _make_model(genres: list[str], prob: float = 0.8) -> LoadedModel:
    schema = {
        "features": [
            {"name": "watch_count_10min", "dtype": "int32"},
            {"name": "category_affinity_score", "dtype": "float64"},
            {"name": "avg_watch_duration", "dtype": "float64"},
            {"name": "recency_score", "dtype": "float64"},
            {"name": "time_of_day_bucket", "dtype": "categorical",
             "categories": ["morning", "afternoon", "evening", "night"]},
            *[{"name": f"genre_{g}", "dtype": "float64"} for g in genres],
        ],
        "genres": genres,
    }
    return LoadedModel(scorer=_FixedScorer(prob), schema=schema, version="1")


def _make_features(genre_vector: dict) -> dict:
    return {
        "watch_count_10min": 5,
        "category_affinity_score": 0.7,
        "avg_watch_duration": 80.0,
        "recency_score": 0.6,
        "time_of_day_bucket": "evening",
        "session_genre_vector": json.dumps(genre_vector),
    }


CATALOG = [
    ContentItem("c1", "action", "Action Film"),
    ContentItem("c2", "drama", "Drama Series"),
    ContentItem("c3", "comedy", "Comedy Show"),
]


def test_score_and_rank_orders_by_genre_affinity():
    model = _make_model(["action", "drama", "comedy"])
    features = _make_features({"action": 0.7, "drama": 0.2, "comedy": 0.1})

    ranked = score_and_rank(features, model, CATALOG, top_n=3)

    ids = [item.content_id for item, _ in ranked]
    assert ids[0] == "c1"  # action has highest affinity


def test_score_and_rank_respects_top_n():
    model = _make_model(["action", "drama", "comedy"])
    features = _make_features({"action": 0.7, "drama": 0.2, "comedy": 0.1})

    ranked = score_and_rank(features, model, CATALOG, top_n=2)
    assert len(ranked) == 2


def test_score_zero_for_missing_genre():
    model = _make_model(["action"])
    features = _make_features({})  # empty genre vector

    ranked = score_and_rank(features, model, CATALOG, top_n=3)
    scores = [score for _, score in ranked]
    assert all(s == 0.0 for s in scores)


def test_parse_genre_vector_empty():
    assert _parse_genre_vector("{}") == {}


def test_parse_genre_vector_invalid_json():
    assert _parse_genre_vector("not-json") == {}


def test_parse_genre_vector_valid():
    result = _parse_genre_vector('{"action": 0.6, "drama": 0.4}')
    assert result == {"action": 0.6, "drama": 0.4}
