"""CLI entry point for the user simulation framework.

Usage:
    python -m tests.simulation.runner --suite tests/simulation/suites/baseline.yaml

Requires PSEUDONYMIZE_SECRET to be set. The full stack (event-ingestion,
inference-api, privacy) must be running before invoking this script.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tests.simulation import results as result_store
from tests.simulation.config import Suite, load_suite

_LOCUSTFILE = Path(__file__).parent / "locustfile.py"
_RESULTS_DIR = Path(__file__).parent / "results"


def _print_table(snapshot: dict) -> None:
    eps = snapshot.get("endpoints", {})
    print(f"\nSuite: {snapshot['suite']} | test_type: {snapshot['test_type']} "
          f"| {snapshot['peak_users']} users | {snapshot['duration_s']}s")
    print(f"{'Endpoint':<20} {'Reqs':>6} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8} {'Errors':>7}")
    print("-" * 64)
    for name, ep in sorted(eps.items()):
        print(f"{name:<20} {ep['count']:>6} {ep['p50_ms']:>8.1f} "
              f"{ep['p95_ms']:>8.1f} {ep['p99_ms']:>8.1f} {ep['errors']:>7}")
    print("-" * 64)


def _print_assertions(snapshot: dict) -> None:
    for key, result in snapshot["assertions"].items():
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  {key}: {result['actual']} / {result['threshold']}  [{status}]")


def run(suite: Suite) -> bool:
    secret = os.environ.get("PSEUDONYMIZE_SECRET", "")
    if not secret:
        print("ERROR: PSEUDONYMIZE_SECRET is not set", file=sys.stderr)
        sys.exit(1)

    os.environ["SUITE_CONFIG"] = suite.model_dump_json()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_prefix = str(_RESULTS_DIR / suite.name / ts)
    Path(csv_prefix).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "locust",
        "--headless",
        "--locustfile", str(_LOCUSTFILE),
        "--users", str(suite.peak_users),
        "--spawn-rate", str(suite.spawn_rate),
        "--run-time", f"{suite.duration_s}s",
        "--csv", csv_prefix,
        "--exit-code-on-error", "0",
    ]

    # locustfile.py reads EVENT_INGESTION_URL, INFERENCE_URL, PRIVACY_URL directly from env.
    # Locust requires --host for HttpUser subclasses, but PersonalizedUser extends User
    # and manages its own clients — pass a dummy host to satisfy the CLI parser.
    cmd += ["--host", os.environ.get("EVENT_INGESTION_URL", "http://localhost:8000")]

    print(f"\nStarting: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"Locust exited with code {result.returncode}", file=sys.stderr)

    snapshot_path = result_store.process(csv_prefix, suite)
    snapshot = json.loads(snapshot_path.read_text())

    _print_table(snapshot)
    _print_assertions(snapshot)
    print(f"\nResults saved to {snapshot_path}")

    return snapshot["passed"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a user simulation suite against the live stack")
    parser.add_argument("--suite", required=True, help="Path to a suite YAML file")
    args = parser.parse_args()

    suite = load_suite(args.suite)
    passed = run(suite)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
