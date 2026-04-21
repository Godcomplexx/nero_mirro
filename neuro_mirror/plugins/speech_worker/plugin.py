from __future__ import annotations

import asyncio
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
from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task
from neuro_mirror.core.worker_client import WorkerClient
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.backends import normalize_user_utterance


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


class SpeechWorkerPlugin(ProcessorPlugin):
    plugin_name = "speech_worker"

    def __init__(self, bus, *, settings: Settings) -> None:
        super().__init__(bus)
        self.settings = settings
        self.worker = WorkerClient(
            name="speech_worker",
            python_executable=settings.speech_worker_python,
            script_path=settings.speech_worker_script,
            request_timeout_seconds=settings.worker_request_timeout_seconds,
        )
        self.recorder = VoiceRecorder(
            sample_rate=settings.voice_sample_rate,
            channels=settings.voice_channels,
            max_seconds=settings.voice_max_record_seconds,
        )
        self._recording_path = ""
        self._last_status: dict[str, Any] = {}
        self._warmup_task: asyncio.Task[None] | None = None

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.UI_ACTION,)

    async def on_start(self) -> None:
        await self._ensure_worker_started()
        await self._publish_status_snapshot()
        self._warmup_task = asyncio.create_task(self._warmup_model(), name="speech-worker-warmup")

    async def on_stop(self) -> None:
        if self.recorder.recording:
            self.recorder.stop()
        if self._warmup_task is not None:
            self._warmup_task.cancel()
            try:
                await self._warmup_task
            except asyncio.CancelledError:
                pass
            self._warmup_task = None
        await self.worker.stop()

    async def handle_event(self, event: Event) -> None:
        action = str(event.payload.get("action") or "")
        if action == "start_voice_capture":
            await self._start_voice_capture()
            return
        if action == "stop_voice_capture":
            await self._stop_voice_capture()

    async def _ensure_worker_started(self) -> None:
        try:
            await self.worker.start()
            await self.worker.request("health")
        except Exception:
            pass

    async def _start_voice_capture(self) -> None:
        if not self.recorder.available:
            await self._publish_status_snapshot(message="Микрофонный ввод недоступен: sounddevice не установлен.")
            return

        if self.recorder.recording:
            await self._publish_status_snapshot(message="Запись уже выполняется.")
            return

        try:
            self._recording_path = self.recorder.start()
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

    async def _stop_voice_capture(self) -> None:
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

        payload = {
            "audio_path": audio_path,
            "model_name": self.settings.stt_model_name,
            "language": self.settings.stt_language,
            "device": self.settings.stt_device,
            "compute_type": self.settings.stt_compute_type,
            "beam_size": self.settings.stt_beam_size,
            "best_of": self.settings.stt_best_of,
            "vad_filter": self.settings.stt_vad_filter,
            "hotwords": self.settings.stt_hotwords,
        }
        try:
            if self.settings.stt_device == "cpu":
                response = await self.worker.request("transcribe_audio_file", payload)
            else:
                async with exclusive_gpu_task("stt"):
                    response = await self.worker.request("transcribe_audio_file", payload)
        except Exception as exc:
            await self._publish_status_snapshot(message=f"Ошибка speech worker: {exc}")
            self._delete_temp_file(audio_path)
            return

        self._delete_temp_file(audio_path)

        if not response.ok:
            await self._publish_status_snapshot(message=f"Speech worker error: {response.error_message}")
            return

        raw_transcript = str(response.result.get("transcript") or "").strip()
        transcript = normalize_user_utterance(raw_transcript) or raw_transcript
        notes = str(response.result.get("notes") or "").strip()
        load_ms = response.result.get("load_ms")
        transcribe_ms = response.result.get("transcribe_ms")
        confidence_score = response.result.get("confidence_score")
        average_logprob = response.result.get("average_logprob")
        max_no_speech_prob = response.result.get("max_no_speech_prob")

        if not raw_transcript:
            message = notes or "Речь не распознана."
            await self._publish_status_snapshot(message=message)
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "transcript_text": "",
                        "recording_active": False,
                        "message": message,
                    },
                )
            )
            return

        if self._is_low_confidence_transcript(
            transcript,
            confidence_score=confidence_score,
            average_logprob=average_logprob,
            max_no_speech_prob=max_no_speech_prob,
        ):
            message = "Ещё раз сформулируйте вопрос: речь распознана неуверенно."
            await self._publish_status_snapshot(message=message)
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "transcript_text": transcript,
                        "recording_active": False,
                        "message": message,
                    },
                )
            )
            return

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "transcript_text": transcript,
                    "recording_active": False,
                    "message": self._transcript_message(transcript, load_ms=load_ms, transcribe_ms=transcribe_ms),
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.VOICE_INTENT,
                source=self.name,
                payload={"utterance": transcript, "raw_utterance": raw_transcript},
            )
        )
        await self._publish_status_snapshot()

    async def _warmup_model(self) -> None:
        try:
            payload = {
                "model_name": self.settings.stt_model_name,
                "device": self.settings.stt_device,
                "compute_type": self.settings.stt_compute_type,
            }
            if self.settings.stt_device == "cpu":
                await self.worker.request("warmup_model", payload)
            else:
                async with exclusive_gpu_task("stt"):
                    await self.worker.request("warmup_model", payload)
        except Exception:
            return

    async def _publish_status_snapshot(self, *, message: str | None = None) -> None:
        speech_worker_available = False
        stt_available = False
        try:
            response = await self.worker.request("health")
            if response.ok:
                speech_worker_available = bool(response.result.get("worker_available", True))
                stt_available = bool(response.result.get("stt_available", False))
        except Exception:
            speech_worker_available = False
            stt_available = False

        status = {
            "speech_worker": {
                "available": speech_worker_available,
                "detail": "Speech worker активен" if speech_worker_available else "Speech worker недоступен",
            },
            "microphone": {
                "available": self.recorder.available,
                "detail": "Микрофонный ввод доступен" if self.recorder.available else "Микрофонный ввод недоступен",
            },
            "stt": {
                "available": stt_available,
                "detail": f"STT ({self.settings.stt_model_name}, {self.settings.stt_compute_type}) доступен"
                if stt_available
                else "STT недоступен",
            },
        }
        self._last_status = status
        payload: dict[str, Any] = {
            "worker_statuses": status,
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

    @staticmethod
    def _transcript_message(transcript: str, *, load_ms: Any, transcribe_ms: Any) -> str:
        metrics: list[str] = []
        if load_ms is not None:
            metrics.append(f"загрузка {load_ms} мс")
        if transcribe_ms is not None:
            metrics.append(f"распознавание {transcribe_ms} мс")
        if metrics:
            return f"Распознан текст: {transcript} ({', '.join(metrics)})"
        return f"Распознан текст: {transcript}"

    @staticmethod
    def _is_low_confidence_transcript(
        transcript: str,
        *,
        confidence_score: Any,
        average_logprob: Any,
        max_no_speech_prob: Any,
    ) -> bool:
        if not transcript.strip():
            return True
        if isinstance(confidence_score, (int, float)) and float(confidence_score) < 0.45:
            return True
        if isinstance(average_logprob, (int, float)) and float(average_logprob) < -1.4:
            return True
        if isinstance(max_no_speech_prob, (int, float)) and float(max_no_speech_prob) > 0.75:
            return True
        return False
