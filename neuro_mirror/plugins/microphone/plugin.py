from __future__ import annotations

from pathlib import Path
from typing import Any

from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.utils.audio import VoiceRecorder


class MicrophonePlugin(ProcessorPlugin):
    plugin_name = "microphone"

    def __init__(self, bus, *, settings: Settings) -> None:
        super().__init__(bus)
        self.settings = settings
        self.recorder = VoiceRecorder(
            sample_rate=settings.voice_sample_rate,
            channels=settings.voice_channels,
            max_seconds=settings.voice_max_record_seconds,
        )

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.UI_ACTION,)

    async def on_start(self) -> None:
        await self._publish_status_snapshot()

    async def on_stop(self) -> None:
        if self.recorder.recording:
            audio_path = self.recorder.stop()
            self._delete_temp_file(audio_path)

    async def handle_event(self, event: Event) -> None:
        action = str(event.payload.get("action") or "")
        if action == "start_voice_capture":
            await self._start_voice_capture(event.payload)
            return
        if action == "stop_voice_capture":
            await self._stop_voice_capture(event.payload)

    async def _start_voice_capture(self, payload: dict[str, Any]) -> None:
        if not self.recorder.available:
            await self._publish_status_snapshot(message="Микрофонный ввод недоступен: sounddevice не установлен.")
            return

        if self.recorder.recording:
            await self._publish_status_snapshot(message="Запись уже выполняется.")
            return

        try:
            self.recorder.start()
        except Exception as exc:
            await self._publish_status_snapshot(message=f"Не удалось начать запись: {exc}")
            return

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "recording_active": True,
                    "message": "Идёт запись. Нажмите ещё раз, чтобы остановить.",
                },
            )
        )
        await self._publish_status_snapshot()

    async def _stop_voice_capture(self, payload: dict[str, Any]) -> None:
        if not self.recorder.recording:
            await self._publish_status_snapshot(message="Запись не запущена.")
            return

        audio_path = self.recorder.stop()
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "recording_active": False,
                    "message": "Распознаю голосовую реплику.",
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.SENSOR_AUDIO_CHUNK,
                source=self.name,
                payload={**payload, "audio_path": audio_path},
            )
        )
        await self._publish_status_snapshot()

    async def _publish_status_snapshot(self, *, message: str | None = None) -> None:
        payload: dict[str, Any] = {
            "worker_statuses": {
                "microphone": {
                    "available": self.recorder.available,
                    "detail": "Микрофонный ввод доступен" if self.recorder.available else "Микрофонный ввод недоступен",
                }
            },
            "recording_active": self.recorder.recording,
        }
        if message:
            payload["message"] = message
        await self.bus.publish(Event(topic=Topics.UI_UPDATE, source=self.name, payload=payload))

    @staticmethod
    def _delete_temp_file(file_path: str) -> None:
        if not file_path:
            return
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            return
