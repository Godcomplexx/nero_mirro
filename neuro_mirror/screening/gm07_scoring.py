from __future__ import annotations

import math
import statistics
from typing import Any


def _corrected_rate(successes: int, total: int) -> float | None:
    if total <= 0:
        return None
    return (successes + 0.5) / (total + 1.0)


def score_gm07_trials(
    trials: list[dict[str, Any]], *, expected_trial_count: int = 10
) -> dict[str, Any]:
    """Calculate GM-07 metrics from completed first-response trials."""
    target_trials = [trial for trial in trials if trial.get("target_present") is True]
    no_target_trials = [trial for trial in trials if trial.get("target_present") is False]
    hits = sum(1 for trial in target_trials if trial.get("correct") is True)
    false_alarms = sum(
        1 for trial in no_target_trials if trial.get("response_kind") == "stimulus"
    )
    omissions = len(target_trials) - hits

    correct_times = [
        float(trial["reaction_ms"])
        for trial in trials
        if trial.get("correct") is True and trial.get("reaction_ms") is not None
    ]
    hit_rate = _corrected_rate(hits, len(target_trials))
    false_alarm_rate = _corrected_rate(false_alarms, len(no_target_trials))
    sensitivity = None
    criterion = None
    if hit_rate is not None and false_alarm_rate is not None:
        normal = statistics.NormalDist()
        hit_z = normal.inv_cdf(hit_rate)
        false_alarm_z = normal.inv_cdf(false_alarm_rate)
        sensitivity = hit_z - false_alarm_z
        criterion = -0.5 * (hit_z + false_alarm_z)

    return {
        "g07_omission_rate": omissions / len(target_trials) if target_trials else None,
        "g08_false_alarm_rate": (
            false_alarms / len(no_target_trials) if no_target_trials else None
        ),
        "a01_detection_sensitivity": sensitivity,
        "a02_response_criterion": criterion,
        "g03_median_reaction_ms": statistics.median(correct_times) if correct_times else None,
        "g05_reaction_variability_ms": (
            statistics.pstdev(correct_times) if len(correct_times) > 1 else 0.0
        ) if correct_times else None,
        "u01_correct_action_rate": (
            sum(1 for trial in trials if trial.get("correct") is True) / len(trials)
            if trials else None
        ),
        "u06_complete": len(trials) == expected_trial_count,
        "u06_technically_valid": all(
            math.isfinite(float(trial.get("reaction_ms", -1)))
            and float(trial.get("reaction_ms", -1)) >= 0
            for trial in trials
        ),
    }
