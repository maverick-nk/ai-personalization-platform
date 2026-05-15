from __future__ import annotations

import pytest

from helpers.latency import assert_p95

pytestmark = pytest.mark.latency

_N = 25  # request count — enough for a stable p95


async def test_consent_denied_path_p95_under_50ms(unique_user_id, inference_client):
    """p95 end-to-end latency for the consent-denied fast path is under the 50ms SLO.

    A user with no consent record triggers the shortest code path through the
    inference-api: consent check (Postgres) → return trending. No Redis lookup.
    This is the tightest benchmark against the SLO.
    """
    latencies: list[float] = []
    for _ in range(_N):
        _, elapsed = await inference_client.recommend_timed(unique_user_id)
        latencies.append(elapsed)

    assert_p95(latencies, max_seconds=0.050, label="consent-denied recommendation")


@pytest.mark.slow
async def test_cold_start_path_p95_under_50ms(
    unique_user_id, inference_client, privacy_client
):
    """p95 end-to-end latency for the cold-start path is under the 50ms SLO.

    Consent check (Postgres) + Redis HGETALL miss — more representative of a real
    user who has consent but no watch history yet. Marked slow: 25 sequential requests.
    """
    r = await privacy_client.set_consent(unique_user_id, consent_granted=True)
    assert r.status_code == 200

    latencies: list[float] = []
    for _ in range(_N):
        _, elapsed = await inference_client.recommend_timed(unique_user_id)
        latencies.append(elapsed)

    assert_p95(latencies, max_seconds=0.050, label="cold-start recommendation")
