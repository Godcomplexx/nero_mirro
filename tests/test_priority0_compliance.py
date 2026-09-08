from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.session_store import SessionStore
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.user_profiles import UserProfileStore
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.aggregator.plugin import AggregatorPlugin
from neuro_mirror.plugins.hads_test.plugin import HadsTestPlugin
from neuro_mirror.plugins.moca_test.plugin import MocaTestPlugin
from neuro_mirror.plugins.storage.plugin import StoragePlugin
from neuro_mirror.screening.audio_analyzer import analyze_audio
from neuro_mirror.screening.video_analyzer import analyze_frames


class _RequestBus:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    async def request(self, _event, *, timeout: float = 0) -> dict:
        if self.error is not None:
            raise self.error
        return {"transcript": "тест"}


class _Composer:
    async def compose(self, _payload):
        return "ok"


class TempAudioLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_moca_removes_audio_after_success(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
            path = Path(temp.name)
        plugin = MocaTestPlugin(_RequestBus(), settings=Settings())
        self.assertEqual(await plugin._transcribe(str(path)), "тест")
        self.assertFalse(path.exists())

    async def test_hads_removes_audio_after_failure(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
            path = Path(temp.name)
        plugin = HadsTestPlugin(
            _RequestBus(error=RuntimeError("worker failed")),
            settings=Settings(),
        )
        self.assertEqual(await plugin._transcribe(str(path)), "")
        self.assertFalse(path.exists())


class ConsentModelTest(unittest.TestCase):
    def test_separate_consents_and_legacy_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = UserProfileStore(temp_dir)
            user = store.create_user(
                "Тест",
                consent=True,
                personal_data_consent=True,
                audio_data_consent=False,
                video_data_consent=True,
            )
            self.assertTrue(store.has_consent(user["id"], "personal"))
            self.assertFalse(store.has_consent(user["id"], "audio"))
            self.assertTrue(store.has_consent(user["id"], "video"))

            legacy_path = Path(temp_dir) / "users.json"
            legacy_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "u0099",
                            "name": "Legacy",
                            "consent": {
                                "given": True,
                                "timestamp": "2026-01-01T00:00:00+00:00",
                            },
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            migrated = UserProfileStore(temp_dir)
            for consent_type in ("personal", "audio", "video"):
                self.assertTrue(migrated.has_consent("u0099", consent_type))


class DeidentifiedStorageTest(unittest.IsolatedAsyncioTestCase):
    async def test_direct_identifiers_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = StoragePlugin(EventBus())
            plugin.storage_path = Path(temp_dir) / "screenings.jsonl"
            plugin._items = []
            await plugin.handle_event(
                Event(
                    topic=Topics.USER_SELECTED,
                    source="test",
                    payload={"user_id": "u0001", "user_name": "Иван Иванов"},
                )
            )
            await plugin.handle_event(
                Event(
                    topic=Topics.STORAGE_WRITE,
                    source="test",
                    payload={
                        "report_type": "hads",
                        "name": "Иван Иванов",
                        "contact": "test@example.org",
                        "notes": "Телефон +7 999 123-45-67",
                    },
                )
            )
            saved = json.loads(plugin.storage_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["user_id"], "u0001")
            self.assertNotIn("user_name", saved)
            self.assertNotIn("name", saved)
            self.assertNotIn("test@example.org", json.dumps(saved, ensure_ascii=False))
            self.assertNotIn("+7 999 123-45-67", json.dumps(saved, ensure_ascii=False))


class SessionLifecycleTest(unittest.TestCase):
    def test_checkpoint_interrupt_resume_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sessions.json"
            store = SessionStore(path)
            session = store.start(
                user_id="u0001",
                scenario="moca",
                versions={"app": "0.5.0"},
                technical_params={"mic_ok": True},
                permissions={"audio": True},
            )
            session_id = session["session_id"]
            store.checkpoint(
                session_id,
                {"source": "moca", "next_index": 2, "results": [{"task_id": "one"}]},
            )
            store.interrupt(session_id, "Остановлено пользователем.")

            reloaded = SessionStore(path)
            self.assertEqual(reloaded.get(session_id)["status"], "interrupted")
            resumed = reloaded.resume(session_id, user_id="u0001")
            self.assertEqual(resumed["checkpoint"]["next_index"], 2)
            completed = reloaded.complete(session_id, {"score": 10})
            self.assertEqual(completed["status"], "completed")
            self.assertIsNotNone(completed["finished_at"])

    def test_another_user_cannot_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(Path(temp_dir) / "sessions.json")
            session = store.start(
                user_id="u0001",
                scenario="hads",
                versions={},
            )
            with self.assertRaises(PermissionError):
                store.resume(session["session_id"], user_id="u0002")

    def test_stale_in_progress_session_becomes_resumable_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sessions.json"
            store = SessionStore(path)
            session = store.start(user_id="u0001", scenario="moca", versions={})
            reloaded = SessionStore(path)
            recovered = reloaded.get(session["session_id"])
            self.assertEqual(recovered["status"], "interrupted")
            self.assertIn("завершено", recovered["interruption_reason"])


class AggregatorSessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_completed_moca_is_linked_to_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(Path(temp_dir) / "sessions.json")
            plugin = AggregatorPlugin(
                EventBus(),
                appearance_composer=_Composer(),
                session_store=store,
                settings=Settings(),
            )
            await plugin.handle_event(
                Event(
                    topic=Topics.USER_SELECTED,
                    source="test",
                    payload={"user_id": "u0001"},
                )
            )
            await plugin.handle_event(
                Event(
                    topic=Topics.UI_ACTION,
                    source="test",
                    payload={
                        "action": "start_moca",
                        "audio_allowed": True,
                        "session_conditions": {"mic_ok": True},
                    },
                )
            )
            active = store.list_for_user("u0001", resumable_only=True)
            self.assertEqual(len(active), 1)
            session_id = active[0]["session_id"]
            await plugin.handle_event(
                Event(
                    topic=Topics.MOCA_TEST_RESULT,
                    source="test",
                    payload={
                        "score": 10,
                        "max_score": 15,
                        "percent": 0.667,
                        "tasks": [],
                    },
                )
            )
            completed = store.get(session_id)
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["result"]["session_id"], session_id)


class HonestUnavailableMetricsTest(unittest.TestCase):
    def test_stub_analyzers_do_not_return_fabricated_numbers(self) -> None:
        video = analyze_frames([b"not-a-real-frame"])
        audio = analyze_audio("placeholder.wav")
        self.assertIsNone(video.attention_score)
        self.assertIsNone(video.gaze_stability)
        self.assertIsNone(audio.speech_score)
        self.assertIsNone(audio.reaction_ms)


if __name__ == "__main__":
    unittest.main()
