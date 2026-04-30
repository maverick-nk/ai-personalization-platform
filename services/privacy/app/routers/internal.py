from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Consent
from ..schemas import ConsentCheckResponse

router = APIRouter(tags=["internal"])


@router.get(
    "/consent/check/{pseudo_id}",
    response_model=ConsentCheckResponse,
    summary="Check consent (inference-api use only)",
    description=(
        "Called by the inference-api before every feature fetch. "
        "Returns the current consent state for the given pseudonymized user ID. "
        "\n\n"
        "**Why `pseudo_id` and not raw `user_id`?** The inference-api already holds the "
        "pseudonymized form — it reads Redis keys of the form `user:{pseudo_id}:features`. "
        "Accepting the raw ID here would require the inference-api to know the HMAC secret, "
        "which would violate the pseudonymization boundary. "
        "\n\n"
        "**Opt-in model:** a missing consent record is treated as denied. "
        "Users must explicitly grant consent before receiving personalized recommendations. "
        "\n\n"
        "**Latency contract:** this endpoint must respond in under 5ms — it sits in the "
        "critical path of every recommendation request (50ms end-to-end budget)."
    ),
    response_description="Current consent state. False if no record exists.",
)
async def check_consent(
    pseudo_id: str,
    session: AsyncSession = Depends(get_session),
):
    # This endpoint receives pseudo_id directly, unlike the public endpoints which
    # accept raw user_id and pseudonymize internally. The inference-api already holds
    # the pseudo_id (it reads Redis keys of the form user:{pseudo_id}:features), so
    # pseudonymizing again here would produce a double-hash and miss every record.
    #
    # Primary-key lookup — no joins, no index scan. Fastest possible read path;
    # must stay under 5ms to fit within the inference-api's end-to-end latency budget.
    #
    # Opt-in model: a missing record means the user has never explicitly granted
    # consent, so personalization is denied by default (privacy-first).
    record = await session.get(Consent, pseudo_id)
    return ConsentCheckResponse(
        consent_granted=record.consent_granted if record is not None else False
    )
