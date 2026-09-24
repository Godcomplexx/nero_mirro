from __future__ import annotations

import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm15_picture_naming.stimuli import (
    ITEMS_PER_CATEGORY,
    PICTURE_SETS,
    RECORDING_MS,
)
from neuro_mirror.screening.gm15_scoring import score_gm15


@dataclass(slots=True)
class NamingSession:
    session_id: str
    items: list[dict[str, Any]]
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

    def _start(self) -> dict[str, Any]:
        category_items: list[list[dict[str, Any]]] = []
        for category, source in PICTURE_SETS:
            selected = [dict(item, category=category) for item in source]
            self._random.shuffle(selected)
            category_items.append(selected[:ITEMS_PER_CATEGORY])
        items = [
            category_items[category_index][cycle]
            for cycle in range(ITEMS_PER_CATEGORY)
            for category_index in range(len(category_items))
        ]
        session = NamingSession(uuid.uuid4().hex, items)
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
                "metrics": score_gm15(events),
            }
        session.shown_at_ms = time.time() * 1000
        return self._payload(session)

    @staticmethod
    def _payload(session: NamingSession) -> dict[str, Any]:
        item = session.items[session.item_index]
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "item_number": session.item_index + 1,
            "item_count": len(session.items),
            "category": item["category"],
            "image": item["file"],
            "recording_ms": RECORDING_MS,
        }
