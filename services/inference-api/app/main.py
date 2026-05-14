from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Path, Query

from .catalog import ContentItem, build_catalog, build_trending
from .config import Settings
from .feature_fetcher import FeatureFetcher
from .model_store import ModelStore
from .privacy_client import PrivacyClient
from .pseudonymize import pseudonymize
from .schemas import RecommendationResponse, RecommendedItem
from .scorer import score_and_rank

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    catalog = build_catalog(settings)
    trending = build_trending(settings, catalog)

    privacy = PrivacyClient(
        base_url=settings.privacy_base_url,
        timeout_seconds=settings.privacy_timeout_seconds,
    )
    await privacy.start()

    fetcher = FeatureFetcher(
        host=settings.redis_host,
        port=settings.redis_port,
        socket_timeout=settings.redis_timeout_seconds,
    )
    fetcher.start()

    model_store = ModelStore(
        tracking_uri=settings.mlflow_tracking_uri,
        model_name=settings.mlflow_model_name,
        alias=settings.mlflow_model_alias,
        alias_fallback=settings.mlflow_model_alias_fallback,
        poll_interval_seconds=settings.model_poll_interval_seconds,
    )
    await model_store.start()

    app.state.catalog = catalog
    app.state.trending = trending
    app.state.privacy = privacy
    app.state.fetcher = fetcher
    app.state.model_store = model_store

    yield

    await privacy.stop()
    await fetcher.stop()
    await model_store.stop()


_DESCRIPTION = """
Real-time personalized content recommendations.

## Request flow

Every request goes through four gates in order:

1. **Consent check** — calls the privacy service. Fail-closed: any error or timeout is
   treated as denied (ADR 0007). A user who has revoked consent receives the trending
   fallback on the very next request.
2. **Feature fetch** — reads `user:{pseudo_id}:features` from Redis. A cache miss means
   the user has no watch history yet (cold start) and receives the trending fallback.
3. **Model load** — retrieves the current LightGBM model. Returns the trending fallback
   if the model has not finished its initial load.
4. **Score and rank** — scores each catalog item as
   `engagement_probability × genre_affinity` and returns the top N.

## Pseudonymization

The caller supplies a raw `user_id`. The service derives a pseudonymized ID internally
using HMAC-SHA256 before any Redis lookup or privacy call — the raw identifier never
leaves this service.

## Model hot-swap

A background task polls MLflow every `INFERENCE_MODEL_POLL_INTERVAL_SECONDS` seconds.
When a new version is found under the configured alias, it is loaded and swapped
atomically without dropping any in-flight requests.

## Fallback

Any non-personalized path (consent denied, cold start, model unavailable) returns the
same trending feed. The `personalized` flag and `fallback_reason` field distinguish
these cases from a personalized response.
"""

_TAGS = [
    {"name": "recommendations", "description": "Personalized content ranking."},
    {"name": "ops", "description": "Health and readiness."},
]

app = FastAPI(
    title="Inference API",
    description=_DESCRIPTION,
    version="0.1.0",
    openapi_tags=_TAGS,
    lifespan=lifespan,
)


def _build_response(
    user_id: str,
    ranked: list[tuple[ContentItem, float | None]],
    personalized: bool,
    fallback_reason: str | None,
    model_version: str | None,
) -> RecommendationResponse:
    return RecommendationResponse(
        user_id=user_id,
        recommendations=[
            RecommendedItem(
                content_id=item.content_id,
                genre=item.genre,
                title=item.title,
                score=round(score, 6) if score is not None else None,
            )
            for item, score in ranked
        ],
        personalized=personalized,
        fallback_reason=fallback_reason,
        model_version=model_version,
    )


@app.get(
    "/recommend/{user_id}",
    response_model=RecommendationResponse,
    response_model_exclude_none=True,
    summary="Get personalized recommendations",
    tags=["recommendations"],
    responses={
        200: {"description": "Ranked content list. Check `personalized` to distinguish scored results from trending fallback."},
        422: {"description": "Invalid path or query parameter."},
    },
)
async def recommend(
    user_id: str = Path(description="Raw user identifier. Pseudonymized internally before any lookup."),
    top_n: int = Query(default=10, ge=1, le=100, description="Number of items to return."),
) -> RecommendationResponse:
    """Return Top-N personalized recommendations for a user.

    Falls back to a non-personalized trending list when:
    - The user has not granted (or has revoked) consent
    - The privacy service is unreachable (fail-closed, ADR 0007)
    - The user has no feature data in Redis (cold start)
    - The model is not yet loaded
    """
    pseudo_id = pseudonymize(user_id, settings.pseudonym_secret)

    def trending_fallback(reason: str) -> RecommendationResponse:
        return _build_response(
            user_id,
            [(item, None) for item in app.state.trending[:top_n]],
            personalized=False,
            fallback_reason=reason,
            model_version=None,
        )

    # Step 1 — consent check (fail closed)
    consent_granted = await app.state.privacy.is_consent_granted(pseudo_id)
    if not consent_granted:
        log.info("user=%.8s… consent_denied or privacy_unavailable — returning trending fallback", pseudo_id)
        return trending_fallback("consent_denied")

    # Step 2 — Redis feature fetch
    features = await app.state.fetcher.fetch(pseudo_id)
    if features is None:
        log.info("user=%.8s… cold_start (Redis miss) — returning trending fallback", pseudo_id)
        return trending_fallback("cold_start")

    # Step 3 — model load (only reached when consent granted and features exist)
    model = await app.state.model_store.get()
    if model is None:
        log.warning("Model not loaded — returning trending fallback")
        return trending_fallback("model_unavailable")

    # Step 4 — score and rank
    return _build_response(
        user_id,
        score_and_rank(features, model, app.state.catalog, top_n),
        personalized=True,
        fallback_reason=None,
        model_version=model.version,
    )


@app.get(
    "/health",
    summary="Health check",
    tags=["ops"],
    responses={200: {"description": "Service is running. `model_version` is null if the model has not loaded yet."}},
)
async def health() -> dict:
    model = await app.state.model_store.get()
    return {"status": "ok", "model_version": model.version if model else None}
