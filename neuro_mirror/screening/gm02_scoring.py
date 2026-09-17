from __future__ import annotations

from typing import Any


def score_gm02_attempt(
    expected: list[int],
    clicks: list[dict[str, Any]],
    *,
    successful_rounds: int,
    started_at_ms: float,
    finished_at_ms: float,
) -> dict[str, Any]:
    """Calculate GM-02 metrics from the untouched click event list."""
    clicked_cells = [int(click["cell"]) for click in clicks]
    compared = min(len(expected), len(clicked_cells))
    correct_positions = sum(
        1 for index in range(compared) if clicked_cells[index] == expected[index]
    )
    exact = clicked_cells == expected

    return {
        "m08_series_accuracy": 1.0 if exact else 0.0,
        "m01_max_sequence_length": successful_rounds,
        "m02_position_accuracy": (
            correct_positions / len(expected) if expected else 0.0
        ),
        "m03_order_errors": sum(
            1
            for index in range(compared)
            if clicked_cells[index] != expected[index]
        ) + abs(len(expected) - len(clicked_cells)),
        "u04_duration_ms": max(0.0, finished_at_ms - started_at_ms),
        "u06_complete": True,
        "u06_technically_valid": True,
    }
