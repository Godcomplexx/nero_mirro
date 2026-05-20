from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from neuro_mirror.core.device_manager import DeviceManager
from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.device import IDeviceProvider
from neuro_mirror.models.device import DeviceInfo, DeviceSelection, DeviceValidation, SelectedDevices
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.aggregator.plugin import AggregatorPlugin, SessionState


class _NoopComposer:
    async def compose(self, payload):  # pragma: no cover - not used by these tests
        return ""


class _StaticDeviceProvider(IDeviceProvider):
    def __init__(self) -> None:
        self.camera = DeviceInfo(device_id="0", kind="camera", label="Camera 0", available=True)
        self.microphone = DeviceInfo(device_id="1", kind="microphone", label="Mic 1", available=True)

    def list_cameras(self) -> list[DeviceInfo]:
        return [self.camera]

    def list_microphones(self) -> list[DeviceInfo]:
        return [self.microphone]

    def validate_selection(self, selection: DeviceSelection) -> DeviceValidation:
        return DeviceValidation(
            ok=True,
            selected_devices=SelectedDevices(camera=self.camera, microphone=self.microphone),
            errors=[],
        )


class ScreeningDeviceFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_screening_starts_without_device_capture(self) -> None:
        """Screening now uses browser WebSocket frames — no PREPARE_SESSION or START_CAPTURE."""
        bus = EventBus()
        events = bus.subscribe(Topics.UI_UPDATE, Topics.PREPARE_SESSION, Topics.START_CAPTURE)
        aggregator = AggregatorPlugin(bus, appearance_composer=_NoopComposer())

        await aggregator.handle_event(
            Event(topic=Topics.UI_ACTION, source="test", payload={"action": "start_screening"})
        )

        # Only UI_UPDATE is published; no PREPARE_SESSION follows
        ui_update = await asyncio.wait_for(events.queue.get(), timeout=1)
        self.assertEqual(ui_update.topic, Topics.UI_UPDATE)
        self.assertEqual(aggregator.state, SessionState.SCREENING)
        self.assertEqual(aggregator._pending_capture_mode, "")

        # No more events should arrive
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(events.queue.get(), timeout=0.1)

    async def test_device_resolution_does_not_publish_patient_message(self) -> None:
        bus = EventBus()
        provider = _StaticDeviceProvider()

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = DeviceManager(
                bus,
                settings=Settings(),
                provider=provider,
                selection_path=Path(temp_dir) / "device_selection.json",
            )
            await manager._publish_catalog()

            ui_updates = bus.subscribe(Topics.UI_UPDATE)
            resolved_events = bus.subscribe(Topics.DEVICE_SELECTION_RESOLVED)

            await manager.handle_event(
                Event(topic=Topics.PREPARE_SESSION, source="test", payload={"mode": "daily_fast"})
            )

            resolved = await asyncio.wait_for(resolved_events.queue.get(), timeout=1)
            self.assertEqual(resolved.topic, Topics.DEVICE_SELECTION_RESOLVED)

            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(ui_updates.queue.get(), timeout=0.05)


if __name__ == "__main__":
    unittest.main()
