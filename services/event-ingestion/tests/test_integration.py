"""
Integration tests — require Kafka running (./scripts/start-infra.sh).
Run with: PSEUDONYMIZE_SECRET=test-secret uv run pytest tests/test_integration.py -v
"""

import json
import os
import time
import uuid

import pytest
from confluent_kafka import Consumer, KafkaError
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.skipif(
    not os.getenv("PSEUDONYMIZE_SECRET"),
    reason="PSEUDONYMIZE_SECRET not set — skipping integration tests",
)


@pytest.fixture(scope="session", autouse=True)
def ensure_topics():
    """Pre-create Kafka topics before any test runs.

    Auto-create only triggers when a producer first publishes. If a consumer
    subscribes before the topic exists it gets no partition assignment, causing
    the message sent by the producer to be missed under auto.offset.reset=latest.
    Creating topics upfront eliminates that race entirely.
    """
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": TEST_KAFKA})
    topics = [
        NewTopic("user.watch.events", num_partitions=1, replication_factor=1),
        NewTopic("user.session.events", num_partitions=1, replication_factor=1),
    ]
    futures = admin.create_topics(topics)
    for topic, future in futures.items():
        try:
            future.result()
        except Exception:
            pass  # topic already exists — that's fine

# Always use the host-exposed port. Docker-internal hostnames (kafka:9092) are
# not reachable from the host where tests run.
TEST_KAFKA = "localhost:29092"
SECRET = os.getenv("PSEUDONYMIZE_SECRET", "")  # noqa: S105


@pytest.fixture
def kafka_consumer():
    group_id = f"test-{uuid.uuid4().hex}"
    consumer = Consumer(
        {
            "bootstrap.servers": TEST_KAFKA,
            "group.id": group_id,
            # earliest: consumer reads from the start of the partition so it never
            # misses a message due to the lazy offset-fetch window under `latest`.
            # Each test uses a UUID-based user_id so matching on pseudo_user_id
            # ensures we find the right message even if old ones are present.
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    yield consumer
    consumer.close()


@pytest.fixture
async def client():
    from app.main import app
    from app.producer import KafkaProducer

    # ASGITransport does not trigger the FastAPI lifespan, so app.state.producer is
    # never set. Assign it directly here with the test-accessible address.
    app.state.producer = KafkaProducer(TEST_KAFKA)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.state.producer.flush()


@pytest.mark.asyncio
async def test_watch_event_reaches_kafka(client, kafka_consumer):
    from app.pseudonymize import pseudonymize

    user_id = f"integration-user-{uuid.uuid4().hex}"
    expected_pseudo = pseudonymize(user_id, SECRET)

    kafka_consumer.subscribe(["user.watch.events"])

    response = await client.post(
        "/events/watch",
        json={
            "user_id": user_id,
            "content_id": "mov-integration-1",
            "watch_pct": 42.5,
            "timestamp": "2026-04-18T10:00:00Z",
            "genre": "action",
        },
    )
    assert response.status_code == 202

    # Scan all messages until we find the one matching this test's pseudo_user_id.
    # auto.offset.reset=earliest means old messages may appear first; the UUID-based
    # user_id guarantees the expected_pseudo is unique across runs.
    msg = None
    deadline = time.time() + 10
    while time.time() < deadline:
        m = kafka_consumer.poll(0.5)
        if m is None:
            continue
        if m.error() and m.error().code() != KafkaError._PARTITION_EOF:
            pytest.fail(f"Kafka consumer error: {m.error()}")
        if m.value():
            parsed = json.loads(m.value())
            if parsed.get("pseudo_user_id") == expected_pseudo:
                msg = parsed
                break

    assert msg is not None, "No message received on user.watch.events within timeout"
    assert "user_id" not in msg, "Raw user_id must not appear in Kafka message"
    assert msg["pseudo_user_id"] == expected_pseudo
    assert msg["content_id"] == "mov-integration-1"
    assert msg["watch_pct"] == 42.5
    assert msg["genre"] == "action"


@pytest.mark.asyncio
async def test_session_event_reaches_kafka(client, kafka_consumer):
    from app.pseudonymize import pseudonymize

    user_id = f"integration-user-{uuid.uuid4().hex}"
    expected_pseudo = pseudonymize(user_id, SECRET)

    kafka_consumer.subscribe(["user.session.events"])

    response = await client.post(
        "/events/session",
        json={
            "user_id": user_id,
            "session_id": "sess-001",
            "device": "smart-tv",
            "start_time": "2026-04-18T09:00:00Z",
        },
    )
    assert response.status_code == 202

    msg = None
    deadline = time.time() + 10
    while time.time() < deadline:
        m = kafka_consumer.poll(0.5)
        if m is None:
            continue
        if m.error() and m.error().code() != KafkaError._PARTITION_EOF:
            pytest.fail(f"Kafka consumer error: {m.error()}")
        if m.value():
            parsed = json.loads(m.value())
            if parsed.get("pseudo_user_id") == expected_pseudo:
                msg = parsed
                break

    assert msg is not None, "No message received on user.session.events within timeout"
    assert "user_id" not in msg
    assert msg["pseudo_user_id"] == expected_pseudo
    assert msg["session_id"] == "sess-001"
    assert msg["device"] == "smart-tv"


@pytest.mark.asyncio
async def test_watch_event_without_genre_reaches_kafka(client, kafka_consumer):
    from app.pseudonymize import pseudonymize

    user_id = f"integration-user-{uuid.uuid4().hex}"
    expected_pseudo = pseudonymize(user_id, SECRET)

    kafka_consumer.subscribe(["user.watch.events"])

    response = await client.post(
        "/events/watch",
        json={
            "user_id": user_id,
            "content_id": "mov-no-genre",
            "watch_pct": 10.0,
            "timestamp": "2026-04-18T10:00:00Z",
        },
    )
    assert response.status_code == 202

    msg = None
    deadline = time.time() + 10
    while time.time() < deadline:
        m = kafka_consumer.poll(0.5)
        if m is None:
            continue
        if m.error() and m.error().code() != KafkaError._PARTITION_EOF:
            pytest.fail(f"Kafka consumer error: {m.error()}")
        if m.value():
            parsed = json.loads(m.value())
            if parsed.get("pseudo_user_id") == expected_pseudo:
                msg = parsed
                break

    assert msg is not None, "No message received on user.watch.events within timeout"
    assert msg.get("genre") is None


@pytest.mark.asyncio
async def test_malformed_watch_event_rejected(client):
    response = await client.post(
        "/events/watch",
        json={"user_id": "u1", "content_id": "c1", "watch_pct": 150.0, "timestamp": "2026-04-18T10:00:00Z"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
