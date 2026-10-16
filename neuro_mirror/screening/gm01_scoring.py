"""Pure scoring for GM-01."""
from __future__ import annotations


def score_gm01(
    attempts: list[dict],
    *,
    pair_count: int,
    completed: bool,
    elapsed_ms: float = 0.0,
) -> dict[str, float | int | bool]:
    minimum = pair_count
    moves = len(attempts)
    errors = sum(not bool(item.get("correct")) for item in attempts)
    known_opportunities = sum(int(item.get("known_pair_opportunities") or 0) for item in attempts)
    used_known_pairs = sum(bool(item.get("used_known_pair")) for item in attempts)
    return {
        "m05_moves_above_minimum": max(0, moves - minimum),
        "m06_unused_known_pair_rate": (
            max(0, known_opportunities - used_known_pairs) / known_opportunities
            if known_opportunities else 0.0
        ),
        "u08_completion_rate": 1.0 if completed else 0.0,
        "u07_error_count": errors,
        "u04_duration_ms": max(0.0, elapsed_ms),
        "pair_attempts": moves,
        "u06_complete": bool(completed),
        # Ходов не меньше, чем пар: иначе доска не могла быть собрана, и
        # запись хода игры неполна.
        "u06_technically_valid": moves >= minimum if completed else bool(attempts),
    }
