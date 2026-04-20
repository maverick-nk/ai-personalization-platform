from __future__ import annotations

import redis as redis_lib
from pyflink.datastream import RichSinkFunction

from .config import Settings


class RedisSink(RichSinkFunction):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._client: redis_lib.Redis | None = None

    def open(self, runtime_context) -> None:
        # Deferred connection: RichSinkFunction instances may be pickled and shipped
        # to task managers, so the Redis client must be created after deserialization.
        self._client = redis_lib.Redis(
            host=self._settings.redis_host,
            port=self._settings.redis_port,
            decode_responses=True,
        )

    def write(self, record: dict) -> None:
        key = f"user:{record['pseudo_user_id']}:features"
        pipe = self._client.pipeline(transaction=False)
        pipe.hset(key, mapping=record)
        pipe.expire(key, self._settings.redis_feature_ttl_seconds)
        pipe.execute()

    def invoke(self, value, context) -> None:
        self.write(value)

    def close(self) -> None:
        if self._client:
            self._client.close()
