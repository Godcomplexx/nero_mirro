from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm20_rule_sorting.stimuli import (
    COLORS,
    REFERENCES,
    RULES,
    SHAPES,
    TRIAL_COUNT,
)
from neuro_mirror.screening.gm20_scoring import score_gm20_trials


@dataclass(slots=True)
class RuleSortingSession:
    session_id: str
    active_rule: str
    trial_index: int = 0
    consecutive_correct: int = 0
    previous_rule: str | None = None
    trials_since_switch: int = 1000
    current_stimulus: dict[str, Any] = field(default_factory=dict)
    current_matches: dict[str, str] = field(default_factory=dict)
    shown_at_ms: float = 0.0
    trials: list[dict[str, Any]] = field(default_factory=list)


class Gm20RuleSortingPlugin(BrowserGamePlugin):
    plugin_name = "gm20_rule_sorting"
    game_code = "GM-20"
    start_handler = "_start_session"
    answer_handler = "_check_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, RuleSortingSession] = {}
        self._random = secrets.SystemRandom()

    def _start_session(self) -> dict[str, Any]:
        session = RuleSortingSession(
            session_id=uuid.uuid4().hex,
            active_rule=self._random.choice(RULES),
        )
        self._sessions[session.session_id] = session
        return self._prepare_trial(session)

    def _prepare_trial(self, session: RuleSortingSession) -> dict[str, Any]:
        match_indexes = list(range(4))
        self._random.shuffle(match_indexes)
        color_index, shape_index, count_index = match_indexes[:3]
        stimulus = {
            "color": COLORS[color_index],
            "shape": SHAPES[shape_index],
            "count": count_index + 1,
        }
        matches = {
            "color": REFERENCES[color_index]["id"],
            "shape": REFERENCES[shape_index]["id"],
            "count": REFERENCES[count_index]["id"],
        }
        session.current_stimulus = stimulus
        session.current_matches = matches
        session.shown_at_ms = time.time() * 1000
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "trial": session.trial_index + 1,
            "trial_count": TRIAL_COUNT,
            "references": REFERENCES,
            "stimulus": stimulus,
        }

    def _check_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "")
        session = self._sessions.get(session_id)
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        selected_reference = str(payload.get("selected_reference") or "")
        valid_ids = {reference["id"] for reference in REFERENCES}
        if selected_reference not in valid_ids:
            return {"ok": False, "message": "Некорректный вариант ответа."}

        correct_reference = session.current_matches[session.active_rule]
        correct = selected_reference == correct_reference
        session.trials.append(
            {
                "trial": session.trial_index + 1,
                "stimulus": session.current_stimulus,
                "matches": dict(session.current_matches),
                "active_rule": session.active_rule,
                "previous_rule": session.previous_rule,
                "trials_since_switch": session.trials_since_switch,
                "selected_reference": selected_reference,
                "correct_reference": correct_reference,
                "correct": correct,
                "reaction_ms": max(0.0, time.time() * 1000 - session.shown_at_ms),
                "client_timestamp_ms": payload.get("timestamp_ms"),
            }
        )

        if correct:
            session.consecutive_correct += 1
        else:
            session.consecutive_correct = 0
        session.trial_index += 1
        session.trials_since_switch += 1

        if session.consecutive_correct >= 10 and session.trial_index < TRIAL_COUNT:
            old_rule = session.active_rule
            session.active_rule = self._random.choice([rule for rule in RULES if rule != old_rule])
            session.previous_rule = old_rule
            session.consecutive_correct = 0
            session.trials_since_switch = 1

        if session.trial_index >= TRIAL_COUNT:
            self._sessions.pop(session_id, None)
            return {
                "ok": True,
                "finished": True,
                "feedback": "correct" if correct else "incorrect",
                "metrics": score_gm20_trials(session.trials),
                "events": session.trials,
            }

        next_trial = self._prepare_trial(session)
        next_trial["feedback"] = "correct" if correct else "incorrect"
        return next_trial
