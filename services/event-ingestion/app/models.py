from datetime import datetime

from pydantic import BaseModel, Field


class WatchEvent(BaseModel):
    """Represents a single content watch interaction from the client.

    Validated by Pydantic before the event reaches the Kafka producer — malformed
    events are rejected with 422 at the API boundary, never published to the topic.
    """

    user_id: str  # Raw user identifier; pseudonymized before leaving this service
    content_id: str  # Platform content identifier (movie, episode, etc.)
    # Percentage of content watched. Bounded to [0, 100] to prevent bad data from
    # corrupting downstream feature computations (e.g. avg_watch_duration).
    watch_pct: float = Field(ge=0.0, le=100.0)
    timestamp: datetime  # Client-reported event time; used for recency scoring in Flink
    genre: str | None = None  # Optional content genre; used by feature pipeline for category_affinity_score
    timezone: str | None = None  # IANA tz name (e.g. "America/New_York"); used to derive correct local hour for time_of_day_bucket


class SessionEvent(BaseModel):
    """Represents the start of a user viewing session.

    Used by the feature pipeline to compute session-level features such as
    session_genre_vector and time_of_day_bucket.
    """

    user_id: str  # Raw user identifier; pseudonymized before leaving this service
    session_id: str  # Unique session handle; correlates watch events within a session
    device: str  # Device type (mobile, smart-tv, web, etc.); influences recommendation ranking
    start_time: datetime  # Session start; used to derive time_of_day_bucket feature
