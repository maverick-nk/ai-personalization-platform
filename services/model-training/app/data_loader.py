from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

log = logging.getLogger(__name__)


def _date_range(base_path: str, date_from: date, date_to: date) -> list[str]:
    """Return existing partition paths that fall within [date_from, date_to]."""
    paths = []
    current = date_from
    while current <= date_to:
        partition = (
            Path(base_path)
            / f"year={current.year}"
            / f"month={current.month:02d}"
            / f"day={current.day:02d}"
        )
        if partition.exists():
            paths.append(str(partition))
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
