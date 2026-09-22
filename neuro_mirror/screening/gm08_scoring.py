from __future__ import annotations
import statistics
from typing import Any

def score_gm08_trials(trials: list[dict[str, Any]], *, expected_trials: int = 40) -> dict[str, Any]:
    go = [t for t in trials if not t["stop_signal"]]; stop = [t for t in trials if t["stop_signal"]]
    omissions = sum(1 for t in go if not t["responded"]); false = sum(1 for t in stop if t["responded"])
    times = [float(t["reaction_ms"]) for t in go if t["responded"] and t.get("reaction_ms") is not None]
    return {"g08_false_alarm_rate": false / len(stop) if stop else None,
            "g07_omission_rate": omissions / len(go) if go else None,
            "g03_median_reaction_ms": statistics.median(times) if times else None,
            "g05_reaction_variability_ms": statistics.pstdev(times) if len(times) > 1 else (0.0 if times else None),
            "u07_error_count": false + omissions, "u06_complete": len(trials) == expected_trials,
            "u06_technically_valid": all(isinstance(t.get("responded"), bool) for t in trials)}
