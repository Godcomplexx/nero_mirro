from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from neuro_mirror.plugins.ai_assistant.appearance_memory import AppearanceMemoryStore
from neuro_mirror.plugins.ai_assistant.appearance_response import AppearanceResponseComposer


class StaticVisionComposer(AppearanceResponseComposer):
    description: str = ""

    def _describe_appearance_with_vision_sync(self, frame_base64, analysis):  # type: ignore[no-untyped-def]
        return self.description

    def _rewrite_with_ollama_sync(self, template, analysis):  # type: ignore[no-untyped-def]
        return template


def make_composer(description: str, memory_store: AppearanceMemoryStore | None = None) -> StaticVisionComposer:
    composer = StaticVisionComposer(
        enabled=True,
        ai_backend="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="test",
        ollama_vision_model="test",
        timeout_seconds=10.0,
        memory_store=memory_store,
    )
    composer.description = description
    return composer


class AppearanceMemoryTest(unittest.TestCase):
    def test_first_analysis_returns_short_personal_assessment(self) -> None:
        composer = make_composer(
            "У тебя светлые волосы до плеч, спокойный взгляд и коричневая кофта. "
            "Образ выглядит аккуратно и мягко."
        )

        reply = asyncio.run(
            composer.compose({"frame_base64": "abc", "face_detected": True, "emotion": ""})
        )

        self.assertTrue(
            "кофт" in reply.lower() or "блуз" in reply.lower() or "одежд" in reply.lower(),
            f"Reply should mention clothing item, got: {reply}",
        )
        self.assertLessEqual(sum(reply.count(mark) for mark in ".!?"), 3)

    def test_second_analysis_compares_with_local_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AppearanceMemoryStore(Path(temp_dir) / "appearance_memory.json", limit=20)
            store.append(
                {
                    "hair": "тёмные волосы",
                    "clothing": "чёрное худи",
                    "accessories": "",
                    "style": "повседневный образ",
                    "mood": "спокойное настроение",
                    "summary": "прошлый образ",
                }
            )
            composer = make_composer(
                "Сегодня у тебя светлые волосы до плеч и коричневая кофта. "
                "Взгляд спокойный, образ выглядит аккуратно.",
                store,
            )

            analysis = {"frame_base64": "abc", "face_detected": True, "emotion": ""}
            reply = asyncio.run(composer.compose(analysis))

            # memory note is stored in analysis and contains change info
            self.assertIn("appearance_memory_notes", analysis)
            self.assertIn("причёска", analysis["appearance_memory_notes"])
            self.assertGreaterEqual(len(store.recent(5)), 2)

    def test_sad_mood_adds_soft_support_without_diagnosis(self) -> None:
        composer = make_composer(
            "У тебя аккуратные волосы, коричневая кофта и задумчивый грустный взгляд."
        )

        reply = asyncio.run(
            composer.compose({"frame_base64": "abc", "face_detected": True, "emotion": "грусть"})
        )

        self.assertIn("можем пройти короткий скрининг", reply)
        self.assertNotIn("диагноз", reply.lower())

    def test_red_face_adds_cautious_wellness_suggestion(self) -> None:
        composer = make_composer(
            "Лицо выглядит немного покрасневшим, волосы аккуратные, одежда спокойная."
        )

        reply = asyncio.run(
            composer.compose({"frame_base64": "abc", "face_detected": True, "emotion": ""})
        )

        self.assertIn("может быть свет, жара или усталость", reply)
        self.assertIn("измерить давление", reply)
        self.assertNotIn("у тебя давление", reply.lower())

    def test_memory_does_not_store_frame_base64(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "appearance_memory.json"
            store = AppearanceMemoryStore(path, limit=20)
            store.append(
                {
                    "frame_base64": "secret-image",
                    "hair": "светлые волосы",
                    "clothing": "коричневая кофта",
                    "summary": "аккуратный образ",
                }
            )

            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("frame_base64", json.dumps(raw, ensure_ascii=False))
            self.assertIn("светлые волосы", json.dumps(raw, ensure_ascii=False))

    def test_memory_limit_trims_old_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AppearanceMemoryStore(Path(temp_dir) / "appearance_memory.json", limit=3)
            for index in range(5):
                store.append({"hair": f"запись {index}", "summary": "тест"})

            recent = store.recent(10)
            self.assertEqual(len(recent), 3)
            self.assertEqual(recent[0]["hair"], "запись 2")
            self.assertEqual(recent[-1]["hair"], "запись 4")


if __name__ == "__main__":
    unittest.main()
