from __future__ import annotations

import asyncio
import os
import time

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from helpers.pseudonymize import pseudonymize

pytestmark = [pytest.mark.model_hotswap, pytest.mark.slow]

# How long to wait for the background poller to detect and apply the new version.
# Default poll interval is 30s; we allow 60s to cover load + download time.
_POLL_TIMEOUT = 60.0
_POLL_INTERVAL = 2.0


@pytest.fixture(scope="session")
def mlflow_url() -> str:
    return os.getenv("MLFLOW_URL", "http://localhost:5001")


@pytest.fixture(scope="session")
def mlflow_model_name() -> str:
    return os.getenv("INFERENCE_MLFLOW_MODEL_NAME", "personalization-click-model")


async def test_hot_swap_loads_new_version_without_dropped_requests(
    unique_user_id,
    inference_client,
    privacy_client,
    redis_client,
    pseudonym_secret,
    mlflow_url,
    mlflow_model_name,
):
    """A new model version registered in MLflow is picked up atomically without errors.

    Validates three guarantees of ModelStore:
    1. The background poller detects the new production alias within its poll interval.
    2. In-flight requests during the swap window complete without 5xx errors.
    3. After the swap, /health reports the new version — the (scorer, schema, version)
       triple was replaced atomically under asyncio.Lock.
    """
    # ── Arrange: record current version and ensure requests can reach the model ──
    health = await inference_client.health()
    current_version = health.get("model_version")
    if current_version is None:
        pytest.skip(
            "No model loaded in inference-api (model_version is null in /health) — "
            "run the model-training pipeline first to populate MLflow."
        )

    # Grant consent and write synthetic features so requests go through model scoring
    # (not just consent_denied / cold_start). This exercises the hot-swap lock path.
    r = await privacy_client.set_consent(unique_user_id, consent_granted=True)
    assert r.status_code == 200

    pseudo_id = pseudonymize(unique_user_id, pseudonym_secret)
    redis_key = f"user:{pseudo_id}:features"
    redis_client.hset(redis_key, mapping={
        "watch_count_10min": "5",
        "category_affinity_score": "0.7",
        "avg_watch_duration": "65.0",
        "time_of_day_bucket": "evening",
        "recency_score": "0.8",
        "session_genre_vector": '{"action": 1.0}',
        "pseudo_user_id": pseudo_id,
        "last_event_epoch": str(time.time() - 10),
        "computed_at_epoch": str(time.time() - 5),
    })
    redis_client.expire(redis_key, 3600)

    # Best-effort: verify requests reach the model scoring step before the swap.
    # If pseudonym secrets differ between the test runner and the inference-api container
    # (i.e. PSEUDONYMIZE_SECRET mismatch), the Redis key won't match and responses will
    # be cold_start — the swap test still runs, but scoring concurrency isn't exercised.
    r = await inference_client.recommend(unique_user_id)
    assert r.status_code == 200
    pre_swap_personalized = r.json()["personalized"]

    # ── Act: register a new model version by pointing a new registry entry at the
    # same run artifacts (same weights, different version number). The ModelStore
    # compares version strings; a new number triggers a swap even with identical weights.
    mlflow.set_tracking_uri(mlflow_url)
    client = MlflowClient()

    # Mirror ModelStore._resolve_version(): try production first, then staging.
    # Whichever alias is active, we promote the new version under the same alias
    # so the poller picks it up on the next cycle.
    active_mv, active_alias = None, None
    for alias in ("production", "staging"):
        try:
            active_mv = client.get_model_version_by_alias(mlflow_model_name, alias)
            active_alias = alias
            break
        except Exception:
            continue
    if active_mv is None:
        pytest.fail(
            f"No model version found under 'production' or 'staging' alias for "
            f"'{mlflow_model_name}'. Register a model first."
        )

    new_mv = mlflow.register_model(
        model_uri=f"runs:/{active_mv.run_id}/model",
        name=mlflow_model_name,
    )
    client.set_registered_model_alias(mlflow_model_name, active_alias, new_mv.version)

    # ── Poll: fire concurrent requests while waiting for the background swap ──────
    errors: list[tuple[int, str]] = []   # (status_code, fallback_reason)

    deadline = time.monotonic() + _POLL_TIMEOUT
    swapped = False
    while time.monotonic() < deadline:
        # Five concurrent recommendations — exercises the asyncio.Lock under load
        responses = await asyncio.gather(
            *[inference_client.recommend(unique_user_id) for _ in range(5)]
        )
        for resp in responses:
            if resp.status_code >= 500:
                errors.append((resp.status_code, resp.text[:120]))

        health = await inference_client.health()
        if health.get("model_version") == str(new_mv.version):
            swapped = True
            break

        await asyncio.sleep(_POLL_INTERVAL)

    # ── Assert ───────────────────────────────────────────────────────────────────
    assert errors == [], (
        f"{len(errors)} server error(s) during hot-swap window: {errors}"
    )
    assert swapped, (
        f"inference-api did not swap to model v{new_mv.version} within {_POLL_TIMEOUT}s "
        f"(alias '{active_alias}' promoted). "
        f"Current /health model_version={(await inference_client.health()).get('model_version')!r}. "
        "Check INFERENCE_MODEL_POLL_INTERVAL_SECONDS in docker-compose."
    )

    # One final request after the swap must succeed with no errors.
    # If pre_swap_personalized was True (secrets matched), assert personalization
    # is still intact — scoring path was exercised through the swap window.
    r = await inference_client.recommend(unique_user_id)
    assert r.status_code == 200
    body = r.json()
    if pre_swap_personalized:
        assert body["personalized"] is True, (
            "Post-swap request should still be personalized — model swap broke the scorer."
        )
        assert body["model_version"] == str(new_mv.version), (
            f"Expected new model v{new_mv.version} in response, got {body.get('model_version')!r}."
        )
