import pytest
from pydantic import ValidationError

from app.schemas import ConsentCheckResponse, ConsentUpdateRequest


def test_consent_update_requires_consent_granted():
    with pytest.raises(ValidationError):
        ConsentUpdateRequest()


def test_consent_update_reason_is_optional():
    req = ConsentUpdateRequest(consent_granted=True)
    assert req.reason is None


def test_consent_update_accepts_reason():
    req = ConsentUpdateRequest(consent_granted=False, reason="user request")
    assert req.reason == "user request"


def test_consent_check_response_true():
    resp = ConsentCheckResponse(consent_granted=True)
    assert resp.consent_granted is True


def test_consent_check_response_false():
    resp = ConsentCheckResponse(consent_granted=False)
    assert resp.consent_granted is False
