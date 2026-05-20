from __future__ import annotations

import asyncio
import unittest

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.worker_client import WorkerResponse
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.moca_test.plugin import MocaTestPlugin
from neuro_mirror.plugins.moca_test.plugin import SERIAL_SUBTRACTION_STEPS
from neuro_mirror.plugins.speech_worker.plugin import SpeechWorkerPlugin


class MocaPromptTest(unittest.TestCase):
    def test_serial_subtraction_prompts_reference_current_number(self) -> None:
        prompts = [prompt for prompt, _expected in SERIAL_SUBTRACTION_STEPS]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertIn("данного числа", prompt)
                self.assertIn("семь", prompt)


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
