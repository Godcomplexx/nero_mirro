"""Pure scoring for GM-10."""
from __future__ import annotations


def score_gm10(events: list[dict], total_differences: int) -> dict[str, float | int]:
    found = sum(bool(item.get("correct")) for item in events)
    errors = sum(not bool(item.get("correct")) for item in events)
    correct_times = [float(item.get("reaction_ms") or 0) for item in events if item.get("correct")]
    return {
        "a07_found_difference_rate": found / total_differences if total_differences else 0.0,
        "u07_error_count": errors,
        "g06_mean_correct_action_ms": sum(correct_times) / len(correct_times) if correct_times else 0.0,
    }
