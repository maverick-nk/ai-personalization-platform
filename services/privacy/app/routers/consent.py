from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import AuditLog, Consent
from ..pseudonymize import pseudonymize
from ..schemas import ConsentResponse, ConsentUpdateRequest

router = APIRouter(tags=["consent"])


@router.patch(
    "/consent/{user_id}",
    response_model=ConsentResponse,
    summary="Grant or revoke consent",
    description=(
        "Updates personalization consent for the given user. "
        "The raw `user_id` is pseudonymized internally — it never appears in the database or response. "
        "\n\n"
        "**Atomicity:** the consent upsert and audit log entry are written in a single transaction. "
        "Either both succeed or neither does — the audit trail can never fall out of sync with consent state."
        "\n\n"
        "**Immediacy:** revocation takes effect on the next inference request. "
        "The inference-api checks this service on every call with no caching."
    ),
    response_description="The updated consent record, including the pseudonymized user ID and change timestamp.",
)
async def update_consent(
    user_id: str,
    body: ConsentUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    pseudo_id = pseudonymize(user_id, settings.pseudonymize_secret)
    action = "GRANT" if body.consent_granted else "REVOKE"
    # Single timestamp shared by both the consent upsert and the audit log entry.
    # This guarantees consent.updated_at == audit_log.timestamp for every change —
    # letting you join the two rows by time if needed and removing any ambiguity
    # about which audit entry corresponds to which consent state.
    now = datetime.now(timezone.utc)

    # Upsert consent and append audit log in one session so both rows are committed
    # atomically. A crash between the two writes is impossible — either both land
    # or neither does, which is the hard compliance requirement.
    existing = await session.get(Consent, pseudo_id)
    if existing:
        existing.consent_granted = body.consent_granted
        existing.updated_at = now
        record = existing
    else:
        record = Consent(
            user_pseudo_id=pseudo_id,
            consent_granted=body.consent_granted,
            updated_at=now,
        )
        session.add(record)

    session.add(AuditLog(
        user_pseudo_id=pseudo_id,
        action=action,
        timestamp=now,
        reason=body.reason,
    ))

    await session.commit()
    # refresh re-fetches the row so the response reflects the committed state.
    # Needed because expire_on_commit=False keeps stale in-memory values —
    # without this, updated_at would show the pre-commit value on first-time inserts.
    await session.refresh(record)
    return record
