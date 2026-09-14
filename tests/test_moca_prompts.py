from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.worker_client import WorkerResponse
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.moca_test.plugin import MocaTask, MocaTestPlugin
from neuro_mirror.plugins.moca_test.plugin import SERIAL_SUBTRACTION_STEPS
from neuro_mirror.plugins.speech_worker.plugin import SpeechWorkerPlugin


class MocaPromptTest(unittest.TestCase):
    def test_serial_subtraction_prompts_reference_current_number(self) -> None:
        prompts = [prompt for prompt, _expected in SERIAL_SUBTRACTION_STEPS]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertIn("данного числа", prompt)
                self.assertIn("семь", prompt)

    def test_language_fluency_uses_exactly_one_minute(self) -> None:
        from neuro_mirror.plugins.moca_test.plugin import MOCA_TASKS

        task = next(item for item in MOCA_TASKS if item.task_id == "language_fluency")
        self.assertEqual(task.max_record_seconds, 60.0)


class MocaTtsFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_speak_waits_for_browser_playback_finished_event(self) -> None:
        bus = EventBus()
        plugin = MocaTestPlugin(bus, settings=Settings())
        ui_updates = bus.subscribe(Topics.UI_UPDATE)

        speak_task = asyncio.create_task(plugin._speak("Тестовое задание."))
        update = await asyncio.wait_for(ui_updates.queue.get(), timeout=1)

        self.assertEqual(update.payload["moca_recording"], False)
        self.assertFalse(speak_task.done())

        await plugin.handle_event(
            Event(
                topic=Topics.UI_ACTION,
                source="test",
                payload={
                    "action": "moca_tts_finished",
                    "moca_tts_id": update.payload["moca_tts_id"],
                },
            )
        )

        self.assertTrue(await asyncio.wait_for(speak_task, timeout=1))


class MocaMissingSpeechTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_transcription_becomes_empty_answer_instead_of_error(self) -> None:
        bus = EventBus()
        bus.request = AsyncMock(return_value={
            "accepted": False,
            "transcript": "",
            "message": "Речь не распознана.",
        })
        plugin = MocaTestPlugin(bus, settings=Settings())

        transcript = await plugin._transcribe("missing-answer.wav")

        self.assertEqual(transcript, "")

    async def test_empty_answer_does_not_abort_the_test(self) -> None:
        bus = EventBus()
        plugin = MocaTestPlugin(bus, settings=Settings())
        plugin._speak = AsyncMock(return_value=True)
        plugin._record_and_transcribe = AsyncMock(return_value="")
        results = bus.subscribe(Topics.MOCA_TEST_RESULT)
        task = MocaTask(task_id="attention_digits_backward", domain="Внимание", prompt="Тест")

        with patch("neuro_mirror.plugins.moca_test.plugin.MOCA_TASKS", [task]):
            await plugin._run_test()

        event = await asyncio.wait_for(results.queue.get(), timeout=1)
        self.assertEqual(event.payload["task_count"], 1)
        self.assertEqual(event.payload["tasks"][0]["transcript"], "")
        self.assertEqual(event.payload["tasks"][0]["score"], 0)


class _FakeSpeechWorker:
    async def request(self, action, payload, *, timeout=None):  # type: ignore[no-untyped-def]
        return WorkerResponse(
            ok=True,
            result={
                "transcript": "тестовый ответ",
                "confidence_score": 0.95,
                "average_logprob": -0.1,
                "max_no_speech_prob": 0.01,
            },
        )


class MocaSpeechUiTest(unittest.IsolatedAsyncioTestCase):
    async def test_moca_transcription_does_not_switch_screen_to_assistant(self) -> None:
        bus = EventBus()
        plugin = SpeechWorkerPlugin(bus, settings=Settings())
        plugin.worker = _FakeSpeechWorker()  # type: ignore[assignment]
        ui_updates = bus.subscribe(Topics.UI_UPDATE)
        responses = bus.subscribe(Topics.RESP_SPEECH_TRANSCRIBE)

        await plugin._handle_req_transcribe(
            Event(
                topic=Topics.REQ_SPEECH_TRANSCRIBE,
                source="moca_test",
                payload={
                    "_request_id": "req-1",
                    "audio_path": "answer.wav",
                    "suppress_ui": True,
                },
            )
        )

        response = await asyncio.wait_for(responses.queue.get(), timeout=1)
        self.assertEqual(response.payload["transcript"], "Тестовый ответ")

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ui_updates.queue.get(), timeout=0.05)


if __name__ == "__main__":
    unittest.main()
