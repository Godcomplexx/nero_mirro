from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm14_word_builder.stimuli import WORDS
from neuro_mirror.screening.gm14_scoring import score_gm14_words


@dataclass(slots=True)
class WordBuilderSession:
    session_id: str
    words: list[str]
    word_index: int = 0
    shown_at_ms: float = 0.0
    current_attempts: list[dict[str, Any]] = field(default_factory=list)
    completed_words: list[dict[str, Any]] = field(default_factory=list)


class Gm14WordBuilderPlugin(BrowserGamePlugin):
    plugin_name = "gm14_word_builder"
    game_code = "GM-14"
    start_handler = "_start_session"
    answer_handler = "_check_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, WordBuilderSession] = {}
        self._random = secrets.SystemRandom()

    def _start_session(self) -> dict[str, Any]:
        words = list(WORDS)
        self._random.shuffle(words)
        session = WordBuilderSession(uuid.uuid4().hex, words)
        self._sessions[session.session_id] = session
        return self._word_payload(session)

    def _word_payload(self, session: WordBuilderSession) -> dict[str, Any]:
        target = session.words[session.word_index]
        letters = list(target)
        for _ in range(8):
            self._random.shuffle(letters)
            if "".join(letters) != target:
                break
        if len(letters) > 1 and "".join(letters) == target:
            letters = letters[1:] + letters[:1]
        session.shown_at_ms = time.time() * 1000
        return {
            "ok": True,
            "finished": False,
            "correct": None,
            "session_id": session.session_id,
            "word_number": session.word_index + 1,
            "word_count": len(session.words),
            "letters": [
                {"id": f"letter-{index}", "letter": letter}
                for index, letter in enumerate(letters)
            ],
        }

    def _check_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "")
        session = self._sessions.get(session_id)
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}

        assembled = str(payload.get("assembled") or "").strip().lower()
        target = session.words[session.word_index]
        placements = payload.get("placements")
        if not isinstance(placements, list):
            placements = []
        attempt = {
            "assembled": assembled,
            "correct": assembled == target,
            "placements": placements,
            "submitted_at_ms": payload.get("timestamp_ms"),
        }
        session.current_attempts.append(attempt)
        if assembled != target:
            return {
                "ok": True,
                "finished": False,
                "correct": False,
                "attempt_count": len(session.current_attempts),
            }

        first = str(session.current_attempts[0]["assembled"])
        first_positions = sum(
            1 for index, letter in enumerate(target)
            if index < len(first) and first[index] == letter
        )
        session.completed_words.append(
            {
                "word_number": session.word_index + 1,
                "target": target,
                "attempt_count": len(session.current_attempts),
                "first_attempt_correct_positions": first_positions,
                "duration_ms": max(0.0, time.time() * 1000 - session.shown_at_ms),
                "attempts": session.current_attempts,
            }
        )
        session.word_index += 1
        session.current_attempts = []
        if session.word_index >= len(session.words):
            self._sessions.pop(session_id, None)
            return {
                "ok": True,
                "finished": True,
                "correct": True,
                "metrics": score_gm14_words(session.completed_words),
                "events": session.completed_words,
            }
        payload = self._word_payload(session)
        payload["correct"] = True
        return payload
