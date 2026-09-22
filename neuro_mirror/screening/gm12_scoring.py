from __future__ import annotations
import statistics
from typing import Any

def score_gm12_trials(trials: list[dict[str, Any]], *, expected_trials: int = 10) -> dict[str, Any]:
    correct = [item for item in trials if item.get("correct") is True]
    times = [float(item["reaction_ms"]) for item in correct]
    return {"u01_correct_action_rate": len(correct) / len(trials) if trials else None,
            "l01_stimulus_accuracy": len(correct) / len(trials) if trials else None,
            "g03_median_reaction_ms": statistics.median(times) if times else None,
            "u07_error_count": len(trials) - len(correct),
            "u06_complete": len(trials) == expected_trials,
            "u06_technically_valid": all(item.get("selected_word") for item in trials)}
