from __future__ import annotations

import json

import pandas as pd
import pytest
from app.feature_engineering import (
    TIME_OF_DAY_CATEGORIES,
    build_feature_matrix,
    get_known_genres,
)


def _make_df(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "watch_count_10min": 3,
        "category_affinity_score": 0.5,
        "avg_watch_duration": 60.0,
        "time_of_day_bucket": "evening",
        "recency_score": 0.7,
        "session_genre_vector": "{}",
        "event_date": "2026-05-01",
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


def test_genre_expansion_fills_known_genres():
    df = _make_df([
        {"session_genre_vector": json.dumps({"action": 0.6, "drama": 0.4})},
        {"session_genre_vector": json.dumps({"action": 0.9})},
    ])
    genres = ["action", "drama"]
    X, _, _ = build_feature_matrix(df, genres, engaged_threshold=70.0)
    assert X.loc[0, "genre_action"] == pytest.approx(0.6)
    assert X.loc[0, "genre_drama"] == pytest.approx(0.4)
    assert X.loc[1, "genre_drama"] == pytest.approx(0.0)


def test_label_creation_above_threshold():
    df = _make_df([
        {"avg_watch_duration": 75.0},
        {"avg_watch_duration": 50.0},
        {"avg_watch_duration": 70.0},
    ])
    _, y, _ = build_feature_matrix(df, genres=[], engaged_threshold=70.0)
    assert y.tolist() == [1, 0, 1]


def test_label_creation_exact_threshold():
    df = _make_df([{"avg_watch_duration": 70.0}])
    _, y, _ = build_feature_matrix(df, genres=[], engaged_threshold=70.0)
    assert y.iloc[0] == 1


def test_time_of_day_is_categorical():
    df = _make_df([{"time_of_day_bucket": "morning"}])
    X, _, _ = build_feature_matrix(df, genres=[], engaged_threshold=70.0)
    assert hasattr(X["time_of_day_bucket"], "cat"), "expected pandas Categorical"
    assert list(X["time_of_day_bucket"].cat.categories) == TIME_OF_DAY_CATEGORIES


def test_schema_contract_structure():
    df = _make_df([{"session_genre_vector": json.dumps({"comedy": 1.0})}])
    genres = ["comedy"]
    _, _, contract = build_feature_matrix(df, genres=genres, engaged_threshold=70.0)
    assert "version" in contract
    assert "features" in contract
    assert "label" in contract
    assert "time_of_day_categories" in contract
    assert contract["label"] == "engaged"
    feature_names = [f["name"] for f in contract["features"]]
    assert "time_of_day_bucket" in feature_names
    assert "genre_comedy" in feature_names


def test_schema_contract_time_of_day_has_categories():
    df = _make_df([{}])
    _, _, contract = build_feature_matrix(df, genres=[], engaged_threshold=70.0)
    tod_entry = next(f for f in contract["features"] if f["name"] == "time_of_day_bucket")
    assert tod_entry["dtype"] == "categorical"
    assert tod_entry["categories"] == TIME_OF_DAY_CATEGORIES


def test_get_known_genres_returns_sorted_unique():
    df = _make_df([
        {"session_genre_vector": json.dumps({"drama": 0.4, "action": 0.6})},
        {"session_genre_vector": json.dumps({"comedy": 1.0, "action": 0.0})},
        {"session_genre_vector": "{}"},
    ])
    genres = get_known_genres(df)
    assert genres == ["action", "comedy", "drama"]


def test_get_known_genres_handles_invalid_json():
    df = _make_df([
        {"session_genre_vector": "not-json"},
        {"session_genre_vector": json.dumps({"action": 0.5})},
    ])
    genres = get_known_genres(df)
    assert genres == ["action"]
