from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .database import engine
from .partitions import ensure_partitions
from .routers import audit, consent, internal

_DESCRIPTION = """
Consent enforcement layer for the AI personalization platform.

Maintains a Postgres-backed **consent table** (current state, one row per user) and an
append-only **audit log** (full change history, partitioned by month with a configurable
retention window).

The inference-api calls the [internal consent check](#tag/internal/GET/internal/consent/check/{pseudo_id})
before every feature fetch. Revocation takes effect on the next request — consent state
is never cached by the inference-api.

## Pseudonymization

All public endpoints accept a raw `user_id` and pseudonymize it internally using
HMAC-SHA256 with a shared secret. Raw user identifiers never appear in the database,
logs, or API responses — only the hex digest (`user_pseudo_id`) is stored.

The internal endpoint accepts a `pseudo_id` directly because the inference-api already
holds the pseudonymized form (it reads Redis keys of the form `user:{pseudo_id}:features`).

## Audit Log Retention

Audit history is retained for `AUDIT_RETENTION_MONTHS` months (default: 3). Expired
monthly partitions are dropped at service startup. Consent state is never purged —
only the change history ages out.
"""

_TAGS = [
    {
        "name": "consent",
        "description": "Grant or revoke personalization consent and retrieve audit history.",
    },
    {
        "name": "internal",
        "description": (
            "Endpoints called by internal services only. "
            "The inference-api calls the consent check before every feature fetch. "
            "Not intended for external clients."
        ),
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create any missing monthly partitions and drop expired ones before
    # accepting requests — ensures every INSERT lands in a valid partition.
    await ensure_partitions(engine, retention_months=settings.audit_retention_months)
    yield
    await engine.dispose()


app = FastAPI(
    title="Privacy Service",
    description=_DESCRIPTION,
    version="0.1.0",
    openapi_tags=_TAGS,
    lifespan=lifespan,
)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


app.include_router(consent.router, prefix="/privacy")
app.include_router(audit.router, prefix="/privacy")
app.include_router(internal.router, prefix="/internal")
