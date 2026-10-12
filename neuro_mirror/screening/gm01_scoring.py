"""Pure scoring for GM-01."""
from __future__ import annotations


def score_gm01(attempts: list[dict], *, pair_count: int, completed: bool) -> dict[str, float | int | bool]:
    minimum = pair_count
    moves = len(attempts)
    errors = sum(not bool(item.get("correct")) for item in attempts)
    found = min(pair_count, moves - errors)
    return {
        "m05_moves_above_minimum": max(0, moves - minimum),
        # U08 — доля найденных пар. Числитель и знаменатель хранятся отдельно:
        # по ним проверяется порог перехода уровня.
        "u08_completion_rate": found / pair_count if pair_count else 0.0,
        "u08_pairs_found": found,
        "u08_pairs_total": pair_count,
        "u07_error_count": errors,
        "pair_attempts": moves,
        "u06_complete": bool(completed),
        # Ходов не меньше, чем пар: иначе доска не могла быть собрана, и
        # запись хода игры неполна.
        "u06_technically_valid": moves >= minimum if completed else bool(attempts),
    }
