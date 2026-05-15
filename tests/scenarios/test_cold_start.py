from __future__ import annotations

import pytest

pytestmark = pytest.mark.cold_start


async def test_no_consent_record_returns_consent_denied(unique_user_id, inference_client):
    """A brand-new user with no consent record gets consent_denied.

    Privacy is fail-closed: consent defaults to False when no record exists in Postgres.
    The inference-api never reaches the Redis lookup.
    """
    r = await inference_client.recommend(unique_user_id)
    assert r.status_code == 200
    body = r.json()
    assert body["personalized"] is False
    assert body["fallback_reason"] == "consent_denied"
    assert len(body["recommendations"]) > 0


async def test_consent_granted_no_features_returns_cold_start(
    unique_user_id, inference_client, privacy_client
):
    """A user with consent but no watch history gets the cold-start trending fallback.

    The inference-api passes the consent gate but finds no feature vector in Redis
    for this user — Redis miss triggers cold_start.
    """
    r = await privacy_client.set_consent(unique_user_id, consent_granted=True)
    assert r.status_code == 200

    r = await inference_client.recommend(unique_user_id)
    assert r.status_code == 200
    body = r.json()
    assert body["personalized"] is False
    assert body["fallback_reason"] == "cold_start"
    assert len(body["recommendations"]) > 0
    assert body["user_id"] == unique_user_id
