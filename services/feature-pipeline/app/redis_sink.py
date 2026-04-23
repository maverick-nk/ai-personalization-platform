from __future__ import annotations

import logging

import redis as redis_lib

from .config import Settings

log = logging.getLogger(__name__)


class RedisSink:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: redis_lib.Redis | None = None

    def open(self, runtime_context) -> None:
        # Connection is created here rather than in __init__ because
        # RichSinkFunction instances are pickled before being shipped to Flink
        # task managers. A live socket cannot survive pickling, so we defer
        # until after deserialization when open() is called on the worker.
        self._client = redis_lib.Redis(
            host=self._settings.redis_host,
            port=self._settings.redis_port,
            decode_responses=True,
        )

    def write(self, record: dict) -> None:
        key = f"user:{record['pseudo_user_id']}:features"
        # Redis hash values must be strings. Convert here so callers can pass
        # typed records without caring about Redis encoding requirements.
        str_record = {k: str(v) for k, v in record.items()}
        try:
            # Pipeline batches hset + expire into a single round-trip. transaction=False
            # skips MULTI/EXEC — atomicity is not required here because a partial write
            # (hash without TTL) gets repaired on the next event for the same user.
            pipe = self._client.pipeline(transaction=False)
            pipe.hset(key, mapping=str_record)
            pipe.expire(key, self._settings.redis_feature_ttl_seconds)
            pipe.execute()
        except Exception:
            # Log and continue — a single failed Redis write is not worth crashing the
            # pipeline over. The next event for this user will overwrite the key anyway.
            log.exception("Failed to write features to Redis for key %s", key)

    def close(self) -> None:
        if self._client:
            self._client.close()
