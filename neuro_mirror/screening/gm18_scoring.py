"""Pure scoring for GM-18."""
from __future__ import annotations

from typing import Any


def score_gm18(
    events: list[dict[str, Any]], elapsed_ms: float, *, expected_puzzles: int
) -> dict[str, float | int | bool]:
    moves = sum(int(event.get("moves") or 0) for event in events)
    minimum = sum(int(event.get("minimum_moves") or 0) for event in events)
    pieces = sum(int(event.get("piece_count") or 0) for event in events)
    first_hits = sum(int(event.get("first_placement_correct") or 0) for event in events)
    completed = len(events)
    return {
        "u01_first_placement_accuracy": first_hits / pieces if pieces else 0.0,
        "u08_completion_rate": completed / max(1, expected_puzzles),
        "e01_moves_above_minimum": max(0, moves - minimum),
        "u04_duration_ms": max(0.0, elapsed_ms),
        "g10_repeated_attempts": max(0, moves - minimum),
        "u06_complete": completed >= max(1, expected_puzzles),
        "u06_technically_valid": bool(events) and all(
            int(event.get("piece_count") or 0) > 0
            and bool(event.get("puzzle"))
            for event in events
        ),
    }
