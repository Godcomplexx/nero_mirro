from __future__ import annotations

import asyncio
import unittest

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.settings import Settings
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.aggregator.plugin import AggregatorPlugin, SessionState
from neuro_mirror.plugins.video_analysis.plugin import VisionWorkerPlugin


class RppgScreeningFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_video_analysis_passes_through_worker_screening_result(self) -> None:
        bus = EventBus()
        plugin = VisionWorkerPlugin(bus, settings=Settings())
        analysis_events = bus.subscribe(Topics.ANALYSIS_RESULT)

        await plugin._handle_capture(
            {
                "mode": "daily_fast",
                "analysis_result": {
                    "attention_score": 0.81,
                    "gaze_stability": 0.75,
                    "face_detected": True,
                    "face_count": 1,
                    "heart_rate_bpm": 72.4,
                    "heart_rate_status": "ok",
                    "heart_rate_algorithm": "PhysNet",
                },
            }
        )

        event = await asyncio.wait_for(analysis_events.queue.get(), timeout=1)
        self.assertEqual(event.payload["analysis_type"], "screening")
        self.assertEqual(event.payload["heart_rate_bpm"], 72.4)
        self.assertEqual(event.payload["heart_rate_algorithm"], "PhysNet")

    async def test_aggregator_includes_heart_rate_in_screening_report(self) -> None:
        bus = EventBus()
        plugin = AggregatorPlugin(bus, appearance_composer=object())  # type: ignore[arg-type]
        plugin.state = SessionState.MOCA
        plugin._latest_results = {
            "video": {
                "attention_score": 0.8,
                "gaze_stability": 0.7,
                "heart_rate_bpm": 71.0,
                "heart_rate_status": "ok",
                "heart_rate_algorithm": "PhysNet",
            },
            "moca": {
                "score": 10,
                "max_score": 15,
                "percent": 10 / 15,
                "tasks": [],
                "task_count": 0,
            },
        }
        reports = bus.subscribe(Topics.REPORT_DATA)

        await plugin._finish_moca()

        event = await asyncio.wait_for(reports.queue.get(), timeout=1)
        domains = event.payload["domains"]
        self.assertEqual(domains["heart_rate_bpm"], 71.0)
        self.assertEqual(domains["heart_rate_status"], "ok")
        self.assertEqual(domains["heart_rate_algorithm"], "PhysNet")


if __name__ == "__main__":
    unittest.main()
