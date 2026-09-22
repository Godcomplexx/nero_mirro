from __future__ import annotations

import asyncio

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.gm02_sequence.plugin import Gm02SequencePlugin
from neuro_mirror.screening.gm02_scoring import score_gm02_attempt


def test_gm02_scoring_keeps_metrics_separate() -> None:
    result = score_gm02_attempt(
        [2, 5, 1],
        [
            {"cell": 2, "timestamp_ms": 100.0},
            {"cell": 4, "timestamp_ms": 250.0},
        ],
        successful_rounds=2,
        started_at_ms=50.0,
        finished_at_ms=300.0,
    )

    assert result["m08_series_accuracy"] == 0.0
    assert result["m01_max_sequence_length"] == 2
    assert result["m02_position_accuracy"] == 1 / 3
    assert result["m03_order_errors"] == 2
    assert result["u04_duration_ms"] == 250.0
    assert result["u06_technically_valid"] is True


def test_gm02_plugin_stops_on_first_incorrect_round() -> None:
    async def scenario() -> None:
        bus = EventBus()
        plugin = Gm02SequencePlugin(bus)
        generated = iter((3, 7, 1))
        plugin._new_cell = lambda: next(generated)  # type: ignore[method-assign]
        await plugin.start()
        try:
            started = await bus.request(
                Event(topic=Topics.REQ_GM02_START, source="test")
            )
            assert started["sequence"] == [3]
            assert started["round"] == 1

            second = await bus.request(
                Event(
                    topic=Topics.REQ_GM02_ANSWER,
                    source="test",
                    payload={
                        "session_id": started["session_id"],
                        "clicks": [{"cell": 3, "timestamp_ms": 10.0}],
                    },
                )
            )
            assert second["finished"] is False
            assert second["sequence"] == [3, 7]

            failed = await bus.request(
                Event(
                    topic=Topics.REQ_GM02_ANSWER,
                    source="test",
                    payload={
                        "session_id": started["session_id"],
                        "clicks": [{"cell": 4, "timestamp_ms": 20.0}],
                    },
                )
            )
            assert failed["finished"] is True
            assert failed["reason"] == "error"
            assert failed["metrics"]["m01_max_sequence_length"] == 1
        finally:
            await plugin.stop()

    asyncio.run(scenario())
