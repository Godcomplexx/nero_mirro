from __future__ import annotations

import statistics
from typing import Any


def score_gm20_trials(
    trials: list[dict[str, Any]], *, expected_trial_count: int = 60
) -> dict[str, Any]:
    """Calculate GM-20 accuracy, switching and rule-adherence metrics."""
    correct_count = sum(1 for trial in trials if trial.get("correct") is True)
    perseverative_errors = sum(
        1
        for trial in trials
        if trial.get("correct") is False
        and trial.get("previous_rule")
        and trial.get("selected_reference")
        == (trial.get("matches") or {}).get(trial.get("previous_rule"))
    )
    rule_violations = sum(
        1
        for trial in trials
        if trial.get("selected_reference") not in set((trial.get("matches") or {}).values())
    )
    switch_times = [
        float(trial["reaction_ms"])
        for trial in trials
        if trial.get("correct") is True
        and int(trial.get("trials_since_switch") or 0) <= 3
        and trial.get("previous_rule")
    ]
    stable_times = [
        float(trial["reaction_ms"])
        for trial in trials
        if trial.get("correct") is True
        and int(trial.get("trials_since_switch") or 0) > 3
    ]
    switch_cost = None
    if switch_times and stable_times:
        switch_cost = statistics.median(switch_times) - statistics.median(stable_times)

    return {
        "u01_correct_action_rate": correct_count / len(trials) if trials else None,
        "e06_perseverative_errors": perseverative_errors,
        "e07_switch_cost_ms": switch_cost,
        "e05_rule_violations": rule_violations,
        "u06_complete": len(trials) == expected_trial_count,
        "u06_technically_valid": all(
            trial.get("selected_reference") is not None
            and float(trial.get("reaction_ms", -1)) >= 0
            for trial in trials
        ),
    }
