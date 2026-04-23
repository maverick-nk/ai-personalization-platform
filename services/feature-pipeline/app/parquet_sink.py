from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .config import Settings

log = logging.getLogger(__name__)

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
        records_to_write: list[dict] = []
        with self._lock:
            self._buffer.append(record)
            elapsed = time.monotonic() - self._last_flush_time
            # Flush eagerly on batch_size for high-throughput bursts; flush on
            # interval so files are never delayed indefinitely during quiet periods.
            if (
                len(self._buffer) >= self._settings.parquet_flush_batch_size
                or elapsed >= self._settings.parquet_flush_interval_seconds
            ):
                records_to_write = self._drain_locked()
        # I/O happens outside the lock so incoming buffer() calls are not blocked
        # for the full duration of a file write.
        if records_to_write:
            self._write_parquet(records_to_write)

    def _drain_locked(self) -> list[dict]:
        # Caller must hold self._lock. Copies and clears the buffer so the lock
        # is released before the actual file write begins.
        records = self._buffer[:]
        self._buffer.clear()
        self._last_flush_time = time.monotonic()
        return records

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

            # UUID filename prevents collisions when multiple workers or rapid flushes
            # land in the same partition — unlike a ms timestamp, UUIDs are globally unique.
            filename = f"batch_{uuid.uuid4().hex}.parquet"
            try:
                table = pa.Table.from_pylist(date_records, schema=PARQUET_SCHEMA)
                pq.write_table(table, partition_path / filename, compression="snappy")
                log.debug("Wrote %d records to %s", len(date_records), partition_path / filename)
            except Exception:
                log.exception(
                    "Failed to write Parquet batch (%d records) to %s",
                    len(date_records), partition_path / filename,
                )

    def close(self) -> None:
        # Final flush on shutdown ensures buffered records aren't lost when the
        # pipeline stops cleanly (e.g. during a rolling restart).
        with self._lock:
            records = self._drain_locked()
        if records:
            self._write_parquet(records)
