import pytest
from app.feature_fetcher import _cast


def test_cast_int_field():
    result = _cast({"watch_count_10min": "7"})
    assert result["watch_count_10min"] == 7
    assert isinstance(result["watch_count_10min"], int)


def test_cast_str_fields():
    result = _cast({
        "time_of_day_bucket": "evening",
        "session_genre_vector": '{"action": 0.6}',
        "pseudo_user_id": "abc123",
    })
    assert result["time_of_day_bucket"] == "evening"
    assert result["session_genre_vector"] == '{"action": 0.6}'
    assert result["pseudo_user_id"] == "abc123"


def test_cast_float_field():
    result = _cast({"avg_watch_duration": "72.5"})
    assert result["avg_watch_duration"] == pytest.approx(72.5)
    assert isinstance(result["avg_watch_duration"], float)


def test_cast_malformed_int_defaults_to_zero(caplog):
    result = _cast({"watch_count_10min": "not-a-number"})
    assert result["watch_count_10min"] == 0
    assert "watch_count_10min" in caplog.text


def test_cast_malformed_float_defaults_to_zero(caplog):
    result = _cast({"recency_score": "bad"})
    assert result["recency_score"] == 0.0
    assert "recency_score" in caplog.text


def test_cast_empty_dict():
    assert _cast({}) == {}


def test_cast_mixed_fields():
    raw = {
        "watch_count_10min": "3",
        "avg_watch_duration": "65.0",
        "time_of_day_bucket": "morning",
        "recency_score": "0.4",
    }
    result = _cast(raw)
    assert result["watch_count_10min"] == 3
    assert result["avg_watch_duration"] == pytest.approx(65.0)
    assert result["time_of_day_bucket"] == "morning"
    assert result["recency_score"] == pytest.approx(0.4)
