from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm04_location.stimuli import GRID_SIZE, MAX_TARGETS, MIN_TARGETS, ROUNDS, STUDY_SECONDS
from neuro_mirror.screening.gm04_scoring import score_gm04


@dataclass(slots=True)
class PatternSession:
    session_id: str
    patterns: list[list[int]]
    difficulty_level: int
    grid_size: int
    target_range: tuple[int, int]
    round_index: int = 0
    phase: str = "study"
    shown_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm04LocationPlugin(BrowserGamePlugin):
    plugin_name = "gm04_location"
    game_code = "GM-04"
    start_handler = "_start"
    answer_handler = "_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, PatternSession] = {}
        self._random = secrets.SystemRandom()

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._start(difficulty_level=payload.get("difficulty_level"))

    def _start(self, *, difficulty_level: object = None) -> dict[str, Any]:
        try:
            level = min(3, max(1, int(difficulty_level or 1)))
        except (TypeError, ValueError):
            level = 1
        grid_size, minimum, maximum = ((4, 3, 5), (8, 4, 7), (10, 6, 10))[level - 1]
        patterns = [
            sorted(self._random.sample(range(grid_size ** 2), self._random.randint(minimum, maximum)))
            for _ in range(ROUNDS)
        ]
        session = PatternSession(uuid.uuid4().hex, patterns, level, grid_size, (minimum, maximum))
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        if session.phase == "study":
            if payload.get("action") != "begin_recall":
                return {"ok": False, "message": "Сначала запомните расположение."}
            session.phase = "recall"
            session.shown_ms = time.time() * 1000
            return self._payload(session)

        selected_raw = payload.get("selected")
        if not isinstance(selected_raw, list):
            return {"ok": False, "message": "Ответ должен содержать выбранные клетки."}
        selected = sorted({int(value) for value in selected_raw if 0 <= int(value) < session.grid_size ** 2})
        targets = session.patterns[session.round_index]
        spatial_errors = len(set(targets) ^ set(selected))
        event = {
            "round": session.round_index + 1,
            "targets": targets,
            "selected": selected,
            "correct": selected == targets,
            "spatial_errors": spatial_errors,
            "reaction_ms": max(0.0, time.time() * 1000 - session.shown_ms),
        }
        session.round_events.append(event)
        session.round_index += 1
        session.phase = "study"
        session.shown_ms = time.time() * 1000
        if session.round_index >= len(session.patterns):
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {"ok": True, "finished": True, "correct": event["correct"], "events": events, "metrics": score_gm04(events, expected_rounds=ROUNDS)}
        result = self._payload(session)
        result.update({"correct": event["correct"], "previous_targets": targets, "previous_selected": selected})
        return result

    def _payload(self, session: PatternSession) -> dict[str, Any]:
        return {
            "ok": True, "finished": False, "session_id": session.session_id,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": {"grid_size": session.grid_size, "minimum_targets": session.target_range[0], "maximum_targets": session.target_range[1]},
            "phase": session.phase, "grid_size": session.grid_size,
            "round": session.round_index + 1, "round_count": len(session.patterns),
            "targets": session.patterns[session.round_index] if session.phase == "study" else [],
            "study_seconds": STUDY_SECONDS,
        }
