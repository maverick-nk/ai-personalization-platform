from __future__ import annotations

import os
import uuid

import pytest
import redis

from clients import EventIngestionClient, InferenceClient, PrivacyClient

# ---------------------------------------------------------------------------
# Skip gate — applied to every test in this harness.
# Matches the pattern used in event-ingestion and privacy integration tests.
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    not os.getenv("PSEUDONYMIZE_SECRET"),
    reason=(
        "PSEUDONYMIZE_SECRET not set — start infra and export env vars "
        "before running e2e tests (see tests/TESTING.md)"
    ),
)


# ---------------------------------------------------------------------------
# URL and connection configuration — session scoped, overridable via env vars
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pseudonym_secret() -> str:
    return os.environ["PSEUDONYMIZE_SECRET"]


@pytest.fixture(scope="session")
def event_ingestion_url() -> str:
    return os.getenv("EVENT_INGESTION_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def inference_url() -> str:
    return os.getenv("INFERENCE_URL", "http://localhost:8002")


@pytest.fixture(scope="session")
def privacy_url() -> str:
    return os.getenv("PRIVACY_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def redis_host() -> str:
    return os.getenv("REDIS_HOST", "localhost")


@pytest.fixture(scope="session")
def redis_port() -> int:
    return int(os.getenv("REDIS_PORT", "6379"))


# ---------------------------------------------------------------------------
# Infrastructure clients — session scoped (one connection pool per session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def redis_client(redis_host, redis_port) -> redis.Redis:
    """Synchronous Redis client for direct feature-store assertions."""
    client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    yield client
    client.close()


@pytest.fixture(scope="session")
async def event_client(event_ingestion_url) -> EventIngestionClient:
    client = EventIngestionClient(base_url=event_ingestion_url)
    yield client
    await client.aclose()


@pytest.fixture(scope="session")
async def inference_client(inference_url) -> InferenceClient:
    client = InferenceClient(base_url=inference_url)
    yield client
    await client.aclose()


@pytest.fixture(scope="session")
async def privacy_client(privacy_url) -> PrivacyClient:
    client = PrivacyClient(base_url=privacy_url)
    yield client
    await client.aclose()


# ---------------------------------------------------------------------------
# Test isolation
# ---------------------------------------------------------------------------

@pytest.fixture
def unique_user_id() -> str:
    """Fresh UUID-based user ID per test — no cleanup needed.

    The e2e- prefix makes test-generated Redis keys visually distinguishable
    during debugging. The HMAC digest is unguessable, so orphaned keys after a
    test run are harmless.
    """
    return f"e2e-{uuid.uuid4().hex[:12]}"
