from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm18_puzzle.stimuli import (
    BONUS_PUZZLE,
    MINIMUM_SESSION_MS,
    PUZZLES,
)
from neuro_mirror.screening.gm18_scoring import score_gm18


def minimum_swaps(board: list[int]) -> int:
    visited = [False] * len(board)
    cycles = 0
    for start in range(len(board)):
        if visited[start]:
            continue
        cycles += 1
        current = start
        while not visited[current]:
            visited[current] = True
            current = board[current]
    return len(board) - cycles


@dataclass(slots=True)
class PuzzleSession:
    session_id: str
    started_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_started_at_ms: float = 0.0
    round_index: int = 0
    board: list[int] = field(default_factory=list)
    initial_board: list[int] = field(default_factory=list)
    move_count: int = 0
    minimum_move_count: int = 0
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm18PuzzlePlugin(BrowserGamePlugin):
    plugin_name = "gm18_puzzle"
    game_code = "GM-18"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, PuzzleSession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        session = PuzzleSession(uuid.uuid4().hex)
        self._sessions[session.session_id] = session
        return self._prepare_round(session)

    def _puzzle(self, session: PuzzleSession) -> dict[str, Any]:
        return PUZZLES[session.round_index] if session.round_index < len(PUZZLES) else BONUS_PUZZLE

    def _prepare_round(self, session: PuzzleSession) -> dict[str, Any]:
        puzzle = self._puzzle(session)
        count = puzzle["rows"] * puzzle["columns"]
        board = list(range(count))
        while board == list(range(count)):
            self._random.shuffle(board)
        session.board = board
        session.initial_board = list(board)
        session.move_count = 0
        session.minimum_move_count = minimum_swaps(board)
        session.round_started_at_ms = time.time() * 1000
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        try:
            first = int(payload.get("first_index"))
            second = int(payload.get("second_index"))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Некорректный ход."}
        if first == second or not (0 <= first < len(session.board)) or not (0 <= second < len(session.board)):
            return {"ok": False, "message": "Некорректный ход."}

        session.board[first], session.board[second] = session.board[second], session.board[first]
        session.move_count += 1
        solved = session.board == list(range(len(session.board)))
        if not solved:
            return self._payload(session)

        now_ms = time.time() * 1000
        puzzle = self._puzzle(session)
        session.round_events.append(
            {
                "puzzle": puzzle["name"],
                "grid": f"{puzzle['columns']}x{puzzle['rows']}",
                "placements": list(session.initial_board),
                "moves": session.move_count,
                "minimum_moves": session.minimum_move_count,
                "duration_ms": max(0.0, now_ms - session.round_started_at_ms),
                "correct": True,
            }
        )
        session.round_index += 1
        elapsed_ms = now_ms - session.started_at_ms
        if session.round_index >= len(PUZZLES) and elapsed_ms >= MINIMUM_SESSION_MS:
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "events": events,
                "metrics": score_gm18(events, elapsed_ms),
            }
        return self._prepare_round(session)

    def _payload(self, session: PuzzleSession) -> dict[str, Any]:
        puzzle = self._puzzle(session)
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "round_number": session.round_index + 1,
            "required_rounds": len(PUZZLES),
            "bonus": session.round_index >= len(PUZZLES),
            "name": puzzle["name"],
            "image": puzzle["image"],
            "rows": puzzle["rows"],
            "columns": puzzle["columns"],
            "board": list(session.board),
            "move_count": session.move_count,
        }
