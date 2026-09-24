"""Pure scoring for GM-01."""
from __future__ import annotations


def score_gm01(attempts: list[dict], *, pair_count: int, completed: bool) -> dict[str, float | int | bool]:
    minimum = pair_count
    moves = len(attempts)
    errors = sum(not bool(item.get("correct")) for item in attempts)
    return {
        "m05_moves_above_minimum": max(0, moves - minimum),
        "u08_completion_rate": 1.0 if completed else 0.0,
        "u07_error_count": errors,
        "pair_attempts": moves,
    }
