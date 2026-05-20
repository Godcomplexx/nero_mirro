from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.storage.plugin import StoragePlugin
from neuro_mirror.screening.moca_scoring import score_moca_tasks


class MocaScoringTest(unittest.TestCase):
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
        self.assertIn("3/5", task["details"])


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
