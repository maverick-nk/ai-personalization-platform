from __future__ import annotations

import pytest

pytestmark = pytest.mark.consent


async def test_revocation_takes_effect_immediately(
    unique_user_id, inference_client, privacy_client
):
    """Revoking consent causes consent_denied on the very next recommendation request.

    The inference-api checks the privacy service on every call with no caching —
    revocation must take effect before the next inference request completes.
    """
    # Grant — passes consent gate, cold_start because no features in Redis
    r = await privacy_client.set_consent(unique_user_id, consent_granted=True)
    assert r.status_code == 200

    r = await inference_client.recommend(unique_user_id)
    body = r.json()
    assert body["fallback_reason"] == "cold_start", (
        "Expected cold_start after granting consent (no features in Redis)"
    )

    # Revoke
    r = await privacy_client.set_consent(
        unique_user_id, consent_granted=False, reason="user_request"
    )
    assert r.status_code == 200

    # Very next call must return consent_denied — no caching allowed
    r = await inference_client.recommend(unique_user_id)
    assert r.status_code == 200
    body = r.json()
    assert body["personalized"] is False
    assert body["fallback_reason"] == "consent_denied"


async def test_revocation_writes_audit_log(unique_user_id, privacy_client):
    """Every consent change produces an audit log entry.

    Both the GRANT and REVOKE actions must appear in the audit trail — this is
    a hard compliance requirement (consent.updated_at == audit_log.timestamp, written
    atomically in a single Postgres transaction).
    """
    r = await privacy_client.set_consent(
        unique_user_id, consent_granted=True, reason="initial_grant"
    )
    assert r.status_code == 200

    r = await privacy_client.set_consent(
        unique_user_id, consent_granted=False, reason="user_request"
    )
    assert r.status_code == 200

    audit = await privacy_client.get_audit(unique_user_id)
    assert len(audit) >= 2

    actions = {entry["action"] for entry in audit}
    assert "GRANT" in actions
    assert "REVOKE" in actions


async def test_regrant_consent_restores_access(
    unique_user_id, inference_client, privacy_client
):
    """Re-granting consent after revocation takes effect on the very next request."""
    await privacy_client.set_consent(unique_user_id, consent_granted=True)
    await privacy_client.set_consent(unique_user_id, consent_granted=False)

    r = await privacy_client.set_consent(unique_user_id, consent_granted=True)
    assert r.status_code == 200

    # Consent check passes again → cold_start (no features in Redis for this user)
    r = await inference_client.recommend(unique_user_id)
    body = r.json()
    assert body["personalized"] is False
    assert body["fallback_reason"] == "cold_start"
