from __future__ import annotations

from datetime import datetime, timezone

import pytest

from helpers.pseudonymize import pseudonymize
from helpers.redis_helpers import poll_redis_key

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


@pytest.fixture(autouse=True)
def require_feature_pipeline(feature_pipeline_available):
    if not feature_pipeline_available:
        pytest.skip(
            "Feature pipeline (Flink) not running — "
            "set FEATURE_PIPELINE_ENABLED=true to enable these tests"
        )


async def test_watch_event_appears_in_redis_within_5s(
    unique_user_id,
    event_client,
    redis_client,
    pseudonym_secret,
):
    """A watch event published to Kafka triggers a Redis feature update within 5s.

    Validates the full streaming path: event-ingestion → Kafka → Flink → Redis.
    The feature key must appear within the 5s feature-freshness SLO.
    """
    pseudo_id = pseudonymize(unique_user_id, pseudonym_secret)
    redis_key = f"user:{pseudo_id}:features"

    r = await event_client.watch(
        user_id=unique_user_id,
        content_id="content-propagation-test",
        watch_pct=75.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
        genre="Drama",
    )
    assert r.status_code == 202

    features = await poll_redis_key(redis_client, redis_key, timeout=5.0)
    assert features is not None, (
        f"Feature key {redis_key!r} not written to Redis within 5s after watch event. "
        "Check Kafka topic, Flink job, and Redis connectivity."
    )
    assert float(features["watch_count_10min"]) >= 1


async def test_genre_watch_updates_session_genre_vector(
    unique_user_id,
    event_client,
    redis_client,
    pseudonym_secret,
):
    """Watching genre-specific content updates the session_genre_vector feature.

    The session_genre_vector accumulates genre affinity weighted by watch_pct.
    After watching an Action title, the stored vector must reference 'Action'.
    """
    pseudo_id = pseudonymize(unique_user_id, pseudonym_secret)
    redis_key = f"user:{pseudo_id}:features"

    r = await event_client.watch(
        user_id=unique_user_id,
        content_id="content-genre-test",
        watch_pct=90.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
        genre="Action",
    )
    assert r.status_code == 202

    features = await poll_redis_key(redis_client, redis_key, timeout=5.0)
    assert features is not None, (
        f"Feature key {redis_key!r} not written to Redis within 5s. "
        "Is the feature pipeline running?"
    )
    assert "Action" in features["session_genre_vector"]
