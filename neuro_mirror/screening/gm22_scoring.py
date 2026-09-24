"""Pure scoring for GM-22."""
from __future__ import annotations

from typing import Any


def score_gm22(events: list[dict[str, Any]], elapsed_ms: float) -> dict[str, float | int | bool]:
    completed = [event for event in events if event.get("level_complete")]
    valid_moves = sum(bool(event.get("valid")) for event in events)
    invalid_moves = sum(not bool(event.get("valid")) for event in events)
    minimum_moves = sum(int(event.get("minimum_moves") or 0) for event in completed)
    return {
        "u03_completed_levels": len(completed),
        "e05_moves_above_minimum": max(0, valid_moves - minimum_moves),
        "e01_valid_move_count": valid_moves,
        "e03_invalid_move_count": invalid_moves,
        "e04_duration_ms": max(0.0, elapsed_ms),
        "u07_error_count": invalid_moves,
        "u06_complete": len(completed) >= 3 and elapsed_ms >= 60_000,
    }
