from datetime import datetime

from pydantic import BaseModel, Field


class ConsentUpdateRequest(BaseModel):
    consent_granted: bool = Field(
        description="True to grant personalization consent, false to revoke it."
    )
    reason: str | None = Field(
        default=None,
        description=(
            "Optional human-readable context for this change — e.g. 'GDPR Article 17 "
            "erasure request', 'user-initiated via settings page'. Omit for automated "
            "flows; most useful when a person or compliance process triggers the change."
        ),
    )


class ConsentResponse(BaseModel):
    user_pseudo_id: str = Field(
        description=(
            "HMAC-SHA256 digest of the raw user_id. The raw identifier is never stored, "
            "logged, or returned — only this pseudonymized form appears in the database."
        )
    )
    consent_granted: bool = Field(
        description="Consent state after this update."
    )
    updated_at: datetime = Field(
        description=(
            "Timestamp of this change in UTC. Matches the corresponding audit log entry "
            "exactly — both rows share the same timestamp to make forensic tracing unambiguous."
        )
    )

    model_config = {"from_attributes": True}


class AuditLogEntry(BaseModel):
    action: str = Field(
        description="GRANT or REVOKE."
    )
    timestamp: datetime = Field(
        description="When the consent change occurred (UTC)."
    )
    reason: str | None = Field(
        description="Context provided at the time of the change, if any."
    )

    model_config = {"from_attributes": True}


class ConsentCheckResponse(BaseModel):
    consent_granted: bool = Field(
        description=(
            "Whether the user currently has active personalization consent. "
            "False if no consent record exists — consent is denied by default (opt-in model)."
        )
    )
