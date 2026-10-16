"""Pure scoring for GM-22."""
from __future__ import annotations

from typing import Any


def score_gm22(
    events: list[dict[str, Any]],
    elapsed_ms: float,
    *,
    required_levels: int,
) -> dict[str, float | int | bool]:
    """Оценить прохождение башни.

    Число требуемых уровней передаётся вызывающим. Раньше оно было зашито
    тройкой вместе с минимальной продолжительностью занятия: после перехода
    на один уровень за занятие безошибочное решение засчитывалось как
    незавершённое.
    """
    completed = [event for event in events if event.get("level_complete")]
    valid_moves = sum(bool(event.get("legal_move")) for event in events)
    invalid_moves = sum(not bool(event.get("legal_move")) for event in events)
    minimum_moves = sum(int(event.get("minimum_moves") or 0) for event in completed)
    planning_ms = sum(float(event.get("planning_ms") or 0) for event in completed)
    execution_ms = sum(float(event.get("execution_ms") or 0) for event in completed)
    return {
        "u03_successful_levels": len(completed),
        "e05_rule_violation_count": invalid_moves,
        "e01_moves_above_optimum": max(0, valid_moves - minimum_moves),
        "e03_planning_time_ms": planning_ms,
        "e04_execution_time_ms": execution_ms,
        "valid_move_count": valid_moves,
        "u04_duration_ms": max(0.0, elapsed_ms),
        "u07_error_count": invalid_moves,
        "u06_complete": len(completed) >= max(1, required_levels),
        "u06_technically_valid": bool(events) and all(
            event.get("ruleset") == "classic_hanoi"
            and int(event.get("rod_count") or 0) == 3
            and int(event.get("disk_count") or 0) > 0
            for event in events
        ),
    }
