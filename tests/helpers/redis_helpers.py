from __future__ import annotations

import asyncio
import time

import redis


def wait_for_redis_key(
    r: redis.Redis,
    key: str,
    *,
    timeout: float = 5.0,
    interval: float = 0.1,
) -> dict | None:
    """Synchronous blocking poll until a Redis hash key exists or timeout expires.

    Returns the hash dict on success, None on timeout.
    Pattern taken from feature-pipeline/tests/test_integration.py.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = r.hgetall(key)
        if data:
            return data
        time.sleep(interval)
    return None


async def poll_redis_key(
    r: redis.Redis,
    key: str,
    *,
    timeout: float = 5.0,
    interval: float = 0.1,
) -> dict | None:
    """Async poll until a Redis hash key exists or timeout expires.

    Uses the synchronous redis.Redis client (safe from async — no interleaved
    awaits inside the hgetall call) with asyncio.sleep between checks so the
    event loop remains cooperative.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = r.hgetall(key)
        if data:
            return data
        await asyncio.sleep(interval)
    return None
