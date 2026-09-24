from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm03_changed_object.stimuli import ROOMS
from neuro_mirror.screening.gm03_scoring import score_gm03


@dataclass(slots=True)
class LocationSession:
    session_id: str
    rooms: list[dict[str, Any]]
    room_index: int = 0
    object_index: int = 0
    phase: str = "study"
    shown_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm03ChangedObjectPlugin(BrowserGamePlugin):
    plugin_name = "gm03_changed_object"
    game_code = "GM-03"
    start_handler = "_start"
    answer_handler = "_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, LocationSession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        rooms = []
        for source in ROOMS:
            cells = self._random.sample(range(16), 5)
            rooms.append({"name": source["name"], "objects": [
                {"name": name, "symbol": symbol, "cell": cell}
                for (name, symbol), cell in zip(source["objects"], cells)
            ]})
        session = LocationSession(uuid.uuid4().hex, rooms)
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        action = str(payload.get("action") or "select")
        if session.phase == "study":
            if action != "begin_recall":
                return {"ok": False, "message": "Сначала запомните расположение."}
            session.phase = "recall"
            session.shown_ms = time.time() * 1000
            return self._payload(session)

        room = session.rooms[session.room_index]
        target = room["objects"][session.object_index]
        selected_cell = int(payload.get("selected_cell", -1))
        if selected_cell < 0 or selected_cell >= 16:
            return {"ok": False, "message": "Недопустимая позиция."}
        expected_cell = int(target["cell"])
        event = {
            "room": room["name"], "object": target["name"],
            "expected": [expected_cell % 4, expected_cell // 4],
            "selected": [selected_cell % 4, selected_cell // 4],
            "correct": selected_cell == expected_cell,
            "reaction_ms": max(0.0, time.time() * 1000 - session.shown_ms),
        }
        session.round_events.append(event)
        session.object_index += 1
        session.shown_ms = time.time() * 1000
        if session.object_index >= len(room["objects"]):
            session.room_index += 1
            session.object_index = 0
            session.phase = "study"
            if session.room_index >= len(session.rooms):
                events = list(session.round_events)
                self._sessions.pop(session.session_id, None)
                return {"ok": True, "finished": True, "correct": event["correct"], "events": events, "metrics": score_gm03(events)}
        result = self._payload(session)
        result["correct"] = event["correct"]
        return result

    def _payload(self, session: LocationSession) -> dict[str, Any]:
        room = session.rooms[session.room_index]
        payload = {
            "ok": True, "finished": False, "session_id": session.session_id,
            "phase": session.phase, "room": room["name"],
            "room_number": session.room_index + 1, "room_count": len(session.rooms),
        }
        if session.phase == "study":
            payload["objects"] = room["objects"]
            payload["study_seconds"] = 10
        else:
            target = room["objects"][session.object_index]
            payload["target"] = {"name": target["name"], "symbol": target["symbol"]}
            payload["object_number"] = session.object_index + 1
            payload["object_count"] = len(room["objects"])
        return payload
