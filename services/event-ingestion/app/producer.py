import json
import logging
from datetime import datetime

from confluent_kafka import Producer

logger = logging.getLogger(__name__)


def _delivery_callback(err, msg):
    # Called by librdkafka on the producer's background thread after each delivery attempt.
    # Failures are logged but never raised — ingestion uses fire-and-forget semantics:
    # the client already received 202 Accepted, so there is no request context to fail.
    if err:
        logger.error("Kafka delivery failed: topic=%s err=%s", msg.topic(), err)


class KafkaProducer:
    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})

    def publish(self, topic: str, payload: dict) -> None:
        value = json.dumps(payload, default=_serialize).encode()
        # `produce` is non-blocking — it enqueues the message in librdkafka's internal
        # buffer. `poll(0)` services the delivery callback queue without blocking,
        # so delivery failures are surfaced promptly without stalling the request.
        self._producer.produce(topic, value=value, callback=_delivery_callback)
        self._producer.poll(0)

    def flush(self) -> None:
        # Blocks until all buffered messages have been delivered or failed.
        # Called on shutdown to avoid silently dropping in-flight events.
        self._producer.flush()


def _serialize(obj):
    # json.dumps default handler. datetime objects appear in event payloads
    # (timestamp, start_time) and must be serialized as ISO 8601 strings so
    # the Flink consumer can parse them deterministically.
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
