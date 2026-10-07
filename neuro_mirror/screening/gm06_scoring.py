"""Pure scoring for GM-06."""
from __future__ import annotations


def score_gm06(events: list[dict]) -> dict[str, float | int]:
    expected = sum(len(item.get("expected_sequence") or ()) for item in events)
    correct_positions = sum(int(item.get("correct_positions") or 0) for item in events)
    order_errors = expected - correct_positions
    rhythm_errors = [float(item.get("rhythm_error_ms") or 0.0) for item in events]
    successful = [len(item.get("expected_sequence") or ()) for item in events if item.get("correct")]
    return {
        "m08_series_accuracy": sum(bool(item.get("correct")) for item in events) / len(events) if events else 0.0,
        "m01_max_sequence_length": max(successful, default=0),
        "m02_position_accuracy": correct_positions / expected if expected else 0.0,
        "m03_order_errors": order_errors,
        "m09_mean_rhythm_error_ms": sum(rhythm_errors) / len(rhythm_errors) if rhythm_errors else 0.0,
    }
