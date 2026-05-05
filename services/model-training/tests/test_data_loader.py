from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.data_loader import load_parquet

SCHEMA = pa.schema([
    pa.field("pseudo_user_id",          pa.string(),  nullable=False),
    pa.field("watch_count_10min",        pa.int32(),   nullable=False),
    pa.field("category_affinity_score",  pa.float64(), nullable=False),
    pa.field("avg_watch_duration",       pa.float64(), nullable=False),
    pa.field("time_of_day_bucket",       pa.string(),  nullable=False),
    pa.field("recency_score",            pa.float64(), nullable=False),
    pa.field("session_genre_vector",     pa.string(),  nullable=False),
    pa.field("last_event_epoch",         pa.float64(), nullable=False),
    pa.field("computed_at_epoch",        pa.float64(), nullable=False),
    pa.field("event_date",               pa.string(),  nullable=False),
])


def _write_partition(base: Path, event_date: str, n: int = 5) -> None:
    year, month, day = event_date.split("-")
    partition = base / f"year={year}" / f"month={month}" / f"day={day}"
    partition.mkdir(parents=True, exist_ok=True)
    data = {
        "pseudo_user_id": [f"u{i}" for i in range(n)],
        "watch_count_10min": [i for i in range(n)],
        "category_affinity_score": [0.5] * n,
        "avg_watch_duration": [60.0] * n,
        "time_of_day_bucket": ["evening"] * n,
        "recency_score": [0.7] * n,
        "session_genre_vector": [json.dumps({"action": 0.6})] * n,
        "last_event_epoch": [1.0] * n,
        "computed_at_epoch": [2.0] * n,
        "event_date": [event_date] * n,
    }
    table = pa.Table.from_pydict(data, schema=SCHEMA)
    pq.write_table(table, partition / "batch.parquet")


def test_load_returns_correct_shape(tmp_path):
    _write_partition(tmp_path, "2026-05-01", n=10)
    _write_partition(tmp_path, "2026-05-02", n=5)
    df = load_parquet(str(tmp_path), date(2026, 5, 1), date(2026, 5, 2))
    assert len(df) == 15
    assert "watch_count_10min" in df.columns


def test_load_single_partition(tmp_path):
    _write_partition(tmp_path, "2026-05-03", n=3)
    df = load_parquet(str(tmp_path), date(2026, 5, 3), date(2026, 5, 3))
    assert len(df) == 3


def test_load_raises_on_empty_directory(tmp_path):
    with pytest.raises(ValueError, match="No Parquet partitions found"):
        load_parquet(str(tmp_path), date(2026, 1, 1), date(2026, 1, 7))


def test_load_skips_missing_dates(tmp_path):
    # Only 1 May exists; request 1–3 May — should return just 1 May's rows
    _write_partition(tmp_path, "2026-05-01", n=4)
    df = load_parquet(str(tmp_path), date(2026, 5, 1), date(2026, 5, 3))
    assert len(df) == 4
