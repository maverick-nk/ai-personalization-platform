from __future__ import annotations

import httpx


class SyncPrivacyClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=10.0)

    def set_consent(
        self,
        user_id: str,
        consent_granted: bool,
        reason: str | None = None,
    ) -> httpx.Response:
        """PATCH /privacy/consent/{user_id}. Returns raw response — caller asserts."""
        payload: dict = {"consent_granted": consent_granted}
        if reason is not None:
            payload["reason"] = reason
        return self._client.patch(f"/privacy/consent/{user_id}", json=payload)

    def get_audit(self, user_id: str) -> list[dict]:
        """GET /privacy/audit/{user_id}. Returns parsed JSON list."""
        r = self._client.get(f"/privacy/audit/{user_id}")
        r.raise_for_status()
        return r.json()

    def health(self) -> dict:
        r = self._client.get("/health")
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()
