from __future__ import annotations

import asyncio

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.gm14_word_builder.plugin import Gm14WordBuilderPlugin
from neuro_mirror.screening.gm14_scoring import score_gm14_words


class _ReverseRandom:
    def shuffle(self, values: list[object]) -> None:
        values.reverse()


def test_gm14_scoring_uses_first_full_attempt() -> None:
    result = score_gm14_words(
        [
            {
                "target": "лес",
                "attempt_count": 1,
                "first_attempt_correct_positions": 3,
                "duration_ms": 1000,
                "attempts": [{"assembled": "лес"}],
            },
            {
                "target": "море",
                "attempt_count": 2,
                "first_attempt_correct_positions": 2,
                "duration_ms": 2000,
                "attempts": [{"assembled": "мрое"}, {"assembled": "море"}],
            },
        ],
        expected_word_count=2,
    )

    assert result["u01_first_attempt_word_accuracy"] == 0.5
    assert result["l03_letter_position_accuracy"] == 5 / 7
    assert result["g10_repeated_attempts"] == 1
    assert result["u04_duration_ms"] == 3000
    assert result["u06_complete"] is True


def test_gm14_plugin_allows_correction_after_wrong_word() -> None:
    async def scenario() -> None:
        bus = EventBus()
        plugin = Gm14WordBuilderPlugin(bus)
        plugin._random = _ReverseRandom()  # type: ignore[assignment]
        await plugin.start()
        try:
            started = await bus.request(
                Event(topic=Topics.REQ_GM14_START, source="test")
            )
            session = plugin._sessions[started["session_id"]]
            target = session.words[0]
            wrong = target[::-1]
            if wrong == target:
                wrong = target[1:] + target[:1]

            rejected = await bus.request(
                Event(
                    topic=Topics.REQ_GM14_ANSWER,
                    source="test",
                    payload={
                        "session_id": started["session_id"],
                        "assembled": wrong,
                        "placements": [],
                        "timestamp_ms": 100.0,
                    },
                )
            )
            assert rejected["correct"] is False
            assert rejected["attempt_count"] == 1

            accepted = await bus.request(
                Event(
                    topic=Topics.REQ_GM14_ANSWER,
                    source="test",
                    payload={
                        "session_id": started["session_id"],
                        "assembled": target,
                        "placements": [],
                        "timestamp_ms": 200.0,
                    },
                )
            )
            assert accepted["correct"] is True
            assert accepted["word_number"] == 2
            assert session.completed_words[0]["attempt_count"] == 2
        finally:
            await plugin.stop()

    asyncio.run(scenario())
