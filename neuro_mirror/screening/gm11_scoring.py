"""Pure scoring for GM-11."""
from __future__ import annotations

import statistics


def score_gm11(
    events: list[dict], *, expected_rules: int, elapsed_ms: float = 0.0
) -> dict[str, float | int]:
    intervals = [float(item.get("interval_ms") or 0) for item in events]
    switch_intervals = [
        float(item.get("interval_ms") or 0)
        for index, item in enumerate(events)
        if index and item.get("rule_index") != events[index - 1].get("rule_index")
    ]
    ordinary_intervals = [
        float(item.get("interval_ms") or 0)
        for index, item in enumerate(events)
        if not index or item.get("rule_index") == events[index - 1].get("rule_index")
    ]
    switch_cost = (
        max(0.0, statistics.median(switch_intervals) - statistics.median(ordinary_intervals))
        if switch_intervals and ordinary_intervals else 0.0
    )
    return {
        "e08_calculation_accuracy": sum(bool(item.get("correct")) for item in events) / len(events) if events else 0.0,
        "u07_error_count": sum(not bool(item.get("correct")) for item in events),
        "l08_median_response_interval_ms": statistics.median(intervals) if intervals else 0.0,
        "e07_switch_cost_ms": switch_cost,
        "u04_duration_ms": max(0.0, elapsed_ms),
        "u06_complete": len({item.get("rule_index") for item in events}) >= max(1, expected_rules),
        # Ответ засчитывается только распознанным: нераспознанная речь
        # говорит о микрофоне, а не о счёте.
        "u06_technically_valid": bool(events) and any(
            str(item.get("transcript") or "").strip() for item in events
        ),
    }
