from __future__ import annotations

import os
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any

import numpy as np

try:
    import sounddevice as sd  # type: ignore
except Exception:
    sd = None

from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics


class VoiceRecorder:
    def __init__(self, *, sample_rate: int, channels: int, max_seconds: float) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_seconds = max_seconds
        self._stream = None
        self._wave_file: wave.Wave_write | None = None
        self._file_path = ""
        self._lock = threading.Lock()
        self._captured_frames = 0

    @property
    def available(self) -> bool:
        return sd is not None

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> str:
        if sd is None:
            raise RuntimeError("sounddevice не установлен")
        if self._stream is not None:
            raise RuntimeError("запись уже выполняется")

        fd, file_path = tempfile.mkstemp(prefix="neuro_mirror_", suffix=".wav")
        os.close(fd)
        self._file_path = file_path
        self._captured_frames = 0

        wave_file = wave.open(file_path, "wb")
        wave_file.setnchannels(self.channels)
        wave_file.setsampwidth(2)
        wave_file.setframerate(self.sample_rate)
        self._wave_file = wave_file
        max_frames = int(self.sample_rate * self.max_seconds)

        def callback(indata, frames, _time, status) -> None:
            if status:
                return
            pcm = (np.clip(indata, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            with self._lock:
                if self._wave_file is not None:
                    self._wave_file.writeframes(pcm)
                    self._captured_frames += frames
                if self._captured_frames >= max_frames:
                    raise sd.CallbackStop()

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()
        return file_path

    def stop(self) -> str:
        if self._stream is None:
            return ""

        self._stream.stop()
        self._stream.close()
        self._stream = None

        with self._lock:
            if self._wave_file is not None:
                self._wave_file.close()
                self._wave_file = None

        file_path = self._file_path
        self._file_path = ""
        return file_path


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
