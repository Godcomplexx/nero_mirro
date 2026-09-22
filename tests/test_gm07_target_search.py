from __future__ import annotations

import asyncio

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.games.gm07_target_search.plugin import Gm07TargetSearchPlugin
from neuro_mirror.screening.gm07_scoring import score_gm07_trials


class _PredictableRandom:
    def shuffle(self, values: list[object]) -> None:
        return None

    def randrange(self, upper: int) -> int:
        return 0

    def choice(self, values):
        return values[0]


def test_gm07_scoring_separates_omissions_and_false_alarms() -> None:
    trials = [
        {"target_present": True, "correct": True, "response_kind": "stimulus", "reaction_ms": 500},
        {"target_present": True, "correct": False, "response_kind": "none", "reaction_ms": 700},
        {"target_present": False, "correct": False, "response_kind": "stimulus", "reaction_ms": 600},
        {"target_present": False, "correct": True, "response_kind": "none", "reaction_ms": 800},
    ]

    result = score_gm07_trials(trials, expected_trial_count=4)

    assert result["g07_omission_rate"] == 0.5
    assert result["g08_false_alarm_rate"] == 0.5
    assert result["u01_correct_action_rate"] == 0.5
    assert result["g03_median_reaction_ms"] == 650
    assert result["u06_complete"] is True


def test_gm07_plugin_returns_first_target_trial_and_accepts_answer() -> None:
    async def scenario() -> None:
        bus = EventBus()
        plugin = Gm07TargetSearchPlugin(bus)
        plugin._random = _PredictableRandom()  # type: ignore[assignment]
        await plugin.start()
        try:
            started = await bus.request(
                Event(topic=Topics.REQ_GM07_START, source="test")
            )
            target = next(
                item for item in started["stimuli"]
                if item["color"] == "red" and item["rotation"] == 0
            )
            reply = await bus.request(
                Event(
                    topic=Topics.REQ_GM07_ANSWER,
                    source="test",
                    payload={
                        "session_id": started["session_id"],
                        "selected_id": target["id"],
                        "timestamp_ms": 100.0,
                    },
                )
            )
            assert reply["finished"] is False
            assert reply["trial"] == 2
            assert plugin._sessions[started["session_id"]].trials[0]["correct"] is True
        finally:
            await plugin.stop()

    asyncio.run(scenario())
