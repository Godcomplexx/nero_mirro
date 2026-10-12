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
    return {
        "u03_completed_levels": len(completed),
        # U03 по методике — доля башен, собранных в целевую конфигурацию.
        "u03_target_tower_rate": len(completed) / required_levels if required_levels else 0.0,
        "u03_target_towers": len(completed),
        "u03_towers_total": required_levels,
        "e05_moves_above_minimum": max(0, valid_moves - minimum_moves),
        "e01_valid_move_count": valid_moves,
        "e03_invalid_move_count": invalid_moves,
        "e04_duration_ms": max(0.0, elapsed_ms),
        "u07_error_count": invalid_moves,
        "u06_complete": len(completed) >= max(1, required_levels),
        "u06_technically_valid": bool(events),
    }
