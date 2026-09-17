from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.screening.gm17_scoring import score_gm17_trials


TRIAL_COUNT = 10
SHAPES: dict[str, list[list[int]]] = {
    "step": [[18, 18], [58, 18], [58, 38], [82, 38], [82, 82], [42, 82], [42, 62], [18, 62]],
    "flag": [[18, 12], [78, 12], [60, 35], [78, 58], [34, 58], [34, 88], [18, 88]],
    "hook": [[18, 16], [50, 16], [50, 58], [82, 58], [82, 84], [18, 84]],
    "arrow": [[15, 38], [55, 38], [55, 18], [86, 50], [55, 82], [55, 62], [15, 62]],
    "kite": [[50, 12], [84, 44], [66, 86], [28, 72], [16, 34]],
    "zig": [[18, 14], [72, 14], [54, 43], [84, 43], [30, 88], [44, 56], [16, 56]],
}


@dataclass(slots=True)
class RotationSession:
    session_id: str
    shape_order: list[str]
    trial_index: int = 0
    correct_choice_id: str = ""
    current_trial: dict[str, Any] = field(default_factory=dict)
    shown_at_ms: float = 0.0
    trials: list[dict[str, Any]] = field(default_factory=list)


class Gm17MentalRotationPlugin(Plugin):
    plugin_name = "gm17_mental_rotation"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, RotationSession] = {}
        self._random = secrets.SystemRandom()

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.REQ_GM17_START, Topics.REQ_GM17_ANSWER)

    async def handle_event(self, event: Event) -> None:
        request_id = str(event.payload.get("_request_id") or "")
        if event.topic == Topics.REQ_GM17_START:
            payload = self._start_session()
            topic = Topics.RESP_GM17_START
        else:
            payload = self._check_answer(event.payload)
            topic = Topics.RESP_GM17_ANSWER
        payload["_reply_to"] = request_id
        await self.bus.publish(Event(topic=topic, source=self.name, payload=payload))

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
