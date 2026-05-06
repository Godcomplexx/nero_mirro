from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from neuro_mirror.core.settings import Settings
from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task
from neuro_mirror.core.worker_client import WorkerClient
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.backends import normalize_user_utterance


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
        self._last_status: dict[str, Any] = {}
        self._warmup_task: asyncio.Task[None] | None = None

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.SENSOR_AUDIO_CHUNK, Topics.REQ_SPEECH_TRANSCRIBE)

    async def on_start(self) -> None:
        await self._ensure_worker_started()
        await self._publish_status_snapshot()
        self._warmup_task = asyncio.create_task(self._warmup_model(), name="speech-worker-warmup")

    async def on_stop(self) -> None:
        if self._warmup_task is not None:
            self._warmup_task.cancel()
            try:
                await self._warmup_task
            except asyncio.CancelledError:
                pass
            self._warmup_task = None
        await self.worker.stop()

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.REQ_SPEECH_TRANSCRIBE:
            await self._handle_req_transcribe(event)
            return

        audio_path = str(event.payload.get("audio_path") or "")
        if audio_path:
            await self._transcribe_audio_path(audio_path)

    # ---- request-reply: transcription for web layer ----

    async def _handle_req_transcribe(self, event: Event) -> None:
        request_id = event.payload.get("_request_id", "")
        audio_path = str(event.payload.get("audio_path") or "")
        if not audio_path:
            await self._send_reply(request_id, {"accepted": False, "transcript": "", "message": "audio_path is empty"})
            return

        transcribe_timeout = max(self.settings.worker_request_timeout_seconds, 120.0)
        stt_payload = self._build_stt_payload(audio_path)

        try:
            if self.settings.stt_device == "cpu":
                response = await asyncio.wait_for(
                    self.worker.request("transcribe_audio_file", stt_payload, timeout=transcribe_timeout),
                    timeout=transcribe_timeout + 5,
                )
            else:
                async with exclusive_gpu_task("stt"):
                    response = await asyncio.wait_for(
                        self.worker.request("transcribe_audio_file", stt_payload, timeout=transcribe_timeout),
                        timeout=transcribe_timeout + 5,
                    )
        except (TimeoutError, asyncio.TimeoutError):
            message = "Распознавание заняло слишком долго. Модель ещё загружается — попробуйте через 30 секунд."
            await self._publish_ui_message(message, transcript_text="")
            await self._send_reply(request_id, {"accepted": False, "transcript": "", "message": message})
            return
        except Exception as exc:
            message = f"Ошибка распознавания речи: {exc}"
            await self._publish_ui_message(message, transcript_text="")
            await self._send_reply(request_id, {"accepted": False, "transcript": "", "message": message})
            return

        if not response.ok:
            message = f"Ошибка распознавания речи: {response.error_message}"
            await self._publish_ui_message(message, transcript_text="")
            await self._send_reply(request_id, {"accepted": False, "transcript": "", "message": message})
            return

        result = response.result
        raw_transcript = str(result.get("transcript") or "").strip()

        if not raw_transcript:
            message = str(result.get("notes") or "Речь не распознана.")
            await self._publish_ui_message(message, transcript_text="")
            await self._send_reply(request_id, {"accepted": False, "transcript": "", "message": message})
            return

        transcript = normalize_user_utterance(raw_transcript) or raw_transcript

        if self._is_low_confidence_transcript(
            raw_transcript,
            confidence_score=result.get("confidence_score"),
            average_logprob=result.get("average_logprob"),
            max_no_speech_prob=result.get("max_no_speech_prob"),
        ):
            message = "Ещё раз сформулируйте вопрос: речь распознана неуверенно."
            await self._publish_ui_message(message, transcript_text=transcript)
            await self._send_reply(request_id, {
                "accepted": False,
                "transcript": transcript,
                "raw_transcript": raw_transcript,
                "message": message,
            })
            return

        await self._publish_ui_message(
            f"Распознан текст: {transcript}",
            transcript_text=transcript,
        )
        await self._send_reply(request_id, {
            "accepted": True,
            "transcript": transcript,
            "raw_transcript": raw_transcript,
            "notes": str(result.get("notes") or ""),
            "stt_device": str(result.get("device") or ""),
            "stt_model": str(result.get("model_name") or self.settings.stt_model_name),
            "stt_compute_type": str(result.get("compute_type") or ""),
        })

    async def _send_reply(self, request_id: str, payload: dict[str, Any]) -> None:
        payload["_reply_to"] = request_id
        await self.bus.publish(
            Event(topic=Topics.RESP_SPEECH_TRANSCRIBE, source=self.name, payload=payload)
        )

    async def _publish_ui_message(
        self,
        message: str,
        *,
        transcript_text: str | None = None,
    ) -> None:
        ui_payload: dict[str, Any] = {
            "screen": "assistant",
            "message": message,
            "assistant_source": "",
        }
        if transcript_text is not None:
            ui_payload["transcript_text"] = transcript_text
        await self.bus.publish(
            Event(topic=Topics.UI_UPDATE, source=self.name, payload=ui_payload)
        )

    # ---- original internal logic (SENSOR_AUDIO_CHUNK) ----

    async def _ensure_worker_started(self) -> None:
        try:
            await self.worker.start()
            await self.worker.request("health")
        except Exception:
            pass

    def _build_stt_payload(self, audio_path: str) -> dict[str, Any]:
        return {
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

    async def _transcribe_audio_path(self, audio_path: str) -> None:
        payload = self._build_stt_payload(audio_path)
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
                        "assistant_source": "",
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
                        "assistant_source": "",
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
                    "assistant_source": "",
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
