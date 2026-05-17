from __future__ import annotations

import httpx
import pytest
from app.privacy_client import PrivacyClient


@pytest.fixture
async def client():
    c = PrivacyClient(base_url="http://privacy:8001", timeout_seconds=0.003)
    await c.start()
    yield c
    await c.stop()


async def test_consent_granted(client: PrivacyClient, respx_mock):
    respx_mock.get("http://privacy:8001/internal/consent/check/abc123").mock(
        return_value=httpx.Response(200, json={"consent_granted": True})
    )
    assert await client.is_consent_granted("abc123") is True


async def test_consent_denied(client: PrivacyClient, respx_mock):
    respx_mock.get("http://privacy:8001/internal/consent/check/abc123").mock(
        return_value=httpx.Response(200, json={"consent_granted": False})
    )
    assert await client.is_consent_granted("abc123") is False


async def test_non_200_treated_as_denied(client: PrivacyClient, respx_mock):
    respx_mock.get("http://privacy:8001/internal/consent/check/abc123").mock(
        return_value=httpx.Response(503)
    )
    assert await client.is_consent_granted("abc123") is False


async def test_timeout_treated_as_denied(client: PrivacyClient, respx_mock):
    respx_mock.get("http://privacy:8001/internal/consent/check/abc123").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    assert await client.is_consent_granted("abc123") is False


async def test_connection_error_treated_as_denied(client: PrivacyClient, respx_mock):
    respx_mock.get("http://privacy:8001/internal/consent/check/abc123").mock(
        side_effect=httpx.ConnectError("refused")
    )
    assert await client.is_consent_granted("abc123") is False
