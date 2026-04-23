from __future__ import annotations

import threading
import time
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .config import Settings

# Schema is declared here and used by both the sink (writer) and model-training
# (reader) to enforce that the offline store and online store (Redis) carry
# identical feature names and types — preventing training/serving skew.
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
    # Partition column — not a feature; used by model-training to read by date
    # and by the Parquet directory layout (year=/month=/day=/).
    pa.field("event_date",               pa.string(),  nullable=False),
])


class ParquetSink:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._buffer: list[dict] = []
        self._last_flush_time: float = 0.0
        # Lock guards the buffer against concurrent access: Flink may call
        # process_element and close() from different threads.
        self._lock = threading.Lock()

    def open(self, runtime_context) -> None:
        Path(self._settings.parquet_base_path).mkdir(parents=True, exist_ok=True)
        self._last_flush_time = time.monotonic()

    def buffer(self, record: dict) -> None:
        with self._lock:
            self._buffer.append(record)
            elapsed = time.monotonic() - self._last_flush_time
            # Flush eagerly on batch_size for high-throughput bursts; flush on
            # interval so files are never delayed indefinitely during quiet periods.
            if (
                len(self._buffer) >= self._settings.parquet_flush_batch_size
                or elapsed >= self._settings.parquet_flush_interval_seconds
            ):
                self._flush_locked()

    def _flush_locked(self) -> None:
        # Caller must hold self._lock. Copy-and-clear before doing I/O so the
        # lock is held for as short a time as possible.
        if not self._buffer:
            return
        records = self._buffer[:]
        self._buffer.clear()
        self._last_flush_time = time.monotonic()
        self._write_parquet(records)

    def _write_parquet(self, records: list[dict]) -> None:
        # A single flush batch may span midnight — group by event_date so each
        # day's records land in the correct partition directory.
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

            # Millisecond timestamp in filename prevents collisions when multiple
            # flushes land in the same partition within one second.
            filename = f"batch_{int(time.time() * 1000)}.parquet"
            table = pa.Table.from_pylist(date_records, schema=PARQUET_SCHEMA)
            pq.write_table(table, partition_path / filename, compression="snappy")

    def close(self) -> None:
        # Final flush on shutdown ensures buffered records aren't lost when the
        # pipeline stops cleanly (e.g. during a rolling restart).
        with self._lock:
            self._flush_locked()
