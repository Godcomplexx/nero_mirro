from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm09_object_tracking.stimuli import MOVEMENT_MS, OBJECT_COUNT, PREVIEW_MS, ROUNDS, STIMULUS_SHAPES, TARGET_COUNT
from neuro_mirror.screening.gm09_scoring import score_gm09


@dataclass(slots=True)
class TrackingSession:
    session_id: str
    rounds: list[dict[str, Any]]
    round_index: int = 0
    shown_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm09ObjectTrackingPlugin(BrowserGamePlugin):
    plugin_name = "gm09_object_tracking"
    game_code = "GM-09"
    start_handler = "_start"
    answer_handler = "_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, TrackingSession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        rounds = [self._make_round(index) for index in range(ROUNDS)]
        session = TrackingSession(uuid.uuid4().hex, rounds)
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _make_round(self, index: int) -> dict[str, Any]:
        starts = self._positions(OBJECT_COUNT)
        ends = self._positions(OBJECT_COUNT)
        objects = [
            {"id": f"object-{number}", "start": starts[number], "end": ends[number]}
            for number in range(OBJECT_COUNT)
        ]
        targets = self._random.sample([item["id"] for item in objects], TARGET_COUNT)
        return {"objects": objects, "targets": targets, "shape": STIMULUS_SHAPES[index % len(STIMULUS_SHAPES)]}

    def _positions(self, count: int) -> list[list[float]]:
        cells = self._random.sample(range(24), count)
        return [[8 + (cell % 6) * 16.5, 12 + (cell // 6) * 24] for cell in cells]

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        selected_raw = payload.get("selected")
        if not isinstance(selected_raw, list):
            return {"ok": False, "message": "Выберите объекты."}
        current = session.rounds[session.round_index]
        valid_ids = {item["id"] for item in current["objects"]}
        selected = list(dict.fromkeys(str(item) for item in selected_raw if str(item) in valid_ids))
        targets = current["targets"]
        event = {
            "round": session.round_index + 1, "shape": current["shape"],
            "targets": targets, "selected": selected,
            "correct": set(selected) == set(targets),
            "reaction_ms": max(0.0, time.time() * 1000 - session.shown_ms),
        }
        session.round_events.append(event)
        session.round_index += 1
        session.shown_ms = time.time() * 1000
        if session.round_index >= len(session.rounds):
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {"ok": True, "finished": True, "correct": event["correct"], "events": events, "metrics": score_gm09(events)}
        result = self._payload(session)
        result["correct"] = event["correct"]
        return result

    def _payload(self, session: TrackingSession) -> dict[str, Any]:
        current = session.rounds[session.round_index]
        return {
            "ok": True, "finished": False, "session_id": session.session_id,
            "round": session.round_index + 1, "round_count": len(session.rounds),
            "objects": current["objects"], "targets": current["targets"],
            "target_count": TARGET_COUNT, "shape": current["shape"],
            "preview_ms": PREVIEW_MS, "movement_ms": MOVEMENT_MS,
        }
