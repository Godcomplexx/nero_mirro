from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm13_categories.stimuli import BLOCK_DURATION_MS, CATEGORIES
from neuro_mirror.screening.gm13_scoring import analyse_category_response, score_gm13


@dataclass(slots=True)
class CategorySession:
    session_id: str
    categories: list[dict[str, Any]]
    stimulus_set: str
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    category_index: int = 0
    shown_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm13CategoriesPlugin(BrowserGamePlugin):
    plugin_name = "gm13_categories"
    game_code = "GM-13"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, CategorySession] = {}
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
        categories_by_name = {str(item["name"]).casefold(): item for item in CATEGORIES}
        available = tuple(name for name in self.definition.stimulus_sets if name.casefold() in categories_by_name) or tuple(categories_by_name)
        requested = next((name for name in available if name.casefold() == stimulus_set.casefold()), None)
        selected = requested or rng.choice(available)
        remaining_names = [name for name in available if name != selected]
        rng.shuffle(remaining_names)
        ordered_names = [selected] + remaining_names
        categories = [
            categories_by_name[name.casefold()]
            for name in ordered_names[:int(parameters["category_count"])]
        ]
        session = CategorySession(
            uuid.uuid4().hex,
            categories,
            selected,
            level,
            parameters,
        )
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}

        category = session.categories[session.category_index]
        transcript = str(payload.get("transcript") or "").strip()
        analysis = analyse_category_response(transcript, set(category["words"]))
        duration_ms = max(
            0.0,
            float(payload.get("duration_ms") or (time.time() * 1000 - session.shown_at_ms)),
        )
        session.round_events.append(
            {
                "category": category["name"],
                "prompt": category["prompt"],
                "transcript": transcript,
                "recognized": bool(payload.get("recognized", transcript)),
                "tokens": analysis["tokens"],
                "valid_words": analysis["valid_words"],
                "invalid_words": analysis["invalid_words"],
                "repetitions": analysis["repetitions"],
                "duration_ms": duration_ms,
                "valid": bool(transcript),
            }
        )
        session.category_index += 1
        if session.category_index >= len(session.categories):
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "events": events,
                "metrics": score_gm13(events, expected_categories=len(session.categories)),
            }
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    def _resume(self, session: CategorySession, paused_ms: float) -> dict[str, Any]:
        """Прерванный блок категории начинается заново (4.5, п. 5)."""
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    def _trial_number(self, session: CategorySession) -> int:
        return session.category_index + 1

    @staticmethod
    def _payload(session: CategorySession) -> dict[str, Any]:
        category = session.categories[session.category_index]
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "stimulus_set": session.stimulus_set,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": dict(session.difficulty_parameters),
            "category": category["name"],
            "prompt": category["prompt"],
            "block_number": session.category_index + 1,
            "block_count": len(session.categories),
            "duration_ms": int(session.difficulty_parameters.get("block_duration_ms", BLOCK_DURATION_MS)),
        }
