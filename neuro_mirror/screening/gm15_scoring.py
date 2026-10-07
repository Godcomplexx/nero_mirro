"""Pure scoring for GM-15."""
from __future__ import annotations

import statistics
from typing import Any


def score_gm15(events: list[dict[str, Any]]) -> dict[str, float | int]:
    valid_events = [event for event in events if event.get("valid")]
    correct_count = sum(bool(event.get("correct")) for event in events)
    reaction_times = [float(event.get("reaction_ms") or 0) for event in valid_events]
    return {
        "u01_correct_action_rate": correct_count / len(events) if events else 0.0,
        "l01_naming_accuracy": correct_count / len(valid_events) if valid_events else 0.0,
        "u07_error_count": sum(not bool(event.get("correct")) for event in events),
        "g03_median_response_ms": statistics.median(reaction_times) if reaction_times else 0.0,
        "g07_unrecognized_count": len(events) - len(valid_events),
    }
