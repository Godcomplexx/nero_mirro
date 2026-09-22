from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm17_mental_rotation.stimuli import SHAPES, TRIAL_COUNT
from neuro_mirror.screening.gm17_scoring import score_gm17_trials


@dataclass(slots=True)
class RotationSession:
    session_id: str
    shape_order: list[str]
    trial_index: int = 0
    correct_choice_id: str = ""
    current_trial: dict[str, Any] = field(default_factory=dict)
    shown_at_ms: float = 0.0
    trials: list[dict[str, Any]] = field(default_factory=list)


class Gm17MentalRotationPlugin(BrowserGamePlugin):
    plugin_name = "gm17_mental_rotation"
    game_code = "GM-17"
    start_handler = "_start_session"
    answer_handler = "_check_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, RotationSession] = {}
        self._random = secrets.SystemRandom()

    def _start_session(self) -> dict[str, Any]:
        keys = list(SHAPES)
        shape_order = [self._random.choice(keys) for _ in range(TRIAL_COUNT)]
        session = RotationSession(uuid.uuid4().hex, shape_order)
        self._sessions[session.session_id] = session
        return self._prepare_trial(session)

    def _prepare_trial(self, session: RotationSession) -> dict[str, Any]:
        shape_key = session.shape_order[session.trial_index]
        distractor_key = self._random.choice([key for key in SHAPES if key != shape_key])
        correct_rotation = self._random.choice((90, 180, 270))
        distractor_rotation = self._random.choice((90, 180, 270))
        correct_choice_id = uuid.uuid4().hex
        distractor_choice_id = uuid.uuid4().hex
        choices = [
            {
                "id": correct_choice_id,
                "points": SHAPES[shape_key],
                "rotation": correct_rotation,
            },
            {
                "id": distractor_choice_id,
                "points": SHAPES[distractor_key],
                "rotation": distractor_rotation,
            },
        ]
        self._random.shuffle(choices)
        session.correct_choice_id = correct_choice_id
        session.current_trial = {
            "trial": session.trial_index + 1,
            "sample_shape": shape_key,
            "sample_points": SHAPES[shape_key],
            "choices": choices,
            "correct_rotation": correct_rotation,
        }
        session.shown_at_ms = time.time() * 1000
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "trial": session.trial_index + 1,
            "trial_count": TRIAL_COUNT,
            "sample": {"points": SHAPES[shape_key], "rotation": 0},
            "choices": choices,
        }

    def _check_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "")
        session = self._sessions.get(session_id)
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        selected_id = str(payload.get("selected_id") or "")
        valid_ids = {choice["id"] for choice in session.current_trial["choices"]}
        if selected_id not in valid_ids:
            return {"ok": False, "message": "Некорректный вариант ответа."}

        now_ms = time.time() * 1000
        session.trials.append(
            {
                **session.current_trial,
                "selected_id": selected_id,
                "correct": selected_id == session.correct_choice_id,
                "reaction_ms": max(0.0, now_ms - session.shown_at_ms),
                "client_timestamp_ms": payload.get("timestamp_ms"),
            }
        )
        session.trial_index += 1
        if session.trial_index >= TRIAL_COUNT:
            self._sessions.pop(session_id, None)
            return {
                "ok": True,
                "finished": True,
                "metrics": score_gm17_trials(session.trials),
                "events": session.trials,
            }
        return self._prepare_trial(session)
