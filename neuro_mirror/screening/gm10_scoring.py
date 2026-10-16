"""Pure scoring for GM-10."""
from __future__ import annotations


def score_gm10(
    events: list[dict],
    total_differences: int,
    *,
    finished: bool,
    elapsed_ms: float = 0.0,
) -> dict[str, float | int]:
    found = sum(bool(item.get("correct")) for item in events)
    errors = sum(not bool(item.get("correct")) for item in events)
    active_minutes = max(0.0, elapsed_ms) / 60_000
    return {
        "a07_found_difference_rate": found / total_differences if total_differences else 0.0,
        "u07_error_count": errors,
        "g06_correct_actions_per_minute": found / active_minutes if active_minutes else 0.0,
        "u04_duration_ms": max(0.0, elapsed_ms),
        # Задание кончается, когда найдены все отличия или вышло время;
        # признак передаётся игрой, а не выводится из числа нажатий.
        "u06_complete": bool(finished),
        "u06_technically_valid": total_differences > 0,
    }
