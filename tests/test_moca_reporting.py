from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.storage.plugin import StoragePlugin
from neuro_mirror.screening.moca_scoring import (
    score_moca_task,
    score_moca_tasks,
    summarize_moca_tasks,
)


class MocaScoringTest(unittest.TestCase):
    def test_single_task_returns_earned_and_max_score(self) -> None:
        task = score_moca_task(
            "attention_digits_forward",
            "два один восемь пять четыре",
        )

        self.assertEqual(task["score"], 1)
        self.assertEqual(task["max_score"], 1)
        self.assertEqual(task["task_id"], "attention_digits_forward")

    def test_scored_tasks_are_summarized_without_rescoring(self) -> None:
        tasks = [
            score_moca_task("attention_digits_forward", "2 1 8 5 4"),
            score_moca_task("attention_digits_backward", "2 4 7"),
        ]

        result = summarize_moca_tasks(tasks)

        self.assertEqual(result["score"], 2)
        self.assertEqual(result["max_score"], 15)
        self.assertEqual(result["tasks"], tasks)

    def test_perfect_voice_moca_scores_15_points(self) -> None:
        result = score_moca_tasks(
            [
                {"task_id": "memory_1", "domain": "Память", "transcript": "лицо бархат церковь фиалка красный"},
                {"task_id": "memory_2", "domain": "Память", "transcript": "лицо бархат церковь фиалка красный"},
                {"task_id": "attention_digits_forward", "domain": "Внимание", "transcript": "2 1 8 5 4"},
                {"task_id": "attention_digits_backward", "domain": "Внимание", "transcript": "2 4 7"},
                {"task_id": "attention_serial", "domain": "Счет", "transcript": "93 | 86 | 79 | 72 | 65"},
                {
                    "task_id": "language_sentence_1",
                    "domain": "Речь",
                    "transcript": "я знаю только одно что иван это тот кто может сегодня помочь",
                },
                {
                    "task_id": "language_sentence_2",
                    "domain": "Речь",
                    "transcript": "кошка всегда пряталась под диваном когда собаки были в комнате",
                },
                {
                    "task_id": "language_fluency",
                    "domain": "Речь",
                    "transcript": "лес лампа лодка лук лист луна лиса ложка лента линия лекарство",
                },
                {"task_id": "abstraction_1", "domain": "Абстракция", "transcript": "это транспорт"},
                {"task_id": "abstraction_2", "domain": "Абстракция", "transcript": "это измерительные предметы"},
                {"task_id": "delayed_recall", "domain": "Память", "transcript": "лицо бархат церковь фиалка красный"},
            ]
        )

        self.assertEqual(result["score"], 15)
        self.assertEqual(result["max_score"], 15)

    def test_serial_subtraction_uses_partial_credit(self) -> None:
        result = score_moca_tasks(
            [{"task_id": "attention_serial", "domain": "Счет", "transcript": "93 | 86 | 70 | 72 | 60"}]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 2)
        self.assertIn("2/5", task["details"])

    def test_digit_span_ignores_numbers_before_and_after_answer(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_digits_backward",
                    "domain": "Внимание",
                    "transcript": "7 4 2, ответ: 2 4 7, все",
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 1)

    def test_digit_span_does_not_skip_error_inside_answer(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_digits_backward",
                    "domain": "Внимание",
                    "transcript": "9 2 4 8 7 5",
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 0)

    def test_digit_span_does_not_use_tolerance(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_digits_backward",
                    "domain": "Внимание",
                    "transcript": "2 4 8",
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 0)

    def test_serial_subtraction_does_not_skip_unclear_corrections(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": "90 91 93 90 86 79 70 72 65",
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 2)
        self.assertIn("3/5", task["details"])

    def test_serial_subtraction_does_not_skip_multiple_answers(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": "93 90 91 86",
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 1)

    def test_serial_subtraction_scores_chain_after_first_error(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": "92 85 78 71 64",
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 3)
        self.assertIn("4/5", task["details"])
        self.assertIn("92→85", task["details"])

    def test_serial_subtraction_splits_merged_100_and_first_answer(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": (
                        "сто девяносто три восемьдесят четыре "
                        "семьдесят семь семьдесят шестьдесят три"
                    ),
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 3)
        self.assertIn("Результаты: 93 84 77 70 63", task["details"])
        self.assertIn("4/5", task["details"])

    def test_serial_subtraction_understands_inflected_number(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": (
                        "сто минус семь будет девяносто три, "
                        "из восемьдесят шести минус семь будет "
                        "семьдесят девять, из семидесяти девяти "
                        "будет семьдесят два, из семидесяти двух "
                        "будет шестьдесят пять"
                    ),
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 3)
        self.assertIn("86→79", task["details"])

    def test_serial_subtraction_uses_immediate_corrections(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": "93 86 77 79 72 60 65",
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 3)
        self.assertIn("5/5", task["details"])
        self.assertIn("Исправления: 77 60", task["details"])

    def test_serial_subtraction_complex_record_stays_at_two_points(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": "97 97 94 94 87 87 73 60 66 59",
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 2)

    def test_serial_subtraction_separates_swallowed_minus_seven(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": (
                        "девяносто семь девяносто четыре, "
                        "девяносто четыре минус семь — восемьдесят семь, "
                        "восемьдесят семь убавляем, так, "
                        "восьмидесяти семь это будет уже семьдесят три, "
                        "шестьдесят, шестьдесят шесть, пятьдесят девять"
                    ),
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 3)
        self.assertIn("80→73", task["details"])

    def test_serial_subtraction_keeps_real_eighty_seven_operand(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": (
                        "из восьмидесяти семи минус семь "
                        "будет восемьдесят"
                    ),
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 1)
        self.assertIn("Результаты: 87 80", task["details"])

    def test_serial_subtraction_does_not_use_tolerance(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": "93 86 79 73 67",
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 2)
        self.assertIn("3/5", task["details"])

    def test_number_extraction_keeps_mixed_input_order(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "attention_serial",
                    "domain": "Счет",
                    "transcript": (
                        "100 минус 7: 93, восемьдесят шесть, "
                        "79, семьдесят два, 65"
                    ),
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 3)
        self.assertIn("5/5", task["details"])

    def test_sentence_rejects_reordered_words(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "language_sentence_2",
                    "domain": "Речь",
                    "transcript": (
                        "кошка всегда пряталась под диваном, "
                        "когда в комнате были собаки"
                    ),
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 0)
        self.assertIn("Не совпали слова", task["details"])

    def test_sentence_accepts_exact_answer(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "language_sentence_2",
                    "domain": "Речь",
                    "transcript": (
                        "кошка всегда пряталась под диваном, "
                        "когда собаки были в комнате"
                    ),
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 1)

    def test_sentence_accepts_changed_word_endings(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "language_sentence_2",
                    "domain": "Речь",
                    "transcript": (
                        "кошки всегда прятались под диван, "
                        "когда собаки были в комнате"
                    ),
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 1)

    def test_sentence_rejects_different_content_word(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "language_sentence_2",
                    "domain": "Речь",
                    "transcript": (
                        "кошка всегда пряталась под диваном, "
                        "когда собаки были дома"
                    ),
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 0)

    def test_sentence_rejects_missing_word(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "language_sentence_1",
                    "domain": "Речь",
                    "transcript": (
                        "я знаю только одно иван это тот кто "
                        "может сегодня помочь"
                    ),
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 0)
        self.assertIn("Количество слов не совпало", task["details"])

    def test_fluency_uses_full_range_without_duration_check(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "language_fluency",
                    "domain": "Речь",
                    "duration_ms": 180_000,
                    "transcript": (
                        "лес лампа лодка лук лист луна лиса ложка "
                        "лента линия лекарство"
                    ),
                }
            ]
        )
        task = result["tasks"][0]

        self.assertEqual(task["score"], 1)
        self.assertIn("во всем диапазоне", task["expected"])

    def test_abstraction_does_not_find_ride_inside_train(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "abstraction_1",
                    "domain": "Абстракция",
                    "transcript": "техника поезд велосипед",
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 0)

    def test_abstraction_accepts_scale_and_asr_phrase_error(self) -> None:
        tasks = [
            {
                "task_id": "abstraction_2",
                "domain": "Абстракция",
                "transcript": "шкала цифр",
            },
            {
                "task_id": "abstraction_2",
                "domain": "Абстракция",
                "transcript": "смирительный припод",
            },
            {
                "task_id": "abstraction_2",
                "domain": "Абстракция",
                "transcript": "часы линейка замерять замер делать",
            },
            {
                "task_id": "abstraction_2",
                "domain": "Абстракция",
                "transcript": "ими можно мерить величины",
            },
        ]
        result = score_moca_tasks(tasks)

        self.assertEqual(
            [task["score"] for task in result["tasks"]],
            [1, 1, 1, 1],
        )

    def test_delayed_recall_accepts_word_forms(self) -> None:
        result = score_moca_tasks(
            [
                {
                    "task_id": "delayed_recall",
                    "domain": "Память",
                    "transcript": "лица бархатом церкви фиалку красная",
                }
            ]
        )

        self.assertEqual(result["tasks"][0]["score"], 5)


class StoragePersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def test_storage_write_persists_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = StoragePlugin(EventBus())
            plugin.storage_path = Path(temp_dir) / "screenings.jsonl"
            plugin._items = []

            await plugin.handle_event(
                Event(
                    topic=Topics.STORAGE_WRITE,
                    source="test",
                    payload={"report_type": "screening", "domains": {"moca_score": 12}},
                )
            )

            lines = plugin.storage_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            saved = json.loads(lines[0])
            self.assertEqual(saved["report_type"], "screening")
            self.assertEqual(saved["domains"]["moca_score"], 12)
            self.assertIn("stored_at", saved)


if __name__ == "__main__":
    unittest.main()
