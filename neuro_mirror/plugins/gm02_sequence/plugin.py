from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.screening.gm02_scoring import score_gm02_attempt


GRID_SIZE = 3
MAX_ROUNDS = 10


@dataclass(slots=True)
class SequenceSession:
    session_id: str
    sequence: list[int]
    started_at_ms: float
    successful_rounds: int = 0
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm02SequencePlugin(Plugin):
    plugin_name = "gm02_sequence"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, SequenceSession] = {}
        self._random = secrets.SystemRandom()

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.REQ_GM02_START, Topics.REQ_GM02_ANSWER)

    async def handle_event(self, event: Event) -> None:
        request_id = str(event.payload.get("_request_id") or "")
        if event.topic == Topics.REQ_GM02_START:
            payload = self._start_session()
            topic = Topics.RESP_GM02_START
        else:
            payload = self._check_answer(event.payload)
            topic = Topics.RESP_GM02_ANSWER

        payload["_reply_to"] = request_id
        await self.bus.publish(Event(topic=topic, source=self.name, payload=payload))

    def _new_cell(self) -> int:
        return self._random.randrange(GRID_SIZE * GRID_SIZE)

    def _start_session(self) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        session = SequenceSession(
            session_id=session_id,
            sequence=[self._new_cell()],
            started_at_ms=time.time() * 1000,
        )
        self._sessions[session_id] = session
        return self._round_payload(session)

    def _check_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = str(payload.get("session_id") or "")
        session = self._sessions.get(session_id)
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}

        clicks = payload.get("clicks")
        if not isinstance(clicks, list):
            return {"ok": False, "message": "Некорректный список действий."}

        clean_clicks: list[dict[str, Any]] = []
        for click in clicks:
            if not isinstance(click, dict):
                continue
            try:
                cell = int(click.get("cell"))
                timestamp_ms = float(click.get("timestamp_ms"))
            except (TypeError, ValueError):
                continue
            if 0 <= cell < GRID_SIZE * GRID_SIZE:
                clean_clicks.append({"cell": cell, "timestamp_ms": timestamp_ms})

        finished_at_ms = time.time() * 1000
        metrics = score_gm02_attempt(
            session.sequence,
            clean_clicks,
            successful_rounds=session.successful_rounds,
            started_at_ms=session.started_at_ms,
            finished_at_ms=finished_at_ms,
        )
        correct = metrics["m08_series_accuracy"] == 1.0
        session.round_events.append(
            {
                "round": session.successful_rounds + 1,
                "expected": list(session.sequence),
                "clicks": clean_clicks,
                "correct": correct,
            }
        )

        if not correct:
            self._sessions.pop(session_id, None)
            return {
                "ok": True,
                "finished": True,
                "reason": "error",
                "metrics": metrics,
                "events": session.round_events,
            }

        session.successful_rounds += 1
        if session.successful_rounds >= MAX_ROUNDS:
            metrics["m01_max_sequence_length"] = session.successful_rounds
            self._sessions.pop(session_id, None)
            return {
                "ok": True,
                "finished": True,
                "reason": "level_complete",
                "metrics": metrics,
                "events": session.round_events,
            }

        session.sequence.append(self._new_cell())
        return self._round_payload(session)

    @staticmethod
    def _round_payload(session: SequenceSession) -> dict[str, Any]:
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "grid_size": GRID_SIZE,
            "round": session.successful_rounds + 1,
            "max_rounds": MAX_ROUNDS,
            "sequence": list(session.sequence),
        }
