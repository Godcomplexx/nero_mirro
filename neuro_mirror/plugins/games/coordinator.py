"""Persistence coordinator shared by all browser games."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from neuro_mirror.core.session_store import SessionStore
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.catalog import get_game_definition
from neuro_mirror.plugins.games.history import GameHistoryStore
from neuro_mirror.version import session_version_manifest


class GameSessionCoordinator(ProcessorPlugin):
    """Bind an internal game session to a user and persistent session record."""

    plugin_name = "game_session_coordinator"

    def __init__(
        self,
        bus,
        *,
        session_store: SessionStore,
        history_store: GameHistoryStore,
    ) -> None:
        super().__init__(bus)
        self.session_store = session_store
        self.history_store = history_store
        self._session_ids: dict[str, str] = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            Topics.GAME_SESSION_STARTED,
            Topics.GAME_SESSION_CHECKPOINT,
            Topics.GAME_SESSION_COMPLETED,
        )

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.GAME_SESSION_STARTED:
            self._start_session(event.payload)
            return
        if event.topic == Topics.GAME_SESSION_CHECKPOINT:
            self._save_checkpoint(event.payload)
            return
        await self._complete_session(event.payload)

    def _start_session(self, payload: dict[str, Any]) -> None:
        game_session_id = str(payload.get("game_session_id") or "")
        game_code = str(payload.get("game_code") or "")
        user_id = str(payload.get("user_id") or "")
        if not game_session_id or not game_code or not user_id:
            return
        if game_session_id in self._session_ids:
            return

        record = self.session_store.start(
            user_id=user_id,
            scenario="training_game",
            versions=session_version_manifest("training_game"),
            technical_params={
                "game_code": game_code,
                "game_session_id": game_session_id,
                "stimulus_set": str(payload.get("stimulus_set") or ""),
                "difficulty_level": payload.get("difficulty_level"),
            },
        )
        persistent_session_id = str(record["session_id"])
        self._session_ids[game_session_id] = persistent_session_id
        difficulty_level = payload.get("difficulty_level")
        self.history_store.record(
            user_id=user_id,
            session_id=persistent_session_id,
            game_code=game_code,
            stimulus_set=str(payload.get("stimulus_set") or ""),
            difficulty_level=(
                difficulty_level if isinstance(difficulty_level, int) else None
            ),
        )

    def _save_checkpoint(self, payload: dict[str, Any]) -> None:
        game_session_id = str(payload.get("session_id") or "")
        persistent_session_id = self._session_ids.get(game_session_id)
        if persistent_session_id:
            self.session_store.checkpoint(persistent_session_id, deepcopy(payload))

    async def _complete_session(self, payload: dict[str, Any]) -> None:
        game_session_id = str(payload.get("session_id") or "")
        persistent_session_id = self._session_ids.pop(game_session_id, "")
        if not persistent_session_id:
            return
        session = self.session_store.get(persistent_session_id) or {}
        game_code = str(payload.get("game_code") or "")
        definition = get_game_definition(game_code)
        result = {
            **deepcopy(payload),
            "report_type": "training_game",
            "type": "training_game",
            "game_code": definition.code,
            "game_title": definition.title,
            "primary_domain": definition.primary_domain.value,
            "game_session_id": game_session_id,
            "session_id": persistent_session_id,
            "user_id": str(session.get("user_id") or ""),
            "session_started_at": session.get("started_at"),
            "versions": deepcopy(session.get("versions") or {}),
        }
        completed = self.session_store.complete(persistent_session_id, result) or {}
        result["session_status"] = completed.get("status", "completed")
        result["session_finished_at"] = completed.get("finished_at")
        await self.bus.publish(
            Event(topic=Topics.STORAGE_WRITE, source=self.name, payload=result)
        )
