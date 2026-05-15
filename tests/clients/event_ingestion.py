from __future__ import annotations

import httpx


class EventIngestionClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def watch(
        self,
        user_id: str,
        content_id: str,
        watch_pct: float,
        timestamp: str,
        genre: str | None = None,
    ) -> httpx.Response:
        """POST /events/watch. Returns raw response — caller asserts status."""
        payload: dict = {
            "user_id": user_id,
            "content_id": content_id,
            "watch_pct": watch_pct,
            "timestamp": timestamp,
        }
        if genre is not None:
            payload["genre"] = genre
        return await self._client.post("/events/watch", json=payload)

    async def health(self) -> dict:
        r = await self._client.get("/health")
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()
