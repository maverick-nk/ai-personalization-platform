from __future__ import annotations


def p95(samples: list[float]) -> float:
    """95th percentile of a list of elapsed-time floats (seconds)."""
    if not samples:
        raise ValueError("Cannot compute p95 of an empty sample list")
    return sorted(samples)[int(len(samples) * 0.95)]


def assert_p95(samples: list[float], max_seconds: float, label: str = "") -> None:
    """Assert p95 latency is within the SLO. Fails with a human-readable message.

    This is the only public latency assertion — there is no assert_mean, which
    enforces the rule that SLOs must be defined at the tail, not the average.
    """
    actual = p95(samples)
    tag = f" for {label}" if label else ""
    assert actual <= max_seconds, (
        f"p95 latency{tag}: {actual * 1000:.1f}ms exceeds {max_seconds * 1000:.0f}ms SLO"
        f" (n={len(samples)}, min={min(samples)*1000:.1f}ms, max={max(samples)*1000:.1f}ms)"
    )
