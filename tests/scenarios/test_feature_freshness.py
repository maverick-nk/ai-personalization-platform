from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from helpers.pseudonymize import pseudonymize
from helpers.redis_helpers import poll_redis_key

pytestmark = [pytest.mark.feature_freshness, pytest.mark.slow]


@pytest.fixture(autouse=True)
def require_feature_pipeline(feature_pipeline_available):
    if not feature_pipeline_available:
        pytest.skip(
            "Feature pipeline (Flink) not running — "
            "set FEATURE_PIPELINE_ENABLED=true to enable these tests"
        )


async def test_redis_feature_freshness_under_5s(
    unique_user_id,
    event_client,
    redis_client,
    pseudonym_secret,
):
    """Features written to Redis are no more than 5s old at read time.

    computed_at_epoch is the wall-clock time on the Flink worker when the feature
    vector was computed. The test host and Flink container share Docker's clock,
    so comparing against time.time() at read time gives a valid freshness bound.

    Flow: watch event → Kafka → Flink → Redis write → assert age < 5s.
    """
    pseudo_id = pseudonymize(unique_user_id, pseudonym_secret)
    redis_key = f"user:{pseudo_id}:features"

    r = await event_client.watch(
        user_id=unique_user_id,
        content_id="content-freshness-check",
        watch_pct=80.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
        genre="Action",
    )
    assert r.status_code == 202

    # Poll up to 10s — Flink should write within 2s, 10s is the hard ceiling
    features = await poll_redis_key(redis_client, redis_key, timeout=10.0)
    assert features is not None, (
        f"Feature key {redis_key!r} not written to Redis within 10s of the watch event. "
        "Is the feature pipeline running?"
    )

    computed_at = float(features["computed_at_epoch"])
    age_seconds = time.time() - computed_at
    assert age_seconds < 5.0, (
        f"Feature freshness {age_seconds:.2f}s exceeds 5s SLO "
        f"(computed_at={computed_at:.3f}, now={time.time():.3f})"
    )
