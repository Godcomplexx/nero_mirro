from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.screening.gm22_scoring import score_gm22


@dataclass(slots=True)
class TowerSession:
    session_id: str
    difficulty_level: int
    disk_count: int
    difficulty_parameters: dict[str, Any]
    started_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    level_started_at_ms: float = 0.0
    first_move_at_ms: float | None = None
    level_index: int = 0
    rods: list[list[int]] = field(default_factory=list)
    level_valid_moves: int = 0
    level_invalid_moves: int = 0
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm22TowerPlugin(BrowserGamePlugin):
    plugin_name = "gm22_tower"
    game_code = "GM-22"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, TowerSession] = {}

    def _disk_count(self, session: TowerSession) -> int:
        return session.disk_count

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._start(difficulty_level=payload.get("difficulty_level"))

    def _start(self, *, difficulty_level: object = None) -> dict[str, Any]:
        config = level_config(self.game_code)
        try:
            level = int(difficulty_level or config["default_level"])
        except (TypeError, ValueError):
            level = int(config["default_level"])
        available_levels = {int(item["level"]): item for item in config["levels"]}
        if level not in available_levels:
            level = int(config["default_level"])
        parameters = dict(available_levels[level]["parameters"])
        session = TowerSession(
            uuid.uuid4().hex, level, int(parameters["elements"]), parameters
        )
        self._sessions[session.session_id] = session
        return self._prepare_level(session)

    def _prepare_level(self, session: TowerSession) -> dict[str, Any]:
        disk_count = self._disk_count(session)
        rod_count = int(session.difficulty_parameters["rod_count"])
        session.rods = [list(range(disk_count, 0, -1))] + [
            [] for _ in range(rod_count - 1)
        ]
        session.level_valid_moves = 0
        session.level_invalid_moves = 0
        session.level_started_at_ms = time.time() * 1000
        session.first_move_at_ms = None
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        try:
            source = int(payload.get("source_rod"))
            target = int(payload.get("target_rod"))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Некорректный ход."}
        rod_count = int(session.difficulty_parameters["rod_count"])
        if source not in range(rod_count) or target not in range(rod_count) or source == target:
            return {"ok": False, "message": "Некорректный ход."}

        now_ms = time.time() * 1000
        if session.first_move_at_ms is None:
            session.first_move_at_ms = now_ms
        source_rod = session.rods[source]
        target_rod = session.rods[target]
        disk = source_rod[-1] if source_rod else None
        legal_move = disk is not None and (not target_rod or disk < target_rod[-1])
        if legal_move:
            target_rod.append(source_rod.pop())
            session.level_valid_moves += 1
        else:
            session.level_invalid_moves += 1

        disk_count = self._disk_count(session)
        solved = session.rods[-1] == list(range(disk_count, 0, -1))
        event = {
            "level": session.level_index + 1,
            "disk_count": disk_count,
            "ruleset": str(session.difficulty_parameters["ruleset"]),
            "rod_count": rod_count,
            "selected_source": source,
            "selected_target": target,
            "disk": disk,
            # The response was captured correctly; move legality is a game outcome.
            "valid": True,
            "legal_move": legal_move,
            "correct": legal_move,
            "level_complete": solved,
            "elapsed_ms": max(0.0, now_ms - session.level_started_at_ms),
        }
        if solved:
            event.update(
                {
                    "level_moves": session.level_valid_moves,
                    "level_invalid_moves": session.level_invalid_moves,
                    "minimum_moves": 2**disk_count - 1,
                    "planning_ms": max(
                        0.0, (session.first_move_at_ms or now_ms) - session.level_started_at_ms
                    ),
                    "execution_ms": max(0.0, now_ms - (session.first_move_at_ms or now_ms)),
                }
            )
        session.round_events.append(event)

        if not solved:
            result = self._payload(session)
            result["move_valid"] = legal_move
            return result

        elapsed_ms = now_ms - session.started_at_ms
        events = list(session.round_events)
        self._sessions.pop(session.session_id, None)
        return {"ok": True, "finished": True, "events": events, "metrics": score_gm22(events, elapsed_ms, required_levels=1)}

    def _payload(self, session: TowerSession) -> dict[str, Any]:
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": dict(session.difficulty_parameters),
            "level_number": 1,
            "required_levels": 1,
            "bonus": False,
            "disk_count": self._disk_count(session),
            "rods": [list(rod) for rod in session.rods],
            "move_count": session.level_valid_moves,
            "invalid_move_count": session.level_invalid_moves,
        }
