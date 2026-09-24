from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm13_categories.stimuli import BLOCK_DURATION_MS, CATEGORIES
from neuro_mirror.screening.gm13_scoring import analyse_category_response, score_gm13


@dataclass(slots=True)
class CategorySession:
    session_id: str
    category_index: int = 0
    shown_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm13CategoriesPlugin(BrowserGamePlugin):
    plugin_name = "gm13_categories"
    game_code = "GM-13"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, CategorySession] = {}

    def _start(self) -> dict[str, Any]:
        session = CategorySession(uuid.uuid4().hex)
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}

        category = CATEGORIES[session.category_index]
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
        if session.category_index >= len(CATEGORIES):
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "events": events,
                "metrics": score_gm13(events),
            }
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    @staticmethod
    def _payload(session: CategorySession) -> dict[str, Any]:
        category = CATEGORIES[session.category_index]
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "category": category["name"],
            "prompt": category["prompt"],
            "block_number": session.category_index + 1,
            "block_count": len(CATEGORIES),
            "duration_ms": BLOCK_DURATION_MS,
        }
