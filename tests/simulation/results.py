from __future__ import annotations

import csv
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from tests.simulation.config import Suite

_RESULTS_DIR = Path(__file__).parent / "results"


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    sorted_s = sorted(samples)
    idx = int(len(sorted_s) * pct / 100)
    return sorted_s[min(idx, len(sorted_s) - 1)]


def process(csv_prefix: str, suite: Suite) -> Path:
    """Read Locust CSV stats, compute per-endpoint percentiles, write JSON snapshot.

    Locust writes <csv_prefix>_stats.csv with columns:
      Type, Name, Request Count, Failure Count, Median Response Time,
      Average Response Time, Min Response Time, Max Response Time,
      Average Content Size, Requests/s, Failures/s, 50%, 66%, 75%, 80%,
      90%, 95%, 99%, 99.9%, 99.99%, 100%
    """
    stats_path = Path(f"{csv_prefix}_stats.csv")
    if not stats_path.exists():
        raise FileNotFoundError(f"Locust stats CSV not found: {stats_path}")

    endpoints: dict[str, dict] = {}
    total_requests = 0
    total_failures = 0

    with open(stats_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["Name"].strip()
            if name == "Aggregated":
                total_requests = int(row["Request Count"])
                total_failures = int(row["Failure Count"])
                continue
            endpoints[name] = {
                "p50_ms": float(row["50%"] or 0),
                "p95_ms": float(row["95%"] or 0),
                "p99_ms": float(row["99%"] or 0),
                "count": int(row["Request Count"]),
                "errors": int(row["Failure Count"]),
            }

    error_rate_pct = (total_failures / total_requests * 100) if total_requests > 0 else 0.0
    overall_p95 = max((ep["p95_ms"] for ep in endpoints.values()), default=0.0)
    overall_p50 = statistics.median(ep["p50_ms"] for ep in endpoints.values()) if endpoints else 0.0
    overall_p99 = max((ep["p99_ms"] for ep in endpoints.values()), default=0.0)

    assertion_results = {
        "latency_p95_ms": {
            "threshold": suite.assertions.latency_p95_ms,
            "actual": round(overall_p95, 2),
            "passed": overall_p95 <= suite.assertions.latency_p95_ms,
        },
        "error_rate_pct": {
            "threshold": suite.assertions.error_rate_pct,
            "actual": round(error_rate_pct, 4),
            "passed": error_rate_pct <= suite.assertions.error_rate_pct,
        },
    }
    passed = all(a["passed"] for a in assertion_results.values())

    snapshot = {
        "suite": suite.name,
        "test_type": suite.test_type,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "duration_s": suite.duration_s,
        "peak_users": suite.peak_users,
        "total_requests": total_requests,
        "error_rate_pct": round(error_rate_pct, 4),
        "latency_ms": {
            "p50": round(overall_p50, 2),
            "p95": round(overall_p95, 2),
            "p99": round(overall_p99, 2),
        },
        "endpoints": endpoints,
        "assertions": assertion_results,
        "passed": passed,
    }

    out_dir = _RESULTS_DIR / suite.name
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{ts}.json"
    out_path.write_text(json.dumps(snapshot, indent=2))
    return out_path


def load_latest(suite_name: str) -> dict | None:
    suite_dir = _RESULTS_DIR / suite_name
    if not suite_dir.exists():
        return None
    files = sorted(suite_dir.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text())
