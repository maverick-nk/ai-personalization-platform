"""
Integration tests — require:
  - Kafka at localhost:29092  (docker-compose up kafka)
  - Redis at localhost:6379   (docker-compose up redis)
  - Java 11/17/21 in PATH and JAVA_HOME set

Run:
  JAVA_HOME="$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home" \\
  uv run pytest tests/test_integration.py -v -s
"""

import json
import shutil
import threading
import time
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not shutil.which("java"),
    reason="Java not found in PATH — PyFlink requires a JVM",
)

KAFKA_BOOTSTRAP = "localhost:29092"
REDIS_HOST = "localhost"
WATCH_TOPIC = "user.watch.events"
TEST_PARQUET_PATH = "/tmp/test_parquet_feature_pipeline"


@pytest.fixture(scope="module")
def pipeline_thread():
    from pyflink.datastream import StreamExecutionEnvironment

    from app.config import Settings
    from app.pipeline import _find_kafka_connector_jar, build_pipeline

    cfg = Settings(
        kafka_bootstrap_servers=KAFKA_BOOTSTRAP,
        redis_host=REDIS_HOST,
        parquet_base_path=TEST_PARQUET_PATH,
        parquet_flush_interval_seconds=5,
        parquet_flush_batch_size=10,
    )

    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    connector_jar = _find_kafka_connector_jar()
    if connector_jar:
        env.add_jars(f"file://{connector_jar}")

    build_pipeline(env, settings=cfg)

    t = threading.Thread(
        target=lambda: env.execute("test-feature-pipeline"),
        daemon=True,
    )
    t.start()
    time.sleep(3)  # wait for consumer group registration
    yield
    # daemon thread exits automatically when the test session ends


def _publish(payload: dict) -> None:
    from confluent_kafka import Producer

    p = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    p.produce(WATCH_TOPIC, json.dumps(payload, default=str).encode())
    p.flush()


def _poll_redis(key: str, deadline_seconds: float = 5.0):
    import redis

    r = redis.Redis(host=REDIS_HOST, decode_responses=True)
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if r.exists(key):
            return r.hgetall(key)
        time.sleep(0.1)
    return None


def test_watch_event_appears_in_redis_within_2s(pipeline_thread):
    pseudo_user_id = f"test-{uuid.uuid4().hex[:8]}"
    _publish({
        "pseudo_user_id": pseudo_user_id,
        "content_id": "mov-001",
        "watch_pct": 75.0,
        "timestamp": "2026-04-19T10:00:00Z",
        "genre": "action",
    })

    publish_time = time.monotonic()
    key = f"user:{pseudo_user_id}:features"
    features = _poll_redis(key, deadline_seconds=5.0)

    elapsed = time.monotonic() - publish_time
    assert features is not None, f"Redis key {key!r} did not appear within 5s"
    assert elapsed < 2.0, f"Feature write took {elapsed:.2f}s — exceeds 2s SLO"


def test_redis_feature_record_has_all_fields(pipeline_thread):
    pseudo_user_id = f"test-{uuid.uuid4().hex[:8]}"
    _publish({
        "pseudo_user_id": pseudo_user_id,
        "content_id": "mov-002",
        "watch_pct": 50.0,
        "timestamp": "2026-04-19T14:30:00Z",
        "genre": "drama",
    })

    key = f"user:{pseudo_user_id}:features"
    features = _poll_redis(key, deadline_seconds=5.0)

    assert features is not None, f"Redis key {key!r} did not appear within 5s"

    expected_fields = {
        "watch_count_10min",
        "category_affinity_score",
        "avg_watch_duration",
        "time_of_day_bucket",
        "recency_score",
        "session_genre_vector",
        "pseudo_user_id",
        "last_event_epoch",
        "computed_at_epoch",
    }
    assert expected_fields.issubset(set(features.keys()))
    assert features["time_of_day_bucket"] == "afternoon"
    assert features["pseudo_user_id"] == pseudo_user_id
    assert int(features["watch_count_10min"]) == 1


def test_parquet_file_written_after_flush(pipeline_thread):
    pseudo_user_id = f"parquet-{uuid.uuid4().hex[:8]}"

    for i in range(10):
        _publish({
            "pseudo_user_id": pseudo_user_id,
            "content_id": f"mov-{i:03d}",
            "watch_pct": float(i * 10),
            "timestamp": "2026-04-19T10:00:00Z",
            "genre": "comedy",
        })

    parquet_base = Path(TEST_PARQUET_PATH)
    deadline = time.monotonic() + 15.0
    found_files: list[Path] = []
    while time.monotonic() < deadline:
        found_files = list(parquet_base.rglob("*.parquet"))
        if found_files:
            break
        time.sleep(0.5)

    assert found_files, f"No Parquet files written to {TEST_PARQUET_PATH} within 15s"

    import pyarrow.parquet as pq
    table = pq.read_table(found_files[0])
    assert "pseudo_user_id" in table.schema.names
    assert "watch_count_10min" in table.schema.names
    assert "session_genre_vector" in table.schema.names
