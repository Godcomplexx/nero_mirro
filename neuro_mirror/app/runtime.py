from __future__ import annotations

import asyncio
from dataclasses import dataclass

from neuro_mirror.core.event_bus import EventBus
from neuro_mirror.core.device_manager import DeviceManager
from neuro_mirror.core.plugin_manager import PluginManager
from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.plugin import Plugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.aggregator.plugin import AggregatorPlugin
from neuro_mirror.plugins.ai_assistant.appearance_response import AppearanceResponseComposer
from neuro_mirror.plugins.ai_assistant.backends import build_assistant_backend
from neuro_mirror.plugins.ai_assistant.plugin import AIAssistantPlugin
from neuro_mirror.plugins.ai_assistant.rules import load_assistant_rules
from neuro_mirror.plugins.camera.plugin import CameraPlugin
from neuro_mirror.plugins.microphone.plugin import MicrophonePlugin
from neuro_mirror.plugins.speech_worker.plugin import SpeechWorkerPlugin
from neuro_mirror.plugins.storage.plugin import StoragePlugin
from neuro_mirror.plugins.video_analysis.plugin import VisionWorkerPlugin
from neuro_mirror.plugins.voice_test.plugin import DemoVoiceTestPlugin


@dataclass(slots=True)
class RuntimeHandle:
    settings: Settings
    bus: EventBus
    plugin_manager: PluginManager
    stop_event: asyncio.Event
    assistant_backend_label: str
    weather_source_label: str

    async def start(self) -> None:
        await self.plugin_manager.start_all()

    async def stop(self) -> None:
        await self.plugin_manager.stop_all()

    async def bootstrap(self, *, auto_start_override: bool | None = None) -> None:
        await self.bus.publish(Event(topic=Topics.SYSTEM_BOOTSTRAP, source="bootstrap"))

        auto_start = self.settings.auto_start if auto_start_override is None else auto_start_override
        if not auto_start:
            return

        if self.settings.enable_ai_assistant:
            await self.bus.publish(
                Event(
                    topic=Topics.VOICE_INTENT,
                    source="bootstrap",
                    payload={"intent": "start_screening"},
                )
            )
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
    include_ai_plugin: bool = True,
    extra_plugins: list[Plugin] | None = None,
) -> RuntimeHandle:
    bus = EventBus()
    plugin_manager = PluginManager()
    stop_event = stop_event or asyncio.Event()

    assistant_backend_label = (
        f"{settings.ai_backend}:{settings.ollama_model}"
        if settings.enable_ai_assistant
        else "выключен"
    )
    weather_source_label = (
        f"Фиксированная локация: {settings.weather_location}"
        if settings.weather_location
        else "Автоматическое определение по IP"
    )
    assistant_rules = load_assistant_rules(settings.assistant_rules_path)

    appearance_composer = AppearanceResponseComposer(
        enabled=settings.enable_ai_assistant,
        ai_backend=settings.ai_backend,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
        ollama_vision_model=settings.ollama_vision_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        assistant_rules=assistant_rules,
    )

    plugin_manager.register(DeviceManager(bus, settings=settings))
    plugin_manager.register(StoragePlugin(bus))
    plugin_manager.register(CameraPlugin(bus, settings=settings))
    plugin_manager.register(MicrophonePlugin(bus, settings=settings))
    plugin_manager.register(
        VisionWorkerPlugin(bus, settings=settings, appearance_composer=appearance_composer)
    )
    plugin_manager.register(SpeechWorkerPlugin(bus, settings=settings))
    plugin_manager.register(DemoVoiceTestPlugin(bus))
    plugin_manager.register(AggregatorPlugin(bus, appearance_composer=appearance_composer))

    if include_ai_plugin:
        plugin_manager.register(
            AIAssistantPlugin(
                bus,
                enabled=settings.enable_ai_assistant,
                backend=build_assistant_backend(settings, assistant_rules=assistant_rules),
                settings=settings,
            )
        )

    for plugin in extra_plugins or []:
        plugin_manager.register(plugin)

    return RuntimeHandle(
        settings=settings,
        bus=bus,
        plugin_manager=plugin_manager,
        stop_event=stop_event,
        assistant_backend_label=assistant_backend_label,
        weather_source_label=weather_source_label,
    )
