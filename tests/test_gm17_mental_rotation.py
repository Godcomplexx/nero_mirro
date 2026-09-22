from __future__ import annotations

import asyncio

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.gm17_mental_rotation.plugin import Gm17MentalRotationPlugin
from neuro_mirror.screening.gm17_scoring import score_gm17_trials


class _PredictableRandom:
    def choice(self, values):
        return values[0]

    def shuffle(self, values: list[object]) -> None:
        values.reverse()


def test_gm17_scoring_uses_first_responses() -> None:
    result = score_gm17_trials(
        [
            {"selected_id": "a", "correct": True, "reaction_ms": 400},
            {"selected_id": "b", "correct": False, "reaction_ms": 600},
            {"selected_id": "c", "correct": True, "reaction_ms": 800},
        ],
        expected_trial_count=3,
    )

    assert result["u01_correct_action_rate"] == 2 / 3
    assert result["g03_median_reaction_ms"] == 600
    assert result["u07_error_count"] == 1
    assert result["u06_complete"] is True
    assert result["u06_technically_valid"] is True


def test_gm17_plugin_advances_after_one_choice() -> None:
    async def scenario() -> None:
        bus = EventBus()
        plugin = Gm17MentalRotationPlugin(bus)
        plugin._random = _PredictableRandom()  # type: ignore[assignment]
        await plugin.start()
        try:
            started = await bus.request(
                Event(topic=Topics.REQ_GM17_START, source="test")
            )
            session = plugin._sessions[started["session_id"]]
            correct_id = session.correct_choice_id
            assert len(started["choices"]) == 2

            reply = await bus.request(
                Event(
                    topic=Topics.REQ_GM17_ANSWER,
                    source="test",
                    payload={
                        "session_id": started["session_id"],
                        "selected_id": correct_id,
                        "timestamp_ms": 100.0,
                    },
                )
            )
            assert reply["finished"] is False
            assert reply["trial"] == 2
            assert session.trials[0]["correct"] is True
        finally:
            await plugin.stop()

    asyncio.run(scenario())
