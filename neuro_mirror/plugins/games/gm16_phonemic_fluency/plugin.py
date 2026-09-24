from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm16_phonemic_fluency.stimuli import LETTERS, RECORDING_MS
from neuro_mirror.screening.gm16_scoring import analyse_phonemic_response, score_gm16


@dataclass(slots=True)
class FluencySession:
    session_id: str
    letter: str
    shown_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm16PhonemicFluencyPlugin(BrowserGamePlugin):
    plugin_name = "gm16_phonemic_fluency"
    game_code = "GM-16"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, FluencySession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        session = FluencySession(uuid.uuid4().hex, self._random.choice(LETTERS))
        self._sessions[session.session_id] = session
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "letter": session.letter,
            "recording_ms": RECORDING_MS,
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
            "metrics": score_gm16(events),
        }
