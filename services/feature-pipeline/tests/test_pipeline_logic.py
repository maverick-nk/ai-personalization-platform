"""
Pure-Python tests for the eviction logic in FeatureProcessFunction.process_element.
No Flink or JVM required — these exercise the state manipulation directly.
"""
from app.state import UserFeatureState, WatchRecord

WINDOW = 600  # seconds, matches config.window_size_seconds default


def _evict(state: UserFeatureState, now_epoch: float) -> UserFeatureState:
    """Simulate the eviction block from process_element."""
    state.max_seen_event_time = max(state.max_seen_event_time, now_epoch)
    cutoff = state.max_seen_event_time - WINDOW
    state.recent_watches = [r for r in state.recent_watches if r.event_time_epoch >= cutoff]
    return state


def test_late_event_does_not_expand_window():
    # State already has a record at t=900 after processing events up to t=1000.
    state = UserFeatureState(
        recent_watches=[WatchRecord("c1", 50.0, 900.0, None)],
        max_seen_event_time=1000.0,
    )
    # Late event arrives at t=200 (e.g. mobile-buffered).
    state = _evict(state, now_epoch=200.0)

    # High-water mark must not regress.
    assert state.max_seen_event_time == 1000.0
    # Cutoff stays at 400 (1000 - 600), not -400 (200 - 600).
    # The t=900 record is within [400, 1000] and must survive.
    assert len(state.recent_watches) == 1
    assert state.recent_watches[0].event_time_epoch == 900.0


def test_window_advances_with_newer_events():
    state = UserFeatureState()

    for t in [100.0, 200.0, 700.0, 800.0]:
        state.recent_watches.append(WatchRecord("c", 50.0, t, None))
        state = _evict(state, now_epoch=t)

    # After t=800: high-water mark=800, cutoff=200. Events at t=100 evicted.
    assert state.max_seen_event_time == 800.0
    surviving_times = {r.event_time_epoch for r in state.recent_watches}
    assert 100.0 not in surviving_times
    assert {200.0, 700.0, 800.0}.issubset(surviving_times)
