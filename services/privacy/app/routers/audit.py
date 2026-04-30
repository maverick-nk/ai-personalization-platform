from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import AuditLog
from ..pseudonymize import pseudonymize
from ..schemas import AuditLogEntry

router = APIRouter(tags=["consent"])


@router.get(
    "/audit/{user_id}",
    response_model=list[AuditLogEntry],
    summary="Get consent change history",
    description=(
        "Returns the full GRANT/REVOKE history for the given user in reverse-chronological order "
        "(most recent change first). "
        "\n\n"
        "The raw `user_id` is pseudonymized before the database lookup — the audit log stores "
        "only the pseudonymized form, so raw identifiers are never exposed. "
        "\n\n"
        "**Retention:** history is available for the configured retention window "
        "(default 3 months). Entries older than that are dropped when expired monthly "
        "partitions are cleaned up at service startup. "
        "An empty list is returned if the user has no consent history within the window."
    ),
    response_description="Audit log entries ordered newest first. Empty list if no history exists.",
)
async def get_audit(
    user_id: str,
    session: AsyncSession = Depends(get_session),
):
    pseudo_id = pseudonymize(user_id, settings.pseudonymize_secret)
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.user_pseudo_id == pseudo_id)
        .order_by(AuditLog.timestamp.desc())
    )
    return result.scalars().all()
