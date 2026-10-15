from __future__ import annotations

import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm24_category_naming.stimuli import CATEGORY_GROUPS
from neuro_mirror.screening.gm24_scoring import score_gm24


def response_matches(transcript: str, answers: tuple[str, ...]) -> bool:
    clean = " ".join(re.findall(r"[а-яё]+", transcript.lower()))
    return any(re.search(rf"(?:^|\s){re.escape(answer)}(?:$|\s)", clean) for answer in answers)


@dataclass(slots=True)
class CategoryNamingSession:
    session_id: str
    trials: list[dict[str, Any]]
    stimulus_set: str
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    recording_ms: int
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
        trial_count = int(parameters["trials"])
        category_count = int(parameters["category_count"])
        switch_every = int(parameters["switch_every"])
        recording_ms = int(parameters["recording_ms"])

        groups_by_name = {item["category"].casefold(): item for item in CATEGORY_GROUPS}
        available = tuple(name for name in self.definition.stimulus_sets if name.casefold() in groups_by_name)
        requested = next((name for name in available if name.casefold() == stimulus_set.casefold()), None)
        selected = requested or rng.choice(available)
        first_category = groups_by_name[selected.casefold()]["category"]
        other_categories = [item["category"] for item in CATEGORY_GROUPS if item["category"] != first_category]
        categories = [first_category, *rng.sample(other_categories, category_count - 1)]
        word_groups: dict[str, list[tuple[str, ...]]] = {}
        for category in categories:
            source = groups_by_name[category.casefold()]
            category_words = tuple(word for group in source["groups"] for word in group)
            variants = list(combinations(category_words, 3))
            rng.shuffle(variants)
            word_groups[category] = variants
        used_by_category = {category: 0 for category in categories}
        trials: list[dict[str, Any]] = []
        for trial_index in range(trial_count):
            block_index = trial_index // switch_every
            category = categories[block_index % len(categories)]
            selected_group = groups_by_name[category.casefold()]
            variant_index = used_by_category[category]
            used_by_category[category] += 1
            trials.append({
                "category": selected_group["category"],
                "answers": selected_group["answers"],
                "words": word_groups[category][variant_index],
            })
        session = CategoryNamingSession(uuid.uuid4().hex, trials, selected, level, parameters, recording_ms)
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
                "metrics": score_gm24(events, expected_trial_count=len(session.trials)),
            }
        session.shown_at_ms = time.time() * 1000
        result = self._payload(session)
        result["previous_correct"] = correct
        return result

    def _resume(self, session: CategoryNamingSession, paused_ms: float) -> dict[str, Any]:
        """Прерванная тройка слов предъявляется снова (4.5, п. 5)."""
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    def _trial_number(self, session: CategoryNamingSession) -> int:
        return session.trial_index + 1

    @staticmethod
    def _payload(session: CategoryNamingSession) -> dict[str, Any]:
        trial = session.trials[session.trial_index]
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "stimulus_set": session.stimulus_set,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": dict(session.difficulty_parameters),
            "trial_number": session.trial_index + 1,
            "trial_count": len(session.trials),
            "words": list(trial["words"]),
            "recording_ms": session.recording_ms,
        }
