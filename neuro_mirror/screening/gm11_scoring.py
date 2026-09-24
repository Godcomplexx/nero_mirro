"""Pure scoring for GM-11."""
from __future__ import annotations

import statistics


def score_gm11(events: list[dict]) -> dict[str, float | int]:
    intervals = [float(item.get("interval_ms") or 0) for item in events]
    return {
        "e08_calculation_accuracy": sum(bool(item.get("correct")) for item in events) / len(events) if events else 0.0,
        "u07_error_count": sum(not bool(item.get("correct")) for item in events),
        "l08_median_response_interval_ms": statistics.median(intervals) if intervals else 0.0,
    }
