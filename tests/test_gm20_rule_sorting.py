from __future__ import annotations

import asyncio

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.gm20_rule_sorting.plugin import Gm20RuleSortingPlugin
from neuro_mirror.screening.gm20_scoring import score_gm20_trials


class _PredictableRandom:
    def choice(self, values):
        return values[0]

    def shuffle(self, values: list[object]) -> None:
        values.reverse()


def test_gm20_scoring_counts_perseveration_and_rule_violation() -> None:
    trials = [
        {
            "correct": True,
            "selected_reference": "reference-0",
            "matches": {"color": "reference-0", "shape": "reference-1", "count": "reference-2"},
            "previous_rule": None,
            "trials_since_switch": 1000,
            "reaction_ms": 400,
        },
        {
            "correct": False,
            "selected_reference": "reference-0",
            "matches": {"color": "reference-0", "shape": "reference-1", "count": "reference-2"},
            "previous_rule": "color",
            "trials_since_switch": 1,
            "reaction_ms": 500,
        },
        {
            "correct": False,
            "selected_reference": "reference-3",
            "matches": {"color": "reference-0", "shape": "reference-1", "count": "reference-2"},
            "previous_rule": "color",
            "trials_since_switch": 2,
            "reaction_ms": 600,
        },
    ]

    result = score_gm20_trials(trials, expected_trial_count=3)

    assert result["u01_correct_action_rate"] == 1 / 3
    assert result["e06_perseverative_errors"] == 1
    assert result["e05_rule_violations"] == 1
    assert result["u06_complete"] is True


def test_gm20_plugin_switches_after_ten_consecutive_correct_answers() -> None:
    async def scenario() -> None:
        bus = EventBus()
        plugin = Gm20RuleSortingPlugin(bus)
        plugin._random = _PredictableRandom()  # type: ignore[assignment]
        await plugin.start()
        try:
            reply = await bus.request(Event(topic=Topics.REQ_GM20_START, source="test"))
            session = plugin._sessions[reply["session_id"]]
            assert session.active_rule == "color"

            for _ in range(10):
                selected = session.current_matches[session.active_rule]
                reply = await bus.request(
                    Event(
                        topic=Topics.REQ_GM20_ANSWER,
                        source="test",
                        payload={
                            "session_id": session.session_id,
                            "selected_reference": selected,
                            "timestamp_ms": 100.0,
                        },
                    )
                )

            assert reply["feedback"] == "correct"
            assert session.active_rule == "shape"
            assert session.previous_rule == "color"
            assert session.trial_index == 10
            assert all(trial["correct"] for trial in session.trials)
        finally:
            await plugin.stop()

    asyncio.run(scenario())
