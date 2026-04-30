"""Monthly partition management for the audit_log table.

Called at service startup to ensure current and upcoming partitions exist
and to drop any partitions that have aged past the retention window.
Partition names follow the pattern: audit_log_YYYY_MM.
"""

import logging
import re
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)

_TABLE = "audit_log"
_PARTITION_RE = re.compile(r"^audit_log_(\d{4})_(\d{2})$")


def _add_months(d: date, n: int) -> date:
    """Return the first day of the month that is n months from d.

    Shifts month index to 0-based, adds n, then uses integer division to carry
    over into years. Works correctly for both positive and negative n.
    Example: _add_months(date(2026, 11, 1), 2) → date(2027, 1, 1)
             _add_months(date(2026,  1, 1), -1) → date(2025, 12, 1)
    """
    month = d.month - 1 + n
    return date(d.year + month // 12, month % 12 + 1, 1)


async def ensure_partitions(
    engine: AsyncEngine,
    retention_months: int = 6,
    lookahead_months: int = 2,
) -> None:
    """Create missing monthly partitions and drop those past the retention window.

    Runs on every service startup — all operations are idempotent (IF NOT EXISTS /
    IF EXISTS), so concurrent restarts are safe.
    """
    current = date.today().replace(day=1)
    cutoff = _add_months(current, -retention_months)

    async with engine.begin() as conn:
        # pg_inherits tracks the parent→child relationship for partitioned tables.
        # pg_class holds the name of each relation (table or partition).
        # This query returns the names of all monthly child partitions of audit_log
        # without hard-coding any date range — works regardless of how many exist.
        rows = await conn.execute(
            text("""
                SELECT c.relname
                FROM pg_inherits  i
                JOIN pg_class     c ON c.oid = i.inhrelid
                JOIN pg_class     p ON p.oid = i.inhparent
                WHERE p.relname = :table
            """),
            {"table": _TABLE},
        )
        existing = {row[0] for row in rows}

        # lookahead_months=2 creates the partition for next month (and the month after)
        # proactively. Without this, if the service hasn't restarted by the time the
        # calendar rolls over, the first INSERT of the new month would fail because no
        # partition covers that date yet.
        for offset in range(lookahead_months + 1):
            start = _add_months(current, offset)
            end = _add_months(start, 1)
            name = f"{_TABLE}_{start.strftime('%Y_%m')}"
            if name not in existing:
                await conn.execute(text(
                    f"CREATE TABLE IF NOT EXISTS {name} "
                    f"PARTITION OF {_TABLE} "
                    f"FOR VALUES FROM ('{start}') TO ('{end}')"
                ))
                log.info("Created partition %s", name)

        # Drop any partition whose month falls before the cutoff.
        for name in existing:
            m = _PARTITION_RE.match(name)
            if m:
                part_date = date(int(m.group(1)), int(m.group(2)), 1)
                if part_date < cutoff:
                    await conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
                    log.info("Dropped expired partition %s", name)
