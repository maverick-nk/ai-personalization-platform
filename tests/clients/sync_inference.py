from __future__ import annotations

import time

import httpx


class SyncInferenceClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=10.0)

    def recommend(self, user_id: str, top_n: int = 10) -> httpx.Response:
        """GET /recommend/{user_id}. Returns raw response — caller asserts."""
        return self._client.get(f"/recommend/{user_id}", params={"top_n": top_n})

    def recommend_timed(self, user_id: str, top_n: int = 10) -> tuple[httpx.Response, float]:
        """Returns (response, elapsed_seconds). Building block for latency tests."""
        t0 = time.monotonic()
        response = self.recommend(user_id, top_n)
        elapsed = time.monotonic() - t0
        return response, elapsed

    def health(self) -> dict:
        r = self._client.get("/health")
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()
