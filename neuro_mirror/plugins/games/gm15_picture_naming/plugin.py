from __future__ import annotations

import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm15_picture_naming.stimuli import (
    PICTURE_SETS,
    RECORDING_MS,
)
from neuro_mirror.screening.gm15_scoring import score_gm15


@dataclass(slots=True)
class NamingSession:
    session_id: str
    items: list[dict[str, Any]]
    stimulus_set: str
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    item_index: int = 0
    shown_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm15PictureNamingPlugin(BrowserGamePlugin):
    plugin_name = "gm15_picture_naming"
    game_code = "GM-15"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, NamingSession] = {}
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
        sets_by_name = {category.casefold(): (category, source) for category, source in PICTURE_SETS}
        available = tuple(name for name in self.definition.stimulus_sets if name.casefold() in sets_by_name) or tuple(sets_by_name)
        selected_set = next((name for name in available if name.casefold() == stimulus_set.casefold()), available[0])
        remaining_sets = [name for name in available if name != selected_set]
        rng.shuffle(remaining_sets)
        active_sets = [selected_set, *remaining_sets][:int(parameters["category_count"])]
        queues = {}
        for set_name in active_sets:
            category, source = sets_by_name[set_name.casefold()]
            queues[set_name] = [dict(item, category=category) for item in source]
            rng.shuffle(queues[set_name])
        item_count = int(parameters["items"])
        switch_every = int(parameters["switch_every"])
        if switch_every <= 0:
            set_order = [active_sets[0]] * item_count
        else:
            set_order = [
                active_sets[(index // switch_every) % len(active_sets)]
                for index in range(item_count)
            ]
        items = [queues[set_name].pop() for set_name in set_order]
        session = NamingSession(
            uuid.uuid4().hex,
            items,
            selected_set,
            level,
            parameters,
        )
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        item = session.items[session.item_index]
        transcript = str(payload.get("transcript") or "").strip()
        words = set(re.findall(r"[а-яё-]+", transcript.lower()))
        correct = any(answer in words for answer in item["answers"])
        session.round_events.append(
            {
                "category": item["category"],
                "image": item["file"],
                "expected": item["name"],
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
        session.item_index += 1
        if session.item_index >= len(session.items):
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "events": events,
                "metrics": score_gm15(events, expected_items=len(session.items)),
            }
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    def _resume(self, session: NamingSession, paused_ms: float) -> dict[str, Any]:
        """Прерванное изображение показывается снова (4.5, п. 5)."""
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    def _trial_number(self, session: NamingSession) -> int:
        return session.item_index + 1

    @staticmethod
    def _payload(session: NamingSession) -> dict[str, Any]:
        item = session.items[session.item_index]
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "stimulus_set": session.stimulus_set,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": dict(session.difficulty_parameters),
            "item_number": session.item_index + 1,
            "item_count": len(session.items),
            "category": item["category"],
            "image": item["file"],
            "recording_ms": RECORDING_MS,
        }
