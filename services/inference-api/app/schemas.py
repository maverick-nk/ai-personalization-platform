from __future__ import annotations

from pydantic import BaseModel, Field


class RecommendedItem(BaseModel):
    content_id: str = Field(description="Unique content identifier from the catalog.")
    genre: str = Field(description="Genre of the content item.")
    title: str = Field(description="Display title of the content item.")
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Click-probability score produced by the model (0.0–1.0). "
            "Absent for trending fallback items, which are not scored."
        ),
    )


class RecommendationResponse(BaseModel):
    user_id: str = Field(description="The raw user ID as supplied by the caller.")
    recommendations: list[RecommendedItem] = Field(
        description="Ranked list of content items, highest score first."
    )
    personalized: bool = Field(
        description=(
            "True when the list was scored for this specific user. "
            "False when a non-personalized trending fallback was returned."
        )
    )
    fallback_reason: str | None = Field(
        default=None,
        description=(
            "Present only when personalized=false. One of: "
            "'consent_denied' — user has not granted or has revoked consent; "
            "'cold_start' — no feature data found in Redis; "
            "'model_unavailable' — model has not finished loading."
        ),
    )
    model_version: str | None = Field(
        default=None,
        description=(
            "MLflow model version used for scoring. "
            "Absent when personalized=false (model was not invoked)."
        ),
    )
