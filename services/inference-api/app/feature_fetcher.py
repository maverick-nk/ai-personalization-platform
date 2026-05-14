from __future__ import annotations

import logging

import redis.asyncio as aioredis

log = logging.getLogger(__name__)

# All Redis hash values are stored as strings by the feature pipeline.
# We cast them back here so the scorer gets typed data.
_INT_FIELDS = {"watch_count_10min"}
_STR_FIELDS = {"time_of_day_bucket", "session_genre_vector", "pseudo_user_id"}


class FeatureFetcher:
    def __init__(self, host: str, port: int, socket_timeout: float) -> None:
        self._host = host
        self._port = port
        self._socket_timeout = socket_timeout
        self._client: aioredis.Redis | None = None

    def start(self) -> None:
        self._client = aioredis.Redis(
            host=self._host,
            port=self._port,
            decode_responses=True,
            socket_timeout=self._socket_timeout,
            socket_connect_timeout=self._socket_timeout,
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    async def fetch(self, pseudo_id: str) -> dict | None:
        """Return the user's feature hash from Redis, or None on miss or error.

        None → caller should use the cold-start trending fallback.
        """
        if self._client is None:
            log.error("FeatureFetcher used before start() was called")
            return None
        key = f"user:{pseudo_id}:features"
        try:
            raw: dict = await self._client.hgetall(key)
        except Exception:
            log.warning("Redis fetch failed for key %s", key)
            return None

        if not raw:
            return None

        return _cast(raw)


def _cast(raw: dict[str, str]) -> dict[str, int | str | float]:
    result: dict[str, int | str | float] = {}
    for k, v in raw.items():
        if k in _INT_FIELDS:
            try:
                result[k] = int(v)
            except ValueError:
                log.warning("Expected int for field '%s', got %r — defaulting to 0", k, v)
                result[k] = 0
        elif k in _STR_FIELDS:
            result[k] = v
        else:
            try:
                result[k] = float(v)
            except ValueError:
                log.warning("Expected float for field '%s', got %r — defaulting to 0.0", k, v)
                result[k] = 0.0
    return result
