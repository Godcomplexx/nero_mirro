from __future__ import annotations
from typing import Any

def score_gm19_mazes(mazes: list[dict[str, Any]], *, expected_mazes: int = 3) -> dict[str, Any]:
    redundancies = []
    for maze in mazes:
        shortest = max(1, int(maze["shortest_steps"])); actual = max(0, len(maze["path"]) - 1)
        redundancies.append(max(0, actual - shortest) / shortest)
    return {"v02_path_redundancy": sum(redundancies) / len(redundancies) if redundancies else None,
            "u08_completion_rate": len(mazes) / expected_mazes,
            "e03_planning_time_ms": sum(float(m.get("planning_ms") or 0) for m in mazes),
            "e04_execution_time_ms": sum(float(m.get("execution_ms") or 0) for m in mazes),
            "v03_boundary_exits": sum(int(m.get("boundary_errors") or 0) for m in mazes),
            "u06_complete": len(mazes) == expected_mazes,
            "u06_technically_valid": all(m.get("valid_path") for m in mazes)}
