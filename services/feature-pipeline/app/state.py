from dataclasses import dataclass, field


@dataclass
class WatchRecord:
    content_id: str
    watch_pct: float
    event_time_epoch: float  # unix seconds; avoids datetime serialization issues in Flink state
    genre: str | None


@dataclass
class UserFeatureState:
    recent_watches: list[WatchRecord] = field(default_factory=list)
    # Accumulates watch_pct per genre within the current session
    session_genre_counts: dict[str, float] = field(default_factory=dict)
    last_computed_at_epoch: float = 0.0
