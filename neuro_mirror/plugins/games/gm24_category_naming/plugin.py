from __future__ import annotations

import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm24_category_naming.stimuli import CATEGORY_GROUPS, RECORDING_MS
from neuro_mirror.screening.gm24_scoring import score_gm24


def response_matches(transcript: str, answers: tuple[str, ...]) -> bool:
    clean = " ".join(re.findall(r"[а-яё]+", transcript.lower()))
    return any(re.search(rf"(?:^|\s){re.escape(answer)}(?:$|\s)", clean) for answer in answers)


@dataclass(slots=True)
class CategoryNamingSession:
    session_id: str
    trials: list[dict[str, Any]]
    trial_index: int = 0
    shown_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm24CategoryNamingPlugin(BrowserGamePlugin):
    plugin_name = "gm24_category_naming"
    game_code = "GM-24"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, CategoryNamingSession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        trials: list[dict[str, Any]] = []
        for group_index in range(2):
            cycle = [
                {
                    "category": item["category"],
                    "answers": item["answers"],
                    "words": item["groups"][group_index],
                }
                for item in CATEGORY_GROUPS
            ]
            self._random.shuffle(cycle)
            trials.extend(cycle)
        session = CategoryNamingSession(uuid.uuid4().hex, trials)
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        trial = session.trials[session.trial_index]
        transcript = str(payload.get("transcript") or "").strip()
        correct = response_matches(transcript, trial["answers"])
        session.round_events.append(
            {
                "words": list(trial["words"]),
                "expected_category": trial["category"],
                "transcript": transcript,
                "recognized": bool(payload.get("recognized", transcript)),
                "correct": correct,
                "reaction_ms": max(
                    0.0,
                    float(payload.get("duration_ms") or (time.time() * 1000 - session.shown_at_ms)),
                ),
                "valid": bool(transcript),
            }
        )
        session.trial_index += 1
        if session.trial_index >= len(session.trials):
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "correct": correct,
                "events": events,
                "metrics": score_gm24(events),
            }
        session.shown_at_ms = time.time() * 1000
        result = self._payload(session)
        result["previous_correct"] = correct
        return result

    @staticmethod
    def _payload(session: CategoryNamingSession) -> dict[str, Any]:
        trial = session.trials[session.trial_index]
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "trial_number": session.trial_index + 1,
            "trial_count": len(session.trials),
            "words": list(trial["words"]),
            "recording_ms": RECORDING_MS,
        }
