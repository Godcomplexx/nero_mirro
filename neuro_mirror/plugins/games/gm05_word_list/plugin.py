from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm05_word_list.stimuli import STUDY_MS, WORD_SETS
from neuro_mirror.screening.gm05_scoring import score_gm05_rounds


@dataclass(slots=True)
class WordListSession:
    session_id: str
    sets: list[tuple[str, list[str]]]
    round_index: int = 0
    shown_at_ms: float = 0.0
    rounds: list[dict[str, Any]] = field(default_factory=list)


class Gm05WordListPlugin(BrowserGamePlugin):
    plugin_name = "gm05_word_list"
    game_code = "GM-05"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, WordListSession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        sets = []
        for category, source in WORD_SETS:
            words = list(source)
            self._random.shuffle(words)
            sets.append((category, words))
        session = WordListSession(uuid.uuid4().hex, sets)
        self._sessions[session.session_id] = session
        return self._round_payload(session)

    def _round_payload(self, session: WordListSession) -> dict[str, Any]:
        category, words = session.sets[session.round_index]
        targets, distractors = words[:5], words[5:]
        choices = targets + distractors
        self._random.shuffle(choices)
        session.shown_at_ms = time.time() * 1000
        return {"ok": True, "finished": False, "session_id": session.session_id,
                "round": session.round_index + 1, "round_count": len(session.sets),
                "category": category, "study_ms": STUDY_MS, "study_words": targets,
                "choices": choices}

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        selected = payload.get("selected")
        if not isinstance(selected, list):
            return {"ok": False, "message": "Некорректный ответ."}
        _, words = session.sets[session.round_index]
        targets, distractors = words[:5], words[5:]
        valid = set(words)
        clean = list(dict.fromkeys(str(word) for word in selected if str(word) in valid))
        session.rounds.append({"round": session.round_index + 1, "targets": targets,
                               "distractors": distractors, "selected": clean,
                               "duration_ms": max(0.0, time.time() * 1000 - session.shown_at_ms),
                               "client_timestamp_ms": payload.get("timestamp_ms")})
        session.round_index += 1
        if session.round_index == len(session.sets):
            self._sessions.pop(session.session_id, None)
            return {"ok": True, "finished": True, "metrics": score_gm05_rounds(session.rounds), "events": session.rounds}
        return self._round_payload(session)
