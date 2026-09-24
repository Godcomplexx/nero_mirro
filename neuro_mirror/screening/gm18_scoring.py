"""Pure scoring for GM-18."""
from __future__ import annotations

from typing import Any


def score_gm18(events: list[dict[str, Any]], elapsed_ms: float) -> dict[str, float | int | bool]:
    moves = sum(int(event.get("moves") or 0) for event in events)
    minimum = sum(int(event.get("minimum_moves") or 0) for event in events)
    return {
        "u01_completed_puzzles": len(events),
        "u08_completion_rate": 1.0 if events else 0.0,
        "e01_moves_above_minimum": max(0, moves - minimum),
        "u04_duration_ms": max(0.0, elapsed_ms),
        "g10_move_count": moves,
        "u06_complete": len(events) >= 3 and elapsed_ms >= 60_000,
    }
