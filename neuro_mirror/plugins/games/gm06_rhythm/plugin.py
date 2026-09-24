from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm06_rhythm.stimuli import BUTTONS, INTERVALS_MS, ROUNDS, START_LENGTH
from neuro_mirror.screening.gm06_scoring import score_gm06


@dataclass(slots=True)
class RhythmSession:
    session_id: str
    rounds: list[dict[str, Any]]
    round_index: int = 0
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm06RhythmPlugin(BrowserGamePlugin):
    plugin_name = "gm06_rhythm"
    game_code = "GM-06"
    start_handler = "_start"
    answer_handler = "_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, RhythmSession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        rounds = []
        for index in range(ROUNDS):
            length = START_LENGTH + index
            rounds.append({
                "sequence": [self._random.choice(BUTTONS) for _ in range(length)],
                "intervals": [self._random.choice(INTERVALS_MS) for _ in range(max(0, length - 1))],
            })
        session = RhythmSession(uuid.uuid4().hex, rounds)
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        selected = payload.get("selected_sequence")
        intervals = payload.get("selected_intervals_ms")
        if not isinstance(selected, list) or not isinstance(intervals, list):
            return {"ok": False, "message": "Ответ имеет неверный формат."}
        current = session.rounds[session.round_index]
        expected = current["sequence"]
        expected_intervals = current["intervals"]
        correct_positions = sum(a == b for a, b in zip(expected, selected))
        comparable = min(len(expected_intervals), len(intervals))
        rhythm_error = (
            sum(abs(float(intervals[i]) - expected_intervals[i]) for i in range(comparable)) / comparable
            if comparable else 0.0
        )
        event = {
            "round": session.round_index + 1,
            "expected_sequence": expected,
            "selected_sequence": selected,
            "expected_intervals_ms": expected_intervals,
            "selected_intervals_ms": intervals,
            "correct_positions": correct_positions,
            "correct": selected == expected,
            "rhythm_error_ms": rhythm_error,
        }
        session.round_events.append(event)
        session.round_index += 1
        if session.round_index >= len(session.rounds):
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {"ok": True, "finished": True, "correct": event["correct"], "events": events, "metrics": score_gm06(events)}
        result = self._payload(session)
        result["correct"] = event["correct"]
        return result

    def _payload(self, session: RhythmSession) -> dict[str, Any]:
        current = session.rounds[session.round_index]
        return {
            "ok": True, "finished": False, "session_id": session.session_id,
            "round": session.round_index + 1, "round_count": len(session.rounds),
            "sequence": current["sequence"], "intervals_ms": current["intervals"],
            "sequence_length": len(current["sequence"]),
        }
