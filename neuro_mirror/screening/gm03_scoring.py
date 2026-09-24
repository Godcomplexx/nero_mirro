"""Pure scoring for GM-03."""
from __future__ import annotations

import math


def score_gm03(events: list[dict]) -> dict[str, float | int]:
    total = len(events)
    correct = sum(bool(item.get("correct")) for item in events)
    distances = []
    for item in events:
        expected = item.get("expected") or [0, 0]
        selected = item.get("selected") or [0, 0]
        distances.append(math.dist(expected, selected))
    return {
        "u01_correct_action_rate": correct / total if total else 0.0,
        "m04_mean_spatial_error": sum(distances) / total if total else 0.0,
        "u07_error_count": total - correct,
    }
