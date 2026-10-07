from __future__ import annotations

import statistics
from typing import Any


def score_gm17_trials(
    trials: list[dict[str, Any]], *, expected_trial_count: int = 10
) -> dict[str, Any]:
    """Calculate GM-17 first-response metrics."""
    correct_count = sum(1 for trial in trials if trial.get("correct") is True)
    correct_times = [
        float(trial["reaction_ms"])
        for trial in trials
        if trial.get("correct") is True and trial.get("reaction_ms") is not None
    ]
    return {
        "u01_correct_action_rate": correct_count / len(trials) if trials else None,
        "g03_median_reaction_ms": statistics.median(correct_times) if correct_times else None,
        "u07_error_count": len(trials) - correct_count,
        "u06_complete": len(trials) == expected_trial_count,
        "u06_technically_valid": all(
            trial.get("selected_id") is not None
            and float(trial.get("reaction_ms", -1)) >= 0
            for trial in trials
        ),
    }
