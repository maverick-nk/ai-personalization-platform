from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WatchRecord:
    content_id: str
    watch_pct: float
    # Stored as a unix float rather than datetime so Flink can serialize the
    # state without hitting datetime serialization edge cases across timezones.
    event_time_epoch: float
    genre: str | None

    def to_row(self):
        # Lazy import — pyflink is an optional dependency not present in the
        # unit-test environment. Importing at call time keeps state.py importable
        # without a JVM, so test_features.py continues to run without PyFlink.
        from pyflink.common import Row
        return Row(self.content_id, self.watch_pct, self.event_time_epoch, self.genre)

    @classmethod
    def from_row(cls, row) -> WatchRecord:
        return cls(
            content_id=row[0],
            watch_pct=row[1],
            event_time_epoch=row[2],
            genre=row[3],  # None when the event carried no genre tag
        )


@dataclass
class UserFeatureState:
    # Sliding window of recent watch events; stale entries are evicted in
    # FeatureProcessFunction.process_element before features are recomputed.
    recent_watches: list[WatchRecord] = field(default_factory=list)
    # Accumulated watch_pct per genre within the current window — rebuilt from
    # scratch after each eviction pass to stay consistent with recent_watches.
    session_genre_counts: dict[str, float] = field(default_factory=dict)
    # Wall-clock time of the last feature write; informational only.
    last_computed_at_epoch: float = 0.0

    def to_row(self):
        from pyflink.common import Row
        return Row(
            [r.to_row() for r in self.recent_watches],
            self.session_genre_counts,
            self.last_computed_at_epoch,
        )

    @classmethod
    def from_row(cls, row) -> UserFeatureState:
        return cls(
            recent_watches=[WatchRecord.from_row(r) for r in (row[0] or [])],
            # Flink may return a Java LinkedHashMap; dict() normalises it to a
            # plain Python dict so downstream code can use .get() and .items().
            session_genre_counts=dict(row[1]) if row[1] else {},
            last_computed_at_epoch=row[2] or 0.0,
        )
