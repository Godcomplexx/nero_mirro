from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm21_odd_one_out.stimuli import CATEGORIES
from neuro_mirror.screening.gm21_scoring import score_gm21


@dataclass(slots=True)
class OddOneSession:
    session_id: str
    main_category: str
    stimulus_set: str
    category_schedule: list[str]
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    required_trials: int
    switch_every: int
    started_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    shown_at_ms: float = 0.0
    trial_index: int = 0
    current_trial: dict[str, Any] = field(default_factory=dict)
    round_events: list[dict[str, Any]] = field(default_factory=list)
    rng: Any = None


class Gm21OddOneOutPlugin(BrowserGamePlugin):
    plugin_name = "gm21_odd_one_out"
    game_code = "GM-21"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, OddOneSession] = {}
        self._random = secrets.SystemRandom()

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._start(
            stimulus_set=str(payload.get("stimulus_set") or ""),
            difficulty_level=payload.get("difficulty_level"),
            rng=self._session_random(payload),
        )

    def _start(self, *, stimulus_set: str = "", difficulty_level: object = None, rng: Any = None) -> dict[str, Any]:
        rng = rng or self._random
        config = level_config(self.game_code)
        try:
            level = int(difficulty_level or config["default_level"])
        except (TypeError, ValueError):
            level = int(config["default_level"])
        available_levels = {int(item["level"]): item for item in config["levels"]}
        if level not in available_levels:
            level = int(config["default_level"])
        parameters = dict(available_levels[level]["parameters"])
        required_trials = int(parameters["trials"])
        category_count = int(parameters["category_count"])
        switch_every = int(parameters["switch_every"])

        categories_by_name = {name.casefold(): name for name in CATEGORIES}
        available = tuple(name for name in self.definition.stimulus_sets if name.casefold() in categories_by_name)
        requested = next((name for name in available if name.casefold() == stimulus_set.casefold()), None)
        selected = requested or rng.choice(available)
        first_category = categories_by_name[selected.casefold()]
        other_categories = [name for name in CATEGORIES if name != first_category]
        selected_categories = [first_category]
        selected_categories.extend(rng.sample(other_categories, category_count - 1))
        session = OddOneSession(
            uuid.uuid4().hex,
            first_category,
            selected,
            selected_categories,
            level,
            parameters,
            required_trials,
            switch_every,
            rng=rng,
        )
        self._sessions[session.session_id] = session
        return self._prepare_trial(session)

    def _prepare_trial(self, session: OddOneSession) -> dict[str, Any]:
        category_names = list(CATEGORIES)
        if session.switch_every > 0:
            block_index = session.trial_index // session.switch_every
            session.main_category = session.category_schedule[block_index % len(session.category_schedule)]
        main_category = session.main_category
        odd_category = session.rng.choice([name for name in category_names if name != main_category])
        main_items = session.rng.sample(list(CATEGORIES[main_category]), 3)
        odd_item = session.rng.choice(CATEGORIES[odd_category])
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
        session.rng.shuffle(choices)
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
        if session.trial_index >= session.required_trials:
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "correct": correct,
                "events": events,
                "metrics": score_gm21(events, elapsed_ms, expected_trial_count=session.required_trials),
            }
        result = self._prepare_trial(session)
        result["previous_correct"] = correct
        return result

    def _resume(self, session: OddOneSession, paused_ms: float) -> dict[str, Any]:
        """Прерванный набор картинок показывается снова (4.5, п. 5)."""
        session.started_at_ms += paused_ms
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    def _trial_number(self, session: OddOneSession) -> int:
        return session.trial_index + 1

    @staticmethod
    def _payload(session: OddOneSession) -> dict[str, Any]:
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "stimulus_set": session.stimulus_set,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": dict(session.difficulty_parameters),
            "trial_number": session.trial_index + 1,
            "required_trials": session.required_trials,
            "bonus": False,
            "choices": [
                {"id": choice["id"], "image": choice["image"]}
                for choice in session.current_trial["choices"]
            ],
        }
