from __future__ import annotations

import asyncio

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.session_store import SessionStore
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.coordinator import GameSessionCoordinator
from neuro_mirror.plugins.games.history import GameHistoryStore


def test_game_attempts_are_bound_to_user_session(tmp_path) -> None:
    async def scenario() -> None:
        bus = EventBus()
        store = SessionStore(tmp_path / "sessions.json")
        history = GameHistoryStore(tmp_path / "game_history.json")
        coordinator = GameSessionCoordinator(
            bus,
            session_store=store,
            history_store=history,
        )
        stored_reports = bus.subscribe(Topics.STORAGE_WRITE)
        await coordinator.start()
        try:
            await bus.publish(
                Event(
                    topic=Topics.GAME_SESSION_STARTED,
                    source="test",
                    payload={
                        "game_session_id": "game-session-1",
                        "game_code": "GM-14",
                        "user_id": "user-1",
                        "stimulus_set": "слова-1",
                        "difficulty_level": 2,
                    },
                )
            )
            await bus.publish(
                Event(
                    topic=Topics.GAME_SESSION_CHECKPOINT,
                    source="test",
                    payload={
                        "session_id": "game-session-1",
                        "next_index": 1,
                        "trials": [{"index": 1, "correct": True}],
                    },
                )
            )
            await bus.publish(
                Event(
                    topic=Topics.GAME_SESSION_COMPLETED,
                    source="test",
                    payload={
                        "session_id": "game-session-1",
                        "game_code": "GM-14",
                        "completion_status": "completed",
                        "metrics": {"correct": 1},
                        "trials": [{"index": 1, "correct": True}],
                    },
                )
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)

            stored_event = await asyncio.wait_for(stored_reports.queue.get(), timeout=1)

            records = store.list_for_user("user-1")
            assert len(records) == 1
            assert records[0]["scenario"] == "training_game"
            assert records[0]["technical_params"]["game_code"] == "GM-14"
            assert records[0]["checkpoint"]["next_index"] == 1
            assert records[0]["checkpoint"]["trials"][0]["correct"] is True
            assert records[0]["status"] == "completed"
            assert records[0]["result"]["game_session_id"] == "game-session-1"
            assert records[0]["result"]["session_id"] == records[0]["session_id"]
            assert records[0]["result"]["metrics"]["correct"] == 1
            assert stored_event.payload["report_type"] == "training_game"
            assert stored_event.payload["user_id"] == "user-1"
            assert stored_event.payload["game_code"] == "GM-14"
            assert stored_event.payload["game_title"]
            assert stored_event.payload["primary_domain"] == "speech"
            presentations = history.for_user("user-1")
            assert len(presentations) == 1
            assert presentations[0].game_code == "GM-14"
            assert presentations[0].stimulus_set == "слова-1"
        finally:
            await coordinator.stop()
            stored_reports.close()

    asyncio.run(scenario())
