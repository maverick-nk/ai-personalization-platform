from __future__ import annotations

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from uuid import uuid4

import gevent
from locust import User, between, task

from tests.clients.sync_event_ingestion import SyncEventIngestionClient
from tests.clients.sync_inference import SyncInferenceClient
from tests.clients.sync_privacy import SyncPrivacyClient
from tests.helpers.pseudonymize import pseudonymize
from tests.simulation.config import Suite
from tests.simulation.shapes import (
    DynamicLoadShape,  # noqa: F401 — Locust discovers shape classes by import
)

logger = logging.getLogger(__name__)

_CATALOG = [f"content-{i:03d}" for i in range(1, 21)]


def _load_suite() -> Suite:
    raw = os.environ.get("SUITE_CONFIG")
    if not raw:
        raise RuntimeError("SUITE_CONFIG not set")
    return Suite.model_validate(json.loads(raw))


def _weighted_genre(distribution: dict[str, float]) -> str:
    genres, weights = zip(*distribution.items())
    return random.choices(genres, weights=weights, k=1)[0]


class PersonalizedUser(User):
    tasks = []  # populated via @task decorators below
    wait_time = between(1, 3)  # fallback; actual sleep uses expovariate in each task

    # Shape drives user count — wait_time is overridden per-task.
    abstract = False

    def on_start(self) -> None:
        secret = os.environ.get("PSEUDONYMIZE_SECRET", "")
        if not secret:
            raise RuntimeError("PSEUDONYMIZE_SECRET is required")

        raw_id = f"sim-{uuid4().hex[:12]}"
        self.user_id = pseudonymize(raw_id, secret)
        self._suite = _load_suite()
        self._behavior = self._suite.user_behavior
        self._consent_granted = False

        ei_url = os.environ.get("EVENT_INGESTION_URL", "http://localhost:8000")
        inf_url = os.environ.get("INFERENCE_URL", "http://localhost:8002")
        priv_url = os.environ.get("PRIVACY_URL", "http://localhost:8001")

        self._ei = SyncEventIngestionClient(ei_url)
        self._inf = SyncInferenceClient(inf_url)
        self._priv = SyncPrivacyClient(priv_url)

        # Grant consent so most users receive personalized recommendations.
        self._call("consent_grant", "PATCH", self._priv.set_consent, self.user_id, True)
        self._consent_granted = True

    def on_stop(self) -> None:
        self._ei.close()
        self._inf.close()
        self._priv.close()

    # ── helpers ─────────────────────────────────────────────────────────────

    def _call(self, name: str, method: str, fn, *args, **kwargs):
        """Time fn(*args, **kwargs), fire a Locust request event, return response."""
        t0 = time.monotonic()
        exc = None
        response = None
        try:
            response = fn(*args, **kwargs)
            if not response.is_success:
                exc = Exception(f"HTTP {response.status_code}")
                logger.warning("User %s: %s returned %s", self.user_id, name, response.status_code)
        except Exception as e:
            exc = e
            logger.warning("User %s: %s failed — %s", self.user_id, name, e)
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            self.environment.events.request.fire(
                request_type=method,
                name=name,
                response_time=elapsed_ms,
                response_length=len(response.content) if response is not None else 0,
                exception=exc,
                context={},
            )
        return response

    def _sleep(self) -> None:
        gevent.sleep(random.expovariate(1.0 / self._behavior.session_length_mean_s))

    # ── tasks ────────────────────────────────────────────────────────────────

    @task(7)
    def watch(self) -> None:
        content_id = random.choice(_CATALOG)
        watch_pct = round(random.uniform(5.0, 100.0), 1)
        genre = _weighted_genre(self._behavior.genre_distribution)
        ts = datetime.now(timezone.utc).isoformat()
        self._call("watch", "POST", self._ei.watch, self.user_id, content_id, watch_pct, ts, genre)
        self._sleep()

    @task(3)
    def recommend(self) -> None:
        self._call("recommend", "GET", self._inf.recommend, self.user_id)
        self._sleep()

    @task(1)
    def toggle_consent(self) -> None:
        if self._behavior.consent_revoke_probability <= 0:
            return
        if random.random() > self._behavior.consent_revoke_probability:
            return
        new_state = not self._consent_granted
        self._call("consent_toggle", "PATCH", self._priv.set_consent, self.user_id, new_state)
        self._consent_granted = new_state
        self._sleep()
