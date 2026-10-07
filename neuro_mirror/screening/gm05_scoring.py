from __future__ import annotations

import statistics
from typing import Any


def score_gm05_rounds(rounds: list[dict[str, Any]], *, expected_rounds: int = 3) -> dict[str, Any]:
    targets = sum(len(item["targets"]) for item in rounds)
    distractors = sum(len(item["distractors"]) for item in rounds)
    hits = sum(len(set(item["selected"]) & set(item["targets"])) for item in rounds)
    false_alarms = sum(len(set(item["selected"]) & set(item["distractors"])) for item in rounds)
    hit_rate = hits / targets if targets else None
    false_rate = false_alarms / distractors if distractors else None
    sensitivity = None
    if targets and distractors:
        normal = statistics.NormalDist()
        corrected_hit = (hits + 0.5) / (targets + 1)
        corrected_false = (false_alarms + 0.5) / (distractors + 1)
        sensitivity = normal.inv_cdf(corrected_hit) - normal.inv_cdf(corrected_false)
    return {
        "m07_target_recognition_rate": hit_rate,
        "g08_false_alarm_rate": false_rate,
        "m10_recognition_sensitivity": sensitivity,
        "u04_duration_ms": sum(float(item.get("duration_ms") or 0) for item in rounds),
        "u06_complete": len(rounds) == expected_rounds,
        "u06_technically_valid": all(bool(item.get("selected") is not None) for item in rounds),
    }
