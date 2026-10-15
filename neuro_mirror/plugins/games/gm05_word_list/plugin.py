from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm05_word_list.stimuli import WORD_SETS
from neuro_mirror.screening.gm05_scoring import score_gm05_rounds


@dataclass(slots=True)
class WordListSession:
    session_id: str
    sets: list[tuple[str, list[str]]]
    stimulus_set: str
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    round_index: int = 0
    shown_at_ms: float = 0.0
    rounds: list[dict[str, Any]] = field(default_factory=list)
    rng: Any = None


class Gm05WordListPlugin(BrowserGamePlugin):
    plugin_name = "gm05_word_list"
    game_code = "GM-05"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, WordListSession] = {}
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
        sets_by_name = {category.casefold(): (category, source) for category, source in WORD_SETS}
        available_sets = tuple(
            set_name
            for set_name in self.definition.stimulus_sets
            if set_name.casefold() in sets_by_name
        ) or tuple(sets_by_name)
        requested_set = stimulus_set.casefold()
        selected_set = next(
            (set_name for set_name in available_sets if set_name.casefold() == requested_set),
            available_sets[0],
        )
        category, source = sets_by_name[selected_set.casefold()]
        words = rng.sample(list(source), int(parameters["choice_words"]))
        session = WordListSession(
            uuid.uuid4().hex,
            [(category, words)],
            selected_set,
            level,
            parameters,
            rng=rng,
        )
        self._sessions[session.session_id] = session
        return self._round_payload(session)

    def _round_payload(self, session: WordListSession) -> dict[str, Any]:
        category, words = session.sets[session.round_index]
        target_count = int(session.difficulty_parameters["target_words"])
        targets, distractors = words[:target_count], words[target_count:]
        choices = targets + distractors
        session.rng.shuffle(choices)
        session.shown_at_ms = time.time() * 1000
        return {"ok": True, "finished": False, "session_id": session.session_id,
                "round": session.round_index + 1, "round_count": len(session.sets),
                "stimulus_set": session.stimulus_set,
                "difficulty_level": session.difficulty_level,
                "difficulty_parameters": dict(session.difficulty_parameters),
                "category": category, "study_ms": int(session.difficulty_parameters["study_ms"]), "study_words": targets,
                "choices": choices}

    def _resume(self, session: WordListSession, paused_ms: float) -> dict[str, Any]:
        """Слова показываются для запоминания заново (4.5, п. 5)."""
        return self._round_payload(session)

    def _trial_number(self, session: WordListSession) -> int:
        return session.round_index + 1

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        selected = payload.get("selected")
        if not isinstance(selected, list):
            return {"ok": False, "message": "Некорректный ответ."}
        _, words = session.sets[session.round_index]
        target_count = int(session.difficulty_parameters["target_words"])
        targets, distractors = words[:target_count], words[target_count:]
        valid = set(words)
        clean = list(dict.fromkeys(str(word) for word in selected if str(word) in valid))
        session.rounds.append({"round": session.round_index + 1, "targets": targets,
                               "distractors": distractors, "selected": clean,
                               "duration_ms": max(0.0, time.time() * 1000 - session.shown_at_ms),
                               "client_timestamp_ms": payload.get("timestamp_ms")})
        session.round_index += 1
        if session.round_index == len(session.sets):
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "metrics": score_gm05_rounds(
                    session.rounds,
                    expected_rounds=len(session.sets),
                ),
                "events": session.rounds,
            }
        return self._round_payload(session)
