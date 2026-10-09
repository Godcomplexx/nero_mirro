"""Pure scoring for GM-03."""
from __future__ import annotations

import math


def score_gm03(events: list[dict], *, expected_rooms: int) -> dict[str, float | int]:
    total = len(events)
    correct = sum(bool(item.get("correct")) for item in events)
    distances = []
    for item in events:
        expected = item.get("expected") or [0, 0]
        selected = item.get("selected") or [0, 0]
        distances.append(math.dist(expected, selected))
    return {
        "u01_correct_action_rate": correct / total if total else 0.0,
        "u01_correct_actions": correct,
        "u01_actions_total": total,
        "m04_mean_spatial_error": sum(distances) / total if total else 0.0,
        "u07_error_count": total - correct,
        "u06_complete": total >= max(1, expected_rooms),
        # У каждой пробы должна быть и загаданная, и выбранная клетка: без
        # них расстояние между ними ничего не значит.
        "u06_technically_valid": bool(events) and all(
            item.get("expected") and item.get("selected") for item in events
        ),
    }
