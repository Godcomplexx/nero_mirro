from __future__ import annotations

import asyncio
from dataclasses import dataclass

from neuro_mirror.core.dataset_store import DatasetStore
from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.device_manager import DeviceManager
from neuro_mirror.core.plugin_manager import PluginManager
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.session_store import SessionStore
from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.aggregator.plugin import AggregatorPlugin
from neuro_mirror.plugins.camera.plugin import CameraPlugin
from neuro_mirror.plugins.microphone.plugin import MicrophonePlugin
from neuro_mirror.plugins.speech_worker.plugin import SpeechWorkerPlugin
from neuro_mirror.plugins.storage.plugin import StoragePlugin
from neuro_mirror.plugins.video_analysis.plugin import VisionWorkerPlugin
from neuro_mirror.plugins.voice_test.plugin import VoiceTestPlugin
from neuro_mirror.plugins.moca_test.plugin import MocaTestPlugin
from neuro_mirror.plugins.hads_test.plugin import HadsTestPlugin
from neuro_mirror.plugins.games.registry import iter_game_plugins
from neuro_mirror.plugins.games.coordinator import GameSessionCoordinator
from neuro_mirror.plugins.games.history import GameHistoryStore


@dataclass(slots=True)
class RuntimeHandle:
    settings: Settings
    bus: EventBus
    plugin_manager: PluginManager
    stop_event: asyncio.Event
    session_store: SessionStore
    dataset_store: DatasetStore
    game_history_store: GameHistoryStore

    async def start(self) -> None:
        await self.plugin_manager.start_all()

    async def stop(self) -> None:
        await self.plugin_manager.stop_all()

    async def bootstrap(self, *, auto_start_override: bool | None = None) -> None:
        await self.bus.publish(Event(topic=Topics.SYSTEM_BOOTSTRAP, source="bootstrap"))

        auto_start = self.settings.auto_start if auto_start_override is None else auto_start_override
        if not auto_start:
            return

        await self.bus.publish(
            Event(
                topic=Topics.UI_ACTION,
                source="bootstrap",
                payload={"action": "start_screening"},
            )
        )


def create_runtime(
    settings: Settings,
    *,
    stop_event: asyncio.Event | None = None,
    extra_plugins: list[Plugin] | None = None,
) -> RuntimeHandle:
    bus = EventBus()
    plugin_manager = PluginManager()
    stop_event = stop_event or asyncio.Event()

    session_store = SessionStore()
    dataset_store = DatasetStore()
    game_history_store = GameHistoryStore()

    plugin_manager.register(DeviceManager(bus, settings=settings))
    plugin_manager.register(StoragePlugin(bus))
    plugin_manager.register(CameraPlugin(bus, settings=settings))
    plugin_manager.register(MicrophonePlugin(bus, settings=settings))
    plugin_manager.register(VisionWorkerPlugin(bus, settings=settings))
    plugin_manager.register(SpeechWorkerPlugin(bus, settings=settings))
    plugin_manager.register(VoiceTestPlugin(bus, settings=settings))
    plugin_manager.register(MocaTestPlugin(bus, settings=settings, dataset_store=dataset_store))
    plugin_manager.register(HadsTestPlugin(bus, settings=settings, dataset_store=dataset_store))
    for game_plugin in iter_game_plugins(bus):
        plugin_manager.register(game_plugin)
    plugin_manager.register(
        GameSessionCoordinator(
            bus,
            session_store=session_store,
            history_store=game_history_store,
        )
    )
    plugin_manager.register(
        AggregatorPlugin(
            bus,
            session_store=session_store,
            settings=settings,
            dataset_store=dataset_store,
        )
    )

    for plugin in extra_plugins or []:
        plugin_manager.register(plugin)

    return RuntimeHandle(
        settings=settings,
        bus=bus,
        plugin_manager=plugin_manager,
        stop_event=stop_event,
        session_store=session_store,
        dataset_store=dataset_store,
        game_history_store=game_history_store,
    )
