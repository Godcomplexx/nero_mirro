from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm17_mental_rotation.stimuli import SHAPE_SETS, TRIAL_COUNT, shape_payload
from neuro_mirror.screening.gm17_scoring import score_gm17_trials


@dataclass(slots=True)
class RotationSession:
    session_id: str
    shape_order: list[str]
    stimulus_set: str
    difficulty_level: int
    choice_count: int
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

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._start_session(stimulus_set=str(payload.get("stimulus_set") or ""), difficulty_level=payload.get("difficulty_level"))

    def _start_session(self, *, stimulus_set: str = "", difficulty_level: object = None) -> dict[str, Any]:
        try: level = min(3, max(1, int(difficulty_level or 1)))
        except (TypeError, ValueError): level = 1
        choice_count = (2, 3, 4)[level - 1]
        available = tuple(name for name in self.definition.stimulus_sets if name in SHAPE_SETS) or tuple(SHAPE_SETS)
        selected = stimulus_set if stimulus_set in available else available[0]
        keys = list(SHAPE_SETS[selected])
        # Build shuffled cycles so all figures occur with similar frequency
        # and the same figure never appears twice in a row between cycles.
        shape_order: list[str] = []
        while len(shape_order) < TRIAL_COUNT:
            cycle = list(keys)
            self._random.shuffle(cycle)
            if shape_order and cycle[0] == shape_order[-1]:
                cycle[0], cycle[1] = cycle[1], cycle[0]
            shape_order.extend(cycle)
        shape_order = shape_order[:TRIAL_COUNT]
        session = RotationSession(uuid.uuid4().hex, shape_order, selected, level, choice_count)
        self._sessions[session.session_id] = session
        return self._prepare_trial(session)

    def _prepare_trial(self, session: RotationSession) -> dict[str, Any]:
        shape_key = session.shape_order[session.trial_index]
        set_keys = SHAPE_SETS[session.stimulus_set]
        distractor_keys = self._random.sample([key for key in set_keys if key != shape_key], session.choice_count - 1)
        correct_rotation = self._random.choice((90, 180, 270))
        correct_choice_id = uuid.uuid4().hex
        choices = [
            {
                "id": correct_choice_id,
                **shape_payload(shape_key),
                "rotation": correct_rotation,
            },
        ]
        choices.extend({"id": uuid.uuid4().hex, **shape_payload(key), "rotation": self._random.choice((90, 180, 270))} for key in distractor_keys)
        self._random.shuffle(choices)
        session.correct_choice_id = correct_choice_id
        session.current_trial = {
            "trial": session.trial_index + 1,
            "sample_shape": shape_key,
            "sample": shape_payload(shape_key),
            "choices": choices,
            "correct_rotation": correct_rotation,
        }
        session.shown_at_ms = time.time() * 1000
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "stimulus_set": session.stimulus_set,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": {"choices": session.choice_count},
            "trial": session.trial_index + 1,
            "trial_count": TRIAL_COUNT,
            "sample": {**shape_payload(shape_key), "rotation": 0},
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
