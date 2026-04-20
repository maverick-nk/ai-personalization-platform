import json
import math
from datetime import datetime, timezone

from .state import UserFeatureState


def compute_watch_count_10min(state: UserFeatureState) -> int:
    # Eviction happens in process_element before this is called; count what's in state.
    return len(state.recent_watches)


def compute_category_affinity_score(
    state: UserFeatureState, now_epoch: float, lambda_: float
) -> float:
    score = 0.0
    n = len(state.recent_watches)
    if n == 0:
        return 0.0
    for record in state.recent_watches:
        if record.genre is None:
            continue
        age = now_epoch - record.event_time_epoch
        score += record.watch_pct * math.exp(-lambda_ * age)
    norm = 100.0 * n
    return min(score / norm, 1.0)


def compute_avg_watch_duration(state: UserFeatureState) -> float:
    if not state.recent_watches:
        return 0.0
    return sum(r.watch_pct for r in state.recent_watches) / len(state.recent_watches)


def compute_time_of_day_bucket(event_time_epoch: float) -> str:
    hour = datetime.fromtimestamp(event_time_epoch, tz=timezone.utc).hour
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def compute_recency_score(
    state: UserFeatureState, now_epoch: float, lambda_: float
) -> float:
    n = len(state.recent_watches)
    if n == 0:
        return 0.0
    score = sum(
        r.watch_pct * math.exp(-lambda_ * (now_epoch - r.event_time_epoch))
        for r in state.recent_watches
    )
    norm = 100.0 * n
    return min(score / norm, 1.0)


def compute_session_genre_vector(state: UserFeatureState) -> str:
    total = sum(state.session_genre_counts.values())
    if total == 0:
        return "{}"
    normalized = {g: count / total for g, count in state.session_genre_counts.items()}
    return json.dumps(normalized, sort_keys=True)
