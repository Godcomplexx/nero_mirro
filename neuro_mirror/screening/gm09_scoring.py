"""Pure scoring for GM-09."""
from __future__ import annotations


def score_gm09(events: list[dict]) -> dict[str, float | int]:
    total_targets = sum(len(item.get("targets") or ()) for item in events)
    hits = sum(len(set(item.get("targets") or ()) & set(item.get("selected") or ())) for item in events)
    return {
        "a06_tracking_accuracy": hits / total_targets if total_targets else 0.0,
        "u03_correct_rounds": sum(bool(item.get("correct")) for item in events),
        "u07_error_count": total_targets - hits,
    }
