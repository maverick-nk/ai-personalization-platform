import pytest
from pydantic import ValidationError

from app.models import SessionEvent, WatchEvent


class TestWatchEvent:
    def test_valid(self):
        e = WatchEvent(user_id="u1", content_id="c1", watch_pct=50.0, timestamp="2026-04-18T10:00:00Z")
        assert e.watch_pct == 50.0

    def test_watch_pct_below_zero(self):
        with pytest.raises(ValidationError):
            WatchEvent(user_id="u1", content_id="c1", watch_pct=-1.0, timestamp="2026-04-18T10:00:00Z")

    def test_watch_pct_above_hundred(self):
        with pytest.raises(ValidationError):
            WatchEvent(user_id="u1", content_id="c1", watch_pct=100.1, timestamp="2026-04-18T10:00:00Z")

    def test_watch_pct_boundary_values(self):
        WatchEvent(user_id="u1", content_id="c1", watch_pct=0.0, timestamp="2026-04-18T10:00:00Z")
        WatchEvent(user_id="u1", content_id="c1", watch_pct=100.0, timestamp="2026-04-18T10:00:00Z")

    def test_missing_user_id(self):
        with pytest.raises(ValidationError):
            WatchEvent(content_id="c1", watch_pct=50.0, timestamp="2026-04-18T10:00:00Z")

    def test_missing_content_id(self):
        with pytest.raises(ValidationError):
            WatchEvent(user_id="u1", watch_pct=50.0, timestamp="2026-04-18T10:00:00Z")

    def test_missing_timestamp(self):
        with pytest.raises(ValidationError):
            WatchEvent(user_id="u1", content_id="c1", watch_pct=50.0)

    def test_invalid_timestamp(self):
        with pytest.raises(ValidationError):
            WatchEvent(user_id="u1", content_id="c1", watch_pct=50.0, timestamp="not-a-date")


class TestSessionEvent:
    def test_valid(self):
        e = SessionEvent(user_id="u1", session_id="s1", device="mobile", start_time="2026-04-18T10:00:00Z")
        assert e.device == "mobile"

    def test_missing_session_id(self):
        with pytest.raises(ValidationError):
            SessionEvent(user_id="u1", device="mobile", start_time="2026-04-18T10:00:00Z")

    def test_missing_device(self):
        with pytest.raises(ValidationError):
            SessionEvent(user_id="u1", session_id="s1", start_time="2026-04-18T10:00:00Z")

    def test_invalid_start_time(self):
        with pytest.raises(ValidationError):
            SessionEvent(user_id="u1", session_id="s1", device="tv", start_time="not-a-date")
