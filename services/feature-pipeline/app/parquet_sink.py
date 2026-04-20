from __future__ import annotations

import threading
import time
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pyflink.datastream import RichSinkFunction

from .config import Settings

PARQUET_SCHEMA = pa.schema([
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


class ParquetSink(RichSinkFunction):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._buffer: list[dict] = []
        self._last_flush_time: float = 0.0
        self._lock = threading.Lock()

    def open(self, runtime_context) -> None:
        Path(self._settings.parquet_base_path).mkdir(parents=True, exist_ok=True)
        self._last_flush_time = time.monotonic()

    def buffer(self, record: dict) -> None:
        with self._lock:
            self._buffer.append(record)
            elapsed = time.monotonic() - self._last_flush_time
            if (
                len(self._buffer) >= self._settings.parquet_flush_batch_size
                or elapsed >= self._settings.parquet_flush_interval_seconds
            ):
                self._flush_locked()

    def invoke(self, value, context) -> None:
        self.buffer(value)

    def _flush_locked(self) -> None:
        if not self._buffer:
            return
        records = self._buffer[:]
        self._buffer.clear()
        self._last_flush_time = time.monotonic()
        self._write_parquet(records)

    def _write_parquet(self, records: list[dict]) -> None:
        by_date: dict[str, list[dict]] = defaultdict(list)
        for r in records:
            by_date[r["event_date"]].append(r)

        for event_date, date_records in by_date.items():
            year, month, day = event_date.split("-")
            partition_path = (
                Path(self._settings.parquet_base_path)
                / f"year={year}"
                / f"month={month}"
                / f"day={day}"
            )
            partition_path.mkdir(parents=True, exist_ok=True)

            filename = f"batch_{int(time.time() * 1000)}.parquet"
            table = pa.Table.from_pylist(date_records, schema=PARQUET_SCHEMA)
            pq.write_table(table, partition_path / filename, compression="snappy")

    def close(self) -> None:
        with self._lock:
            self._flush_locked()
