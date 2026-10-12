"""Pure scoring for GM-09."""
from __future__ import annotations


def score_gm09(events: list[dict], *, expected_rounds: int) -> dict[str, float | int]:
    total_targets = sum(len(item.get("targets") or ()) for item in events)
    hits = sum(len(set(item.get("targets") or ()) & set(item.get("selected") or ())) for item in events)
    return {
        "a06_tracking_accuracy": hits / total_targets if total_targets else 0.0,
        "a06_tracked_targets": hits,
        "a06_targets_total": total_targets,
        "u03_correct_rounds": sum(bool(item.get("correct")) for item in events),
        "u07_error_count": total_targets - hits,
        "u06_complete": len(events) >= max(1, expected_rounds),
        # В раунде должны быть отслеживаемые объекты: иначе задание не
        # предъявилось, и точность слежения ничего не выражает.
        "u06_technically_valid": bool(events) and total_targets > 0,
    }
