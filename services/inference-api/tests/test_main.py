from __future__ import annotations

import json
from unittest.mock import AsyncMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from app.catalog import build_catalog, build_trending
from app.config import Settings
from app.main import app
from app.model_store import LoadedModel
from app.scorers.base import BaseScorer


class _FixedScorer(BaseScorer):
    def __init__(self, prob: float = 0.8) -> None:
        self._prob = prob

    def predict_proba(self, X):
        return np.array([self._prob] * len(X))


_SCHEMA = {
    "features": [
        {"name": "watch_count_10min", "dtype": "int32"},
        {"name": "category_affinity_score", "dtype": "float64"},
        {"name": "avg_watch_duration", "dtype": "float64"},
        {"name": "recency_score", "dtype": "float64"},
        {"name": "time_of_day_bucket", "dtype": "categorical",
         "categories": ["morning", "afternoon", "evening", "night"]},
        {"name": "genre_action", "dtype": "float64"},
        {"name": "genre_drama", "dtype": "float64"},
    ],
    "genres": ["action", "drama"],
    "time_of_day_categories": ["morning", "afternoon", "evening", "night"],
}

_FEATURES = {
    "watch_count_10min": 5,
    "category_affinity_score": 0.7,
    "avg_watch_duration": 80.0,
    "recency_score": 0.6,
    "time_of_day_bucket": "evening",
    "session_genre_vector": json.dumps({"action": 0.7, "drama": 0.3}),
}


def _make_model(version: str = "42", prob: float = 0.8) -> LoadedModel:
    return LoadedModel(scorer=_FixedScorer(prob), schema=_SCHEMA, version=version)


@pytest.fixture
def privacy():
    mock = AsyncMock()
    mock.is_consent_granted = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def fetcher():
    mock = AsyncMock()
    mock.fetch = AsyncMock(return_value=_FEATURES.copy())
    return mock


@pytest.fixture
def model_store():
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=_make_model())
    return mock


@pytest.fixture
async def client(privacy, fetcher, model_store):
    """Set app.state directly and bypass the lifespan — no real connections needed."""
    settings = Settings()
    app.state.catalog = build_catalog(settings)
    app.state.trending = build_trending(settings, app.state.catalog)
    app.state.privacy = privacy
    app.state.fetcher = fetcher
    app.state.model_store = model_store

    # Do not use AsyncClient as a context manager — that triggers the lifespan
    # which would attempt real connections to Redis, MLflow, and the privacy service.
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield c
    await c.aclose()


# ---------------------------------------------------------------------------
# /recommend — happy path
# ---------------------------------------------------------------------------

async def test_personalized_response(client):
    r = await client.get("/recommend/user123?top_n=5")
    assert r.status_code == 200
    body = r.json()
    assert body["personalized"] is True
    assert body["model_version"] == "42"
    assert "fallback_reason" not in body
    assert len(body["recommendations"]) == 5
    for item in body["recommendations"]:
        assert "score" in item


async def test_recommendations_sorted_by_score(client):
    r = await client.get("/recommend/user123?top_n=10")
    scores = [item["score"] for item in r.json()["recommendations"]]
    assert scores == sorted(scores, reverse=True)


async def test_top_n_default_is_10(client):
    r = await client.get("/recommend/user123")
    assert r.status_code == 200
    assert len(r.json()["recommendations"]) == 10


# ---------------------------------------------------------------------------
# /recommend — fallback paths
# ---------------------------------------------------------------------------

async def test_consent_denied_returns_trending(client, privacy):
    privacy.is_consent_granted.return_value = False
    r = await client.get("/recommend/user123")
    body = r.json()
    assert body["personalized"] is False
    assert body["fallback_reason"] == "consent_denied"
    assert "model_version" not in body
    for item in body["recommendations"]:
        assert "score" not in item


async def test_cold_start_returns_trending(client, fetcher):
    fetcher.fetch.return_value = None
    r = await client.get("/recommend/user123")
    body = r.json()
    assert body["personalized"] is False
    assert body["fallback_reason"] == "cold_start"
    assert "model_version" not in body


async def test_model_unavailable_returns_trending(client, model_store):
    model_store.get.return_value = None
    r = await client.get("/recommend/user123")
    body = r.json()
    assert body["personalized"] is False
    assert body["fallback_reason"] == "model_unavailable"
    assert "model_version" not in body


# ---------------------------------------------------------------------------
# /recommend — input validation
# ---------------------------------------------------------------------------

async def test_top_n_zero_returns_422(client):
    r = await client.get("/recommend/user123?top_n=0")
    assert r.status_code == 422


async def test_top_n_above_max_returns_422(client):
    r = await client.get("/recommend/user123?top_n=101")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

async def test_health_includes_model_version(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["model_version"] == "42"


async def test_health_when_model_not_loaded(client, model_store):
    model_store.get.return_value = None
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json().get("model_version") is None
