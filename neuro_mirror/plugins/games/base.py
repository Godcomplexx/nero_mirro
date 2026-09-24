"""Base request/reply protocol for newly implemented browser games."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.catalog import get_game_definition


class BrowserGamePlugin(Plugin):
    """Standard transport shell; a game implements only start and answer logic."""

    game_code = ""
    game_definition = None
    start_handler = "_start"
    answer_handler = "_answer"
    _event_list_attributes = ("round_events", "rounds", "trials", "completed_words", "results")

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self.definition = self.game_definition or get_game_definition(self.game_code)

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            self.definition.start_request_topic,
            self.definition.answer_request_topic,
        )

    async def handle_event(self, event: Event) -> None:
        request_id = str(event.payload.get("_request_id") or "")
        is_start = event.topic == self.definition.start_request_topic
        result = self.start_game(event.payload) if is_start else self.answer_game(event.payload)
        checkpoint = result.get("checkpoint")
        if isinstance(checkpoint, dict):
            await self.bus.publish(
                Event(topic=Topics.GAME_SESSION_CHECKPOINT, source=self.name, payload=checkpoint)
            )
        if is_start and result.get("ok") and result.get("session_id"):
            await self.bus.publish(
                Event(
                    topic=Topics.GAME_SESSION_STARTED,
                    source=self.name,
                    payload={
                        "game_session_id": str(result["session_id"]),
                        "game_code": self.definition.code,
                        "user_id": str(event.payload.get("user_id") or ""),
                        "stimulus_set": str(
                            event.payload.get("stimulus_set")
                            or (
                                self.definition.stimulus_sets[0]
                                if self.definition.stimulus_sets
                                else ""
                            )
                        ),
                        "difficulty_level": event.payload.get("difficulty_level"),
                    },
                )
            )
        report = result.get("report")
        if isinstance(report, dict):
            await self.bus.publish(
                Event(
                    topic=Topics.GAME_SESSION_COMPLETED,
                    source=self.name,
                    payload=deepcopy(report),
                )
            )
        result["_reply_to"] = request_id
        result.setdefault("game_code", self.definition.code)
        await self.bus.publish(
            Event(
                topic=(
                    self.definition.start_response_topic
                    if is_start
                    else self.definition.answer_response_topic
                ),
                source=self.name,
                payload=result,
            )
        )

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return getattr(self, self.start_handler)()

    def answer_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = getattr(self, self.answer_handler)(payload)
        if not result.get("ok"):
            return result
        session_id = str(payload.get("session_id") or result.get("session_id") or "")
        events = result.get("events")
        if not isinstance(events, list):
            session = getattr(self, "_sessions", {}).get(session_id)
            events = self._session_events(session)
        journal = [self._normalise_event(index, item) for index, item in enumerate(events or (), start=1)]
        result["checkpoint"] = {
            "source": self.definition.topic_prefix,
            "session_id": session_id,
            "next_index": len(journal),
            "trials": deepcopy(journal),
        }
        if result.get("finished"):
            metrics = result.get("metrics") or {}
            complete = metrics.get("u06_complete")
            technically_valid = metrics.get("u06_technically_valid")
            result["report"] = {
                "type": "training_game",
                "game_code": self.definition.code,
                "session_id": session_id,
                "completion_status": (
                    "completed" if complete is True
                    else "incomplete" if complete is False
                    else "unknown"
                ),
                "technical_validity": (
                    "valid" if technically_valid is True
                    else "invalid" if technically_valid is False
                    else "unknown"
                ),
                "metrics": deepcopy(result.get("metrics") or {}),
                "trials": deepcopy(journal),
            }
        return result

    def _session_events(self, session: object | None) -> list[dict[str, Any]]:
        if session is None:
            return []
        for attribute in self._event_list_attributes:
            value = getattr(session, attribute, None)
            if isinstance(value, list):
                return value
        return []

    @staticmethod
    def _normalise_event(index: int, raw_event: object) -> dict[str, Any]:
        raw = deepcopy(raw_event) if isinstance(raw_event, dict) else {"value": raw_event}
        answer_keys = {
            key for key in raw
            if key.startswith("selected")
            or key in {
                "answer",
                "assembled",
                "boundary_errors",
                "clicks",
                "invalid_words",
                "path",
                "placements",
                "recognized",
                "repetitions",
                "responded",
                "tokens",
                "transcript",
                "valid_words",
            }
        }
        time_keys = {
            key for key in raw
            if key.endswith("_ms") or key in {"reaction_time", "duration"}
        }
        stimulus = {key: value for key, value in raw.items() if key not in answer_keys | time_keys | {"correct", "valid"}}
        answer = {key: raw[key] for key in answer_keys}
        elapsed = next((raw[key] for key in time_keys if isinstance(raw.get(key), (int, float))), 0.0)
        return {
            "index": index,
            "stimulus": stimulus,
            "answer": answer,
            "elapsed_ms": max(0.0, float(elapsed)),
            "valid": raw.get("valid"),
            "correct": raw.get("correct"),
            "raw": raw,
        }
