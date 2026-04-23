from dataclasses import dataclass, field


@dataclass
class WatchRecord:
    content_id: str
    watch_pct: float
    # Stored as a unix float rather than datetime so Flink can pickle the state
    # without hitting datetime serialization edge cases across timezones.
    event_time_epoch: float
    genre: str | None


@dataclass
class UserFeatureState:
    # Sliding window of recent watch events; stale entries are evicted in
    # FeatureProcessFunction.process_element before features are recomputed.
    recent_watches: list[WatchRecord] = field(default_factory=list)
    # Accumulates watch_pct per genre within the current session — used to
    # build the normalized session_genre_vector feature.
    session_genre_counts: dict[str, float] = field(default_factory=dict)
    # Wall-clock time of the last feature write; informational only, not used
    # in any feature computation.
    last_computed_at_epoch: float = 0.0
