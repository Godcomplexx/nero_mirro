from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm07_target_search.stimuli import OBJECT_COUNT, TARGETS, TRIAL_COUNT
from neuro_mirror.screening.gm07_scoring import score_gm07_trials


@dataclass(slots=True)
class TargetSearchSession:
    session_id: str
    target_schedule: list[bool]
    stimulus_set: str
    target: dict[str, Any]
    difficulty_level: int
    grid_size: int
    trial_index: int = 0
    current_stimuli: list[dict[str, Any]] = field(default_factory=list)
    shown_at_ms: float = 0.0
    trials: list[dict[str, Any]] = field(default_factory=list)


class Gm07TargetSearchPlugin(BrowserGamePlugin):
    plugin_name = "gm07_target_search"
    game_code = "GM-07"
    start_handler = "_start_session"
    answer_handler = "_check_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, TargetSearchSession] = {}
        self._random = secrets.SystemRandom()

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._start_session(stimulus_set=str(payload.get("stimulus_set") or ""), difficulty_level=payload.get("difficulty_level"))

    def _start_session(self, *, stimulus_set: str = "", difficulty_level: object = None) -> dict[str, Any]:
        try: level = min(3, max(1, int(difficulty_level or 1)))
        except (TypeError, ValueError): level = 1
        grid_size, target_limits = ((4, (3, 5)), (8, (4, 7)), (10, (6, 10)))[level - 1]
        available_sets = tuple(
            set_name for set_name in self.definition.stimulus_sets if set_name in TARGETS
        ) or tuple(TARGETS)
        selected_set = stimulus_set if stimulus_set in available_sets else available_sets[0]
        present_count = self._random.randint(*target_limits)
        schedule = [True] * present_count + [False] * (TRIAL_COUNT - present_count)
        self._random.shuffle(schedule)
        session = TargetSearchSession(
            uuid.uuid4().hex,
            schedule,
            selected_set,
            dict(TARGETS[selected_set]),
            level,
            grid_size,
        )
        self._sessions[session.session_id] = session
        return self._prepare_trial(session)

    def _prepare_trial(self, session: TargetSearchSession) -> dict[str, Any]:
        target_present = session.target_schedule[session.trial_index]
        object_count = session.grid_size ** 2
        stimuli = [self._make_distractor(session, index) for index in range(object_count)]
        if target_present:
            target_position = self._random.randrange(object_count)
            stimuli[target_position] = {
                "id": f"s{target_position}",
                **session.target,
            }
        self._random.shuffle(stimuli)
        session.current_stimuli = stimuli
        session.shown_at_ms = time.time() * 1000
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "trial": session.trial_index + 1,
            "trial_count": TRIAL_COUNT,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": {"grid_size": session.grid_size, "target_present_trials": sum(session.target_schedule)},
            "grid_size": session.grid_size,
            "object_count": object_count,
            "stimulus_set": session.stimulus_set,
            "target": session.target,
            "stimuli": stimuli,
        }

    def _make_distractor(self, session: TargetSearchSession, index: int) -> dict[str, Any]:
        color = self._random.choice(("red", "black"))
        rotation = self._random.choice((0, 90, 180, 270))
        if color == session.target["color"] and rotation == session.target["rotation"]:
            rotation = self._random.choice((90, 180, 270))
        return {
            "id": f"s{index}",
            "symbol": session.target["symbol"],
            "color": color,
            "rotation": rotation,
        }

    def _check_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "")
        session = self._sessions.get(session_id)
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}

        selected_id = payload.get("selected_id")
        if selected_id is not None:
            selected_id = str(selected_id)
        target_present = session.target_schedule[session.trial_index]
        target_item = next(
            (
                item for item in session.current_stimuli
                if item["color"] == session.target["color"]
                and item["rotation"] == session.target["rotation"]
                and item["symbol"] == session.target["symbol"]
            ),
            None,
        )
        correct = (
            selected_id == target_item["id"] if target_present and target_item
            else selected_id is None
        )
        now_ms = time.time() * 1000
        session.trials.append(
            {
                "trial": session.trial_index + 1,
                "target_present": target_present,
                "stimuli": session.current_stimuli,
                "selected_id": selected_id,
                "response_kind": "none" if selected_id is None else "stimulus",
                "correct": correct,
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
                "metrics": score_gm07_trials(session.trials),
                "events": session.trials,
            }
        return self._prepare_trial(session)
