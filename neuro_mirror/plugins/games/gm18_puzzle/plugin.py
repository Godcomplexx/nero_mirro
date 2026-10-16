from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm18_puzzle.stimuli import (
    BONUS_PUZZLE,
    PUZZLES_BY_LEVEL,
)
from neuro_mirror.screening.gm18_scoring import score_gm18


@dataclass(slots=True)
class PuzzleSession:
    session_id: str
    puzzles: list[dict[str, Any]]
    stimulus_set: str
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    started_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_started_at_ms: float = 0.0
    round_index: int = 0
    pieces: list[int] = field(default_factory=list)
    placements: list[int | None] = field(default_factory=list)
    move_count: int = 0
    minimum_move_count: int = 0
    attempted_pieces: set[int] = field(default_factory=set)
    first_placement_correct: int = 0
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm18PuzzlePlugin(BrowserGamePlugin):
    plugin_name = "gm18_puzzle"
    game_code = "GM-18"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, PuzzleSession] = {}
        self._random = secrets.SystemRandom()

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._start(stimulus_set=str(payload.get("stimulus_set") or ""), difficulty_level=payload.get("difficulty_level"))

    def _start(self, *, stimulus_set: str = "", difficulty_level: object = None) -> dict[str, Any]:
        config = level_config(self.game_code)
        try:
            level = int(difficulty_level or config["default_level"])
        except (TypeError, ValueError):
            level = int(config["default_level"])
        available_levels = {int(item["level"]): item for item in config["levels"]}
        if level not in available_levels:
            level = int(config["default_level"])
        parameters = dict(available_levels[level]["parameters"])
        available = tuple(self.definition.stimulus_sets)
        expected_set = available[min(level - 1, len(available) - 1)]
        selected = stimulus_set if stimulus_set == expected_set else expected_set
        columns, rows = (
            int(value)
            for value in str(parameters["grid"]).lower().replace("×", "x").split("x")
        )
        if rows * columns != int(parameters["pieces"]):
            raise RuntimeError(f"Некорректная сетка сложности GM-18: {parameters!r}")
        puzzles = [
            {**source, "rows": rows, "columns": columns}
            for source in PUZZLES_BY_LEVEL[level][:int(parameters["puzzles"])]
        ]
        self._random.shuffle(puzzles)
        session = PuzzleSession(uuid.uuid4().hex, puzzles, selected, level, parameters)
        self._sessions[session.session_id] = session
        return self._prepare_round(session)

    def _puzzle(self, session: PuzzleSession) -> dict[str, Any]:
        return session.puzzles[session.round_index] if session.round_index < len(session.puzzles) else BONUS_PUZZLE

    def _prepare_round(self, session: PuzzleSession) -> dict[str, Any]:
        puzzle = self._puzzle(session)
        count = puzzle["rows"] * puzzle["columns"]
        session.pieces = list(range(count))
        self._random.shuffle(session.pieces)
        session.placements = [None] * count
        session.move_count = 0
        session.minimum_move_count = count
        session.attempted_pieces.clear()
        session.first_placement_correct = 0
        session.round_started_at_ms = time.time() * 1000
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        try:
            piece = int(payload.get("piece_id"))
            target = int(payload.get("target_index"))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Некорректный ход."}
        if (
            piece not in session.pieces
            or not (0 <= target < len(session.placements))
            or session.placements[target] is not None
        ):
            return {"ok": False, "message": "Некорректный ход."}

        placement_correct = piece == target
        if piece not in session.attempted_pieces and placement_correct:
            session.first_placement_correct += 1
        session.attempted_pieces.add(piece)
        session.move_count += 1
        if placement_correct:
            session.placements[target] = piece
            session.pieces.remove(piece)
        solved = not session.pieces
        if not solved:
            result = self._payload(session)
            result["placement_correct"] = placement_correct
            return result

        now_ms = time.time() * 1000
        puzzle = self._puzzle(session)
        session.round_events.append(
            {
                "puzzle": puzzle["name"],
                "grid": f"{puzzle['columns']}x{puzzle['rows']}",
                "placements": list(session.placements),
                "moves": session.move_count,
                "minimum_moves": session.minimum_move_count,
                "piece_count": len(session.placements),
                "first_placement_correct": session.first_placement_correct,
                "duration_ms": max(0.0, now_ms - session.round_started_at_ms),
                "correct": True,
            }
        )
        session.round_index += 1
        elapsed_ms = now_ms - session.started_at_ms
        if session.round_index >= len(session.puzzles):
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "events": events,
                "metrics": score_gm18(
                    events, elapsed_ms, expected_puzzles=len(session.puzzles)
                ),
            }
        return self._prepare_round(session)

    def _payload(self, session: PuzzleSession) -> dict[str, Any]:
        puzzle = self._puzzle(session)
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "stimulus_set": session.stimulus_set,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": dict(session.difficulty_parameters),
            "round_number": session.round_index + 1,
            "required_rounds": len(session.puzzles),
            "bonus": session.round_index >= len(session.puzzles),
            "name": puzzle["name"],
            "image": puzzle["image"],
            "rows": puzzle["rows"],
            "columns": puzzle["columns"],
            "pieces": list(session.pieces),
            "placements": list(session.placements),
            "move_count": session.move_count,
        }
