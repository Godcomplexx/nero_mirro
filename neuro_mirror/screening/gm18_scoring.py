"""Pure scoring for GM-18."""
from __future__ import annotations

from typing import Any


def score_gm18(
    events: list[dict[str, Any]],
    elapsed_ms: float,
    *,
    required_puzzles: int,
) -> dict[str, float | int | bool]:
    """Оценить сборку пазлов.

    U01 по методике — доля фрагментов, установленных на своё место первым же
    перемещением. Число пазлов передаёт игра: прежде здесь стояли три пазла и
    минута занятия, а в задании один пазл, и любое прохождение выходило
    незавершённым.
    """
    moves = sum(int(event.get("moves") or 0) for event in events)
    minimum = sum(int(event.get("minimum_moves") or 0) for event in events)
    first_attempt = sum(int(event.get("first_attempt_pieces") or 0) for event in events)
    moved = sum(int(event.get("moved_pieces") or 0) for event in events)
    return {
        "u01_first_attempt_piece_rate": first_attempt / moved if moved else 0.0,
        "u01_first_attempt_pieces": first_attempt,
        "u01_pieces_total": moved,
        "u08_completed_puzzles": len(events),
        "u08_completion_rate": len(events) / required_puzzles if required_puzzles else 0.0,
        "e01_moves_above_minimum": max(0, moves - minimum),
        "u04_duration_ms": max(0.0, elapsed_ms),
        "g10_move_count": moves,
        "u06_complete": len(events) >= max(1, required_puzzles),
        # Собранный пазл без единого перемещения значит, что ход сборки не
        # записан: перемешанное поле не собирается само.
        "u06_technically_valid": bool(events) and moved > 0,
    }
