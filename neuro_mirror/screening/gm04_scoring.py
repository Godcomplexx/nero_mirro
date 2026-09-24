"""Pure final-set scoring for GM-04."""
from __future__ import annotations


def score_gm04(events: list[dict]) -> dict[str, float | int]:
    targets = sum(len(item.get("targets") or ()) for item in events)
    hits = sum(len(set(item.get("targets") or ()) & set(item.get("selected") or ())) for item in events)
    selected = sum(len(item.get("selected") or ()) for item in events)
    false_hits = sum(len(set(item.get("selected") or ()) - set(item.get("targets") or ())) for item in events)
    return {
        "m07_target_recognition_rate": hits / targets if targets else 0.0,
        "g08_false_alarm_rate": false_hits / selected if selected else 0.0,
        "m04_spatial_error_count": sum(int(item.get("spatial_errors") or 0) for item in events),
        "u03_correct_rounds": sum(bool(item.get("correct")) for item in events),
    }
