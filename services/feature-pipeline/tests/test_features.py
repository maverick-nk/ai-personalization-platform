import json
import math
from datetime import datetime, timezone

import pytest

from app.features import (
    compute_avg_watch_duration,
    compute_category_affinity_score,
    compute_recency_score,
    compute_session_genre_vector,
    compute_time_of_day_bucket,
    compute_watch_count_10min,
)
from app.state import UserFeatureState, WatchRecord

NOW = 1_000_000.0  # arbitrary epoch; offsets are relative to this


# ── watch_count_10min ─────────────────────────────────────────────────────────

def test_watch_count_empty_state():
    assert compute_watch_count_10min(UserFeatureState()) == 0


def test_watch_count_all_within_window():
    state = UserFeatureState(recent_watches=[
        WatchRecord("c1", 50.0, NOW, None),
        WatchRecord("c2", 30.0, NOW - 100, None),
        WatchRecord("c3", 70.0, NOW - 500, None),
    ])
    assert compute_watch_count_10min(state) == 3


def test_watch_count_is_dumb_counter():
    # The function counts whatever is in state — eviction is process_element's job.
    state = UserFeatureState(recent_watches=[WatchRecord("c1", 50.0, NOW - 700, None)])
    assert compute_watch_count_10min(state) == 1


# ── category_affinity_score ───────────────────────────────────────────────────

def test_category_affinity_no_genre_events():
    state = UserFeatureState(recent_watches=[WatchRecord("c1", 100.0, NOW, None)])
    assert compute_category_affinity_score(state, NOW, lambda_=0.001) == 0.0


def test_category_affinity_empty_state():
    assert compute_category_affinity_score(UserFeatureState(), NOW, lambda_=0.001) == 0.0


def test_category_affinity_single_recent_event():
    state = UserFeatureState(recent_watches=[WatchRecord("c1", 100.0, NOW, "action")])
    score = compute_category_affinity_score(state, NOW, lambda_=0.001)
    # age=0 → exp(0)=1 → score=100*1/100 = 1.0
    assert abs(score - 1.0) < 1e-6


def test_category_affinity_decay():
    state = UserFeatureState(recent_watches=[WatchRecord("c1", 100.0, NOW - 1000, "action")])
    score = compute_category_affinity_score(state, NOW, lambda_=0.001)
    # age=1000 → exp(-1) ≈ 0.3679 → score=100*exp(-1)/100
    assert abs(score - math.exp(-1)) < 1e-4


def test_category_affinity_capped_at_one():
    state = UserFeatureState(recent_watches=[
        WatchRecord("c1", 100.0, NOW, "drama"),
        WatchRecord("c2", 100.0, NOW, "drama"),
    ])
    score = compute_category_affinity_score(state, NOW, lambda_=0.001)
    assert score <= 1.0


# ── avg_watch_duration ────────────────────────────────────────────────────────

def test_avg_watch_duration_empty():
    assert compute_avg_watch_duration(UserFeatureState()) == 0.0


def test_avg_watch_duration_single():
    state = UserFeatureState(recent_watches=[WatchRecord("c1", 75.0, NOW, None)])
    assert compute_avg_watch_duration(state) == 75.0


def test_avg_watch_duration_multiple():
    state = UserFeatureState(recent_watches=[
        WatchRecord("c1", 100.0, NOW, None),
        WatchRecord("c2", 50.0, NOW - 60, None),
        WatchRecord("c3", 0.0, NOW - 120, None),
    ])
    assert compute_avg_watch_duration(state) == 50.0


# ── time_of_day_bucket ────────────────────────────────────────────────────────

def _epoch(hour: int) -> float:
    return datetime(2026, 4, 19, hour, 0, 0, tzinfo=timezone.utc).timestamp()


def test_time_of_day_morning():
    assert compute_time_of_day_bucket(_epoch(8)) == "morning"


def test_time_of_day_afternoon():
    assert compute_time_of_day_bucket(_epoch(14)) == "afternoon"


def test_time_of_day_evening():
    assert compute_time_of_day_bucket(_epoch(19)) == "evening"


def test_time_of_day_night():
    assert compute_time_of_day_bucket(_epoch(2)) == "night"


def test_time_of_day_boundary_midnight():
    assert compute_time_of_day_bucket(_epoch(0)) == "night"


def test_time_of_day_boundary_noon():
    assert compute_time_of_day_bucket(_epoch(12)) == "afternoon"


def test_time_of_day_boundary_morning_start():
    assert compute_time_of_day_bucket(_epoch(6)) == "morning"


def test_time_of_day_uses_local_timezone():
    # 16:30 UTC = 22:00 IST (UTC+5:30) → "night" in IST, "afternoon" in UTC.
    # Confirms the IANA timezone shifts the bucket correctly.
    epoch = datetime(2026, 4, 19, 16, 30, 0, tzinfo=timezone.utc).timestamp()
    assert compute_time_of_day_bucket(epoch, "Asia/Kolkata") == "night"
    assert compute_time_of_day_bucket(epoch) == "afternoon"  # UTC fallback


def test_time_of_day_dst_aware():
    # 06:00 UTC on a US summer date = 02:00 EDT (UTC-4) → "night", not "morning".
    # zoneinfo resolves DST automatically; a raw offset of -5 (EST) would give 01:00,
    # also "night" — but this confirms the IANA name path is exercised.
    epoch = datetime(2026, 7, 1, 6, 0, 0, tzinfo=timezone.utc).timestamp()
    assert compute_time_of_day_bucket(epoch, "America/New_York") == "night"


def test_time_of_day_invalid_timezone_falls_back_to_utc():
    epoch = _epoch(8)  # 08:00 UTC → "morning"
    assert compute_time_of_day_bucket(epoch, "Not/ATimezone") == "morning"


def test_time_of_day_none_timezone_falls_back_to_utc():
    epoch = _epoch(14)  # 14:00 UTC → "afternoon"
    assert compute_time_of_day_bucket(epoch, None) == "afternoon"


# ── recency_score ─────────────────────────────────────────────────────────────

def test_recency_score_empty():
    assert compute_recency_score(UserFeatureState(), NOW, lambda_=0.001) == 0.0


def test_recency_score_immediate_event():
    state = UserFeatureState(recent_watches=[WatchRecord("c1", 100.0, NOW, None)])
    score = compute_recency_score(state, NOW, lambda_=0.001)
    assert abs(score - 1.0) < 1e-6


def test_recency_score_decreases_with_age():
    state_new = UserFeatureState(recent_watches=[WatchRecord("c1", 100.0, NOW, None)])
    state_old = UserFeatureState(recent_watches=[WatchRecord("c1", 100.0, NOW - 500, None)])
    assert compute_recency_score(state_new, NOW, 0.001) > compute_recency_score(state_old, NOW, 0.001)


# ── session_genre_vector ──────────────────────────────────────────────────────

def test_session_genre_vector_empty():
    assert compute_session_genre_vector(UserFeatureState()) == "{}"


def test_session_genre_vector_single_genre():
    state = UserFeatureState(session_genre_counts={"action": 80.0})
    result = json.loads(compute_session_genre_vector(state))
    assert abs(result["action"] - 1.0) < 1e-6


def test_session_genre_vector_multiple_normalized():
    state = UserFeatureState(session_genre_counts={"action": 60.0, "drama": 40.0})
    result = json.loads(compute_session_genre_vector(state))
    assert abs(result["action"] - 0.6) < 1e-6
    assert abs(result["drama"] - 0.4) < 1e-6
    assert abs(sum(result.values()) - 1.0) < 1e-6


def test_session_genre_vector_sorted_keys():
    state = UserFeatureState(session_genre_counts={"drama": 50.0, "action": 50.0})
    result_str = compute_session_genre_vector(state)
    assert result_str.index("action") < result_str.index("drama")
