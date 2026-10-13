from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm16_phonemic_fluency.stimuli import MAX_RECORDING_MS
from neuro_mirror.screening.gm16_scoring import analyse_phonemic_response, score_gm16


@dataclass(slots=True)
class FluencySession:
    session_id: str
    letter: str
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    shown_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm16PhonemicFluencyPlugin(BrowserGamePlugin):
    plugin_name = "gm16_phonemic_fluency"
    game_code = "GM-16"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, FluencySession] = {}
        self._random = secrets.SystemRandom()

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
        session = FluencySession(
            uuid.uuid4().hex,
            self._random.choice(tuple(parameters["letters"])),
            level,
            parameters,
        )
        self._sessions[session.session_id] = session
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "letter": session.letter,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": dict(session.difficulty_parameters),
            "recording_ms": int(session.difficulty_parameters.get("max_recording_ms", MAX_RECORDING_MS)),
        }

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        transcript = str(payload.get("transcript") or "").strip()
        analysis = analyse_phonemic_response(transcript, session.letter)
        duration_ms = max(
            0.0,
            float(payload.get("duration_ms") or (time.time() * 1000 - session.shown_at_ms)),
        )
        event = {
            "letter": session.letter,
            "transcript": transcript,
            "recognized": bool(payload.get("recognized", transcript)),
            "tokens": analysis["tokens"],
            "valid_words": analysis["valid_words"],
            "invalid_words": analysis["invalid_words"],
            "repetitions": analysis["repetitions"],
            "duration_ms": duration_ms,
            "valid": bool(transcript),
        }
        session.round_events.append(event)
        events = list(session.round_events)
        self._sessions.pop(session.session_id, None)
        return {
            "ok": True,
            "finished": True,
            "events": events,
            "metrics": score_gm16(events, expected_rounds=1),
        }
