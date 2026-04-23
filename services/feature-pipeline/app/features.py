import json
import math
from datetime import datetime, timezone

from .state import UserFeatureState


def compute_watch_count_10min(state: UserFeatureState) -> int:
    # Measures short-term engagement intensity. A high count in the last 10 minutes
    # signals the user is in an active binge session — the model can lean harder on
    # recent genre signals and deprioritize older preference history. A count of 0
    # after a long gap suggests the user just returned and may want a fresh start.
    # Eviction happens in process_element before this is called; count what's in state.
    return len(state.recent_watches)


def compute_category_affinity_score(
    state: UserFeatureState, now_epoch: float, lambda_: float
) -> float:
    # Captures how strongly the user gravitates toward genre-tagged content right now,
    # with older watches contributing less via exponential decay. A score near 1.0
    # means the user has been heavily watching genre content very recently — ideal for
    # surfacing more of the same. Decay prevents a single genre binge from permanently
    # locking recommendations; affinity naturally fades if the user moves on.
    # Events without a genre tag are excluded — they don't carry preference signal.
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
    # Reflects content completion behaviour — a strong proxy for satisfaction.
    # Users averaging >80% are finishing what they start (lean-back viewers who
    # reward good matches). Users averaging <30% are skipping frequently, which
    # can mean poor recommendations or a browse-first discovery pattern. The model
    # uses this to calibrate how confident it should be in genre-based signals:
    # low completion rates suggest the user is still exploring, not yet settled.
    if not state.recent_watches:
        return 0.0
    return sum(r.watch_pct for r in state.recent_watches) / len(state.recent_watches)


def compute_time_of_day_bucket(event_time_epoch: float, tz_name: str | None = None) -> str:
    # Watching habits shift meaningfully by time of day. Morning viewers tend toward
    # shorter, lighter content (news, comedy). Evening and night sessions skew toward
    # longer-form drama and films. The model treats this as a context feature — the
    # same user may want different recommendations at 8am vs 10pm, even with identical
    # watch history. Bucketing into 4 coarse categories avoids overfitting to the hour.
    # tz_name is an IANA timezone name (e.g. "America/New_York"). When provided, the
    # local hour is resolved correctly including DST transitions. Falls back to UTC
    # if the client did not send a timezone or the name is unrecognised.
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    hour = datetime.fromtimestamp(event_time_epoch, tz=tz).hour
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
    # A decay-weighted measure of how actively engaged the user has been across all
    # content, regardless of genre. Unlike category_affinity_score, this treats every
    # watch event equally — it answers "is this user hot right now?" rather than
    # "what do they like?". A high recency score means the user is in an active
    # session with high completion rates on recent content; the inference API can
    # serve personalised results with high confidence. A low score (churned or idle
    # user) signals the model should blend in more popular/trending fallback content.
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
    # Encodes the user's genre taste distribution within the current session as a
    # normalized probability vector. Unlike category_affinity_score (which collapses
    # all genres into a single number), this preserves the full mix — e.g.
    # {"action": 0.6, "drama": 0.4} tells the model the user is split across two
    # genres rather than locked into one. Useful for diverse recommendation slates
    # and detecting taste shifts mid-session.
    #
    # session_genre_counts values are pre-divided by 100 (in process_element) so
    # each event contributes a fractional completion in [0, 1] rather than a raw
    # percentage point. The normalization below then produces a proper probability
    # distribution regardless of how many events are in the session.
    #
    # Stored as sorted-key JSON so the model-training pipeline can parse it
    # deterministically into a feature vector.
    total = sum(state.session_genre_counts.values())
    if total == 0:
        return "{}"
    normalized = {g: count / total for g, count in state.session_genre_counts.items()}
    return json.dumps(normalized, sort_keys=True)
