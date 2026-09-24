from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm21_odd_one_out.stimuli import (
    CATEGORIES,
    MINIMUM_SESSION_MS,
    REQUIRED_TRIALS,
)
from neuro_mirror.screening.gm21_scoring import score_gm21


@dataclass(slots=True)
class OddOneSession:
    session_id: str
    started_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    shown_at_ms: float = 0.0
    trial_index: int = 0
    current_trial: dict[str, Any] = field(default_factory=dict)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm21OddOneOutPlugin(BrowserGamePlugin):
    plugin_name = "gm21_odd_one_out"
    game_code = "GM-21"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, OddOneSession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        session = OddOneSession(uuid.uuid4().hex)
        self._sessions[session.session_id] = session
        return self._prepare_trial(session)

    def _prepare_trial(self, session: OddOneSession) -> dict[str, Any]:
        category_names = list(CATEGORIES)
        main_category = category_names[session.trial_index % len(category_names)]
        odd_category = self._random.choice([name for name in category_names if name != main_category])
        main_items = self._random.sample(list(CATEGORIES[main_category]), 3)
        odd_item = self._random.choice(CATEGORIES[odd_category])
        choices = [
            {"id": uuid.uuid4().hex, "name": name, "image": image, "category": main_category}
            for name, image in main_items
        ]
        odd_choice = {
            "id": uuid.uuid4().hex,
            "name": odd_item[0],
            "image": odd_item[1],
            "category": odd_category,
        }
        choices.append(odd_choice)
        self._random.shuffle(choices)
        session.current_trial = {
            "main_category": main_category,
            "odd_category": odd_category,
            "odd_id": odd_choice["id"],
            "choices": choices,
        }
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        selected_id = str(payload.get("selected_id") or "")
        choices = session.current_trial["choices"]
        selected = next((choice for choice in choices if choice["id"] == selected_id), None)
        if selected is None:
            return {"ok": False, "message": "Некорректный вариант ответа."}
        correct = selected_id == session.current_trial["odd_id"]
        now_ms = time.time() * 1000
        session.round_events.append(
            {
                "main_category": session.current_trial["main_category"],
                "odd_category": session.current_trial["odd_category"],
                "choices": [choice["name"] for choice in choices],
                "selected_id": selected_id,
                "selected_name": selected["name"],
                "correct": correct,
                "reaction_ms": max(0.0, now_ms - session.shown_at_ms),
            }
        )
        session.trial_index += 1
        elapsed_ms = now_ms - session.started_at_ms
        if session.trial_index >= REQUIRED_TRIALS and elapsed_ms >= MINIMUM_SESSION_MS:
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "correct": correct,
                "events": events,
                "metrics": score_gm21(events, elapsed_ms),
            }
        result = self._prepare_trial(session)
        result["previous_correct"] = correct
        return result

    @staticmethod
    def _payload(session: OddOneSession) -> dict[str, Any]:
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "trial_number": session.trial_index + 1,
            "required_trials": REQUIRED_TRIALS,
            "bonus": session.trial_index >= REQUIRED_TRIALS,
            "choices": [
                {"id": choice["id"], "image": choice["image"]}
                for choice in session.current_trial["choices"]
            ],
        }
