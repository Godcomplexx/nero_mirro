"""Pure scoring for GM-21."""
from __future__ import annotations

import statistics
from typing import Any


def score_gm21(events: list[dict[str, Any]], elapsed_ms: float) -> dict[str, float | int | bool]:
    correct_count = sum(bool(event.get("correct")) for event in events)
    reaction_times = [float(event.get("reaction_ms") or 0) for event in events]
    return {
        "u01_correct_action_rate": correct_count / len(events) if events else 0.0,
        "g03_median_reaction_ms": statistics.median(reaction_times) if reaction_times else 0.0,
        "u07_error_count": len(events) - correct_count,
        "u04_duration_ms": max(0.0, elapsed_ms),
        "u06_complete": len(events) >= 12 and elapsed_ms >= 60_000,
    }
