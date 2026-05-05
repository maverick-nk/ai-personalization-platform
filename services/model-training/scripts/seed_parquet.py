"""Generate synthetic Parquet data for local model-training smoke tests.

Writes 30 days of fake feature rows to /tmp/parquet_sample using the same
schema as the feature pipeline's PARQUET_SCHEMA. Run this before
`uv run python -m app` when real Kafka/Flink data isn't available.
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

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

GENRES = ["action", "drama", "comedy", "thriller", "sci-fi", "documentary"]
TIME_BUCKETS = ["morning", "afternoon", "evening", "night"]
BASE_PATH = Path("/tmp/parquet_sample")
DAYS = 30
ROWS_PER_DAY = 200
SEED = 42


def _genre_vector() -> str:
    n = random.randint(1, 3)
    chosen = random.sample(GENRES, n)
    weights = [random.random() for _ in chosen]
    total = sum(weights)
    return json.dumps({g: round(w / total, 4) for g, w in zip(chosen, weights)}, sort_keys=True)


def _make_row(user_id: str, event_date: str, base_epoch: float) -> dict:
    watch_pct = random.gauss(65, 20)
    watch_pct = max(0.0, min(100.0, watch_pct))
    count = random.randint(0, 10)
    age_seconds = random.uniform(0, 600)
    recency = watch_pct / 100.0 * math.exp(-0.001 * age_seconds)
    return {
        "pseudo_user_id":         user_id,
        "watch_count_10min":      count,
        "category_affinity_score": round(random.uniform(0.0, 1.0), 4),
        "avg_watch_duration":      round(watch_pct, 2),
        "time_of_day_bucket":      random.choice(TIME_BUCKETS),
        "recency_score":           round(min(recency, 1.0), 4),
        "session_genre_vector":    _genre_vector(),
        "last_event_epoch":        base_epoch,
        "computed_at_epoch":       base_epoch + 0.1,
        "event_date":              event_date,
    }


def main() -> None:
    random.seed(SEED)
    today = date.today()
    total = 0

    for day_offset in range(DAYS):
        event_date = today - timedelta(days=DAYS - 1 - day_offset)
        date_str = event_date.strftime("%Y-%m-%d")
        base_epoch = float(event_date.toordinal()) * 86400.0

        rows = [
            _make_row(f"user_{i % 50:03d}", date_str, base_epoch + i)
            for i in range(ROWS_PER_DAY)
        ]

        year, month, day = date_str.split("-")
        partition = BASE_PATH / f"year={year}" / f"month={month}" / f"day={day}"
        partition.mkdir(parents=True, exist_ok=True)

        table = pa.Table.from_pylist(rows, schema=SCHEMA)
        pq.write_table(table, partition / "batch.parquet", compression="snappy")
        total += len(rows)

    print(f"Wrote {total} rows across {DAYS} days to {BASE_PATH}")
    print(f"Set MODEL_TRAINING_PARQUET_BASE_PATH={BASE_PATH} before running the pipeline.")


if __name__ == "__main__":
    main()
