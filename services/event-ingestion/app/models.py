from datetime import datetime

from pydantic import BaseModel, Field


class WatchEvent(BaseModel):
    """Represents a single content watch interaction from the client.

    Validated by Pydantic before the event reaches the Kafka producer — malformed
    events are rejected with 422 at the API boundary, never published to the topic.
    """

    user_id: str = Field(
        description=(
            "Raw user identifier. Pseudonymized internally using HMAC-SHA256 before "
            "publication — the raw value never appears in Kafka, Redis, Parquet, or logs."
        )
    )
    content_id: str = Field(
        description="Platform content identifier (movie ID, episode ID, etc.)."
    )
    watch_pct: float = Field(
        ge=0.0,
        le=100.0,
        description=(
            "Percentage of the content watched, in the range [0, 100]. "
            "Bounded at ingestion to prevent corrupt values from skewing downstream "
            "feature computations such as `avg_watch_duration`."
        ),
    )
    timestamp: datetime = Field(
        description=(
            "Client-reported time of the watch event (ISO 8601). "
            "Used by the Flink feature pipeline to compute recency-weighted features."
        )
    )
    genre: str | None = Field(
        default=None,
        description=(
            "Content genre (e.g. 'drama', 'comedy'). Optional — omit if unknown. "
            "Used by the feature pipeline to update `category_affinity_score`."
        ),
    )
    timezone: str | None = Field(
        default=None,
        description=(
            "IANA time zone name for the user's local time (e.g. 'America/New_York'). "
            "Used to map the event timestamp to a local hour for the `time_of_day_bucket` feature."
        ),
    )


class SessionEvent(BaseModel):
    """Represents the start of a user viewing session.

    Used by the feature pipeline to compute session-level features such as
    `session_genre_vector` and `time_of_day_bucket`.
    """

    user_id: str = Field(
        description=(
            "Raw user identifier. Pseudonymized internally using HMAC-SHA256 before "
            "publication — the raw value never appears in Kafka, Redis, Parquet, or logs."
        )
    )
    session_id: str = Field(
        description=(
            "Unique session handle. Used to correlate watch events that occurred "
            "within the same viewing session."
        )
    )
    device: str = Field(
        description=(
            "Device type for this session (e.g. 'mobile', 'smart-tv', 'web'). "
            "Used as a contextual signal in the recommendation model."
        )
    )
    start_time: datetime = Field(
        description=(
            "Session start time (ISO 8601). "
            "Used with the user's timezone to derive the `time_of_day_bucket` feature."
        )
    )


class AcceptedResponse(BaseModel):
    accepted: bool = Field(
        description=(
            "Always true. Indicates the event was accepted for asynchronous delivery "
            "to Kafka. Does not guarantee broker acknowledgement — see fire-and-forget "
            "delivery semantics (ADR 0003)."
        )
    )
