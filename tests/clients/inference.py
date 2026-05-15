from __future__ import annotations

import time

import httpx


class InferenceClient:
    def __init__(self, base_url: str) -> None:
        # 10s timeout: latency tests fire many sequential requests; individual
        # calls stay well under SLO but the client timeout must not interfere.
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def recommend(self, user_id: str, top_n: int = 10) -> httpx.Response:
        """GET /recommend/{user_id}. Returns raw response — caller asserts."""
        return await self._client.get(
            f"/recommend/{user_id}", params={"top_n": top_n}
        )

    async def recommend_timed(
        self, user_id: str, top_n: int = 10
    ) -> tuple[httpx.Response, float]:
        """Returns (response, elapsed_seconds). Building block for latency tests."""
        t0 = time.monotonic()
        response = await self.recommend(user_id, top_n)
        elapsed = time.monotonic() - t0
        return response, elapsed

    async def health(self) -> dict:
        r = await self._client.get("/health")
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()
