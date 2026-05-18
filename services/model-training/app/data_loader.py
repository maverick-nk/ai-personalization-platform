from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
import pyarrow.parquet as pq

log = logging.getLogger(__name__)


def _is_gcs(path: str) -> bool:
    return path.startswith("gs://")


def _partition_exists(path: str, gcs: bool) -> bool:
    if gcs:
        import gcsfs
        fs = gcsfs.GCSFileSystem()
        bucket_path = path.removeprefix("gs://")
        return fs.exists(bucket_path)
    else:
        from pathlib import Path
        return Path(path).exists()


def _date_range(base_path: str, date_from: date, date_to: date) -> list[str]:
    """Return existing partition paths that fall within [date_from, date_to]."""
    gcs = _is_gcs(base_path)
    paths = []
    current = date_from
    while current <= date_to:
        suffix = (
            f"year={current.year}"
            f"/month={current.month:02d}"
            f"/day={current.day:02d}"
        )
        if gcs:
            partition = f"{base_path.rstrip('/')}/{suffix}"
        else:
            from pathlib import Path
            partition = str(Path(base_path) / f"year={current.year}" / f"month={current.month:02d}" / f"day={current.day:02d}")
        if _partition_exists(partition, gcs):
            paths.append(partition)
        current += timedelta(days=1)
    return paths


def load_parquet(base_path: str, date_from: date, date_to: date) -> pd.DataFrame:
    """Read all Parquet partitions in [date_from, date_to] into a single DataFrame.

    Raises ValueError if no data is found — silent empty training produces a
    model that would silently degrade inference quality.
    """
    paths = _date_range(base_path, date_from, date_to)
    if not paths:
        raise ValueError(
            f"No Parquet partitions found in '{base_path}' "
            f"between {date_from} and {date_to}"
        )

    tables = []
    for path in paths:
        try:
            tables.append(pq.read_table(path).to_pandas())
        except Exception:
            log.exception("Failed to read Parquet partition: %s", path)

    if not tables:
        raise ValueError(
            f"Found partition directories but all reads failed for '{base_path}'"
        )

    df = pd.concat(tables, ignore_index=True)
    log.info("Loaded %d rows from %d partitions (%s → %s)", len(df), len(tables), date_from, date_to)
    return df
