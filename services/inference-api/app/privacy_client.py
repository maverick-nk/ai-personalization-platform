from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class PrivacyClient:
    """Thin async client for the privacy service internal consent-check endpoint."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._url = base_url.rstrip("/") + "/internal/consent/check"
        # Timeout is kept very tight — the privacy call is on the critical path
        # and must complete well within the 50ms e2e budget (ADR 0007).
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    async def is_consent_granted(self, pseudo_id: str) -> bool:
        """Return True only when the privacy service explicitly grants consent.

        Any error — timeout, connection refused, non-200 response — is treated as
        denied (fail-closed). This matches ADR 0007: silence from the consent gate
        is never treated as permission.
        """
        if self._client is None:
            log.error("PrivacyClient used before start() was called")
            return False
        try:
            response = await self._client.get(f"{self._url}/{pseudo_id}")
            if response.status_code != 200:
                log.warning(
                    "Privacy service returned %d for pseudo_id=%.8s…",
                    response.status_code, pseudo_id,
                )
                return False
            data = response.json()
            return bool(data.get("consent_granted", False))
        except Exception:
            log.warning("Privacy service unreachable for pseudo_id=%.8s… — failing closed", pseudo_id)
            return False
