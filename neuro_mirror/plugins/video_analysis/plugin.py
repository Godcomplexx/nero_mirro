from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib import error, request

import asyncio
import logging

from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task_sync
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.worker_client import WorkerClient
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.appearance_response import AppearanceResponseComposer
from neuro_mirror.screening.video_analyzer import analyze_frames
from neuro_mirror.utils.text import is_safe_russian_text

logger = logging.getLogger(__name__)


class VisionWorkerPlugin(ProcessorPlugin):
    plugin_name = "video_analysis"

    def __init__(
        self,
        bus,
        *,
        settings: Settings,
        appearance_composer: AppearanceResponseComposer | None = None,
    ) -> None:
        super().__init__(bus)
        self.settings = settings
        self.appearance_composer = appearance_composer
        self.worker = WorkerClient(
            name="vision_worker",
            python_executable=settings.vision_worker_python,
            script_path=settings.vision_worker_script,
            request_timeout_seconds=settings.worker_request_timeout_seconds,
        )
        self._last_status: dict[str, Any] = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.SENSOR_VIDEO_FRAME, Topics.REQ_APPEARANCE_ANALYZE)

    async def on_start(self) -> None:
        return None

    async def on_stop(self) -> None:
        await self.worker.stop()

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.REQ_APPEARANCE_ANALYZE:
            await self._handle_req_appearance(event)
            return

        if event.topic == Topics.SENSOR_VIDEO_FRAME:
            await self._handle_capture(event.payload)

    # ---- request-reply: appearance analysis for web layer ----

    async def _handle_req_appearance(self, event: Event) -> None:
        request_id = event.payload.get("_request_id", "")
        image_path = str(event.payload.get("image_path") or "")
        if not image_path:
            await self._send_reply(request_id, {"error": "image_path is empty"})
            return

        await self._ensure_worker_started()
        try:
            response = await self.worker.request("analyze_image_file", {"image_path": image_path})
        except Exception as exc:
            await self._send_reply(request_id, {"error": str(exc)})
            return

        if not response.ok:
            await self._send_reply(request_id, {"error": response.error_message})
            return

        result = dict(response.result, source_backend="vision_worker:web")
        # Keep frame_base64 in result so AppearanceResponseComposer can use
        # its full 3-stage pipeline (Vision EN → translate RU → polish)
        # instead of the simpler _call_ollama_vision_sync prompt.

        reply_text = ""
        if self.appearance_composer:
            reply_text = await self.appearance_composer.compose(result)
            if not is_safe_russian_text(reply_text):
                result["appearance_description"] = ""
                reply_text = self.appearance_composer._build_template(result)
            if not result.get("appearance_description"):
                vision_status = str(result.get("vision_status") or "").strip()
                note = "Детальное vision-описание всего кадра не получено; видимые детали не выдумывались."
                if vision_status:
                    note = f"{note} Статус vision: {vision_status}."
                existing_notes = str(result.get("notes") or "").strip()
                result["notes"] = f"{existing_notes} {note}".strip()
            # Remove heavy field before publishing
            result.pop("frame_base64", None)

        report_payload = {
            "report_type": "appearance",
            "state": "completed",
            "compliment": reply_text,
            "observed": result.get("observed") or "",
            "suggestion": "Если описание не появилось, проверь доступность Ollama и установленную vision-модель.",
            "face_detected": result.get("face_detected"),
            "face_count": result.get("face_count"),
            "confidence": result.get("confidence"),
            "emotion": result.get("emotion") or "",
            "appearance_description": result.get("appearance_description") or "",
            "appearance_checklist": result.get("appearance_checklist") or {},
            "appearance_memory_notes": result.get("appearance_memory_notes") or "",
            "wellness_suggestion": result.get("wellness_suggestion") or "",
            "vision_status": result.get("vision_status") or "",
            "emotiefflib_available": result.get("emotiefflib_available"),
            "notes": result.get("notes") or "",
            "source_backend": result.get("source_backend") or "vision_worker:web",
        }

        await self.bus.publish(Event(topic=Topics.REPORT_DATA, source="web.appearance", payload=report_payload))
        await self.bus.publish(Event(topic=Topics.STORAGE_WRITE, source="web.appearance", payload=report_payload))
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "summary",
                    "message": reply_text,
                    "assistant_source": "визуальный анализ",
                    "report": report_payload,
                },
            )
        )
        await self._send_reply(request_id, {"reply": reply_text, "report": report_payload})

    async def _send_reply(self, request_id: str, payload: dict[str, Any]) -> None:
        payload["_reply_to"] = request_id
        await self.bus.publish(
            Event(topic=Topics.RESP_APPEARANCE_ANALYZE, source=self.name, payload=payload)
        )

    # ---- original internal logic (SENSOR_VIDEO_FRAME) ----

    async def _handle_capture(self, payload: dict[str, Any]) -> None:
        mode = str(payload.get("mode") or "")
        frame_base64 = str(payload.get("image_base64") or "").strip()
        if not frame_base64:
            await self._publish_video_failure(mode, str(payload.get("error") or "Кадр камеры не получен."))
            return

        await self._ensure_worker_started()
        image_path = self._write_frame_to_temp_file(frame_base64)
        try:
            response = await self.worker.request("analyze_image_file", {"image_path": image_path})
        finally:
            try:
                Path(image_path).unlink(missing_ok=True)
            except Exception:
                pass

        if mode == "appearance_check":
            if response.ok:
                result = dict(response.result, source_backend="vision_worker")
                # Let AppearanceResponseComposer handle the full Vision pipeline
                # (frame_base64 stays in result for the 3-stage EN→RU→polish flow)

                await self.bus.publish(
                    Event(
                        topic=Topics.ANALYSIS_RESULT,
                        source=self.name,
                        payload=result,
                    )
                )
                await self._publish_status_snapshot(response.result)
                return

            await self.bus.publish(
                Event(
                    topic=Topics.ANALYSIS_RESULT,
                    source=self.name,
                    payload={
                        "analysis_type": "appearance",
                        "face_detected": False,
                        "face_count": 0,
                        "emotiefflib_available": False,
                        "confidence": 0.0,
                        "emotion": "",
                        "appearance_description": "",
                        "observed": "",
                        "notes": f"Vision worker error: {response.error_message}",
                        "source_backend": "vision_worker",
                    },
                )
            )
            await self._publish_error_status(response.error_message)
            return

        if response.ok:
            raw = dict(response.result)
            await self._publish_status_snapshot(raw)

            # Run real screening analysis on the frame
            try:
                frame_data = base64.b64decode(frame_base64) if frame_base64 else b""
                video_result = await asyncio.to_thread(analyze_frames, [frame_data] if frame_data else [])
                logger.info(
                    "screening video analysis: attention=%.2f gaze=%.2f face=%s",
                    video_result.attention_score,
                    video_result.gaze_stability,
                    video_result.face_detected,
                )
            except Exception as exc:
                logger.exception("screening video analysis failed, using fallback")
                from neuro_mirror.screening.video_analyzer import VideoAnalysisResult
                video_result = VideoAnalysisResult(
                    attention_score=0.5,
                    face_detected=bool(raw.get("face_detected", False)),
                    face_count=int(raw.get("face_count") or 0),
                    notes=f"Fallback из-за ошибки анализа: {exc}",
                )

            await self.bus.publish(
                Event(
                    topic=Topics.ANALYSIS_RESULT,
                    source=self.name,
                    payload={
                        "analysis_type": "screening",
                        "attention_score": video_result.attention_score,
                        "gaze_stability": video_result.gaze_stability,
                        "micro_expression_flags": list(video_result.micro_expression_flags),
                        "face_detected": video_result.face_detected,
                        "face_count": video_result.face_count,
                        "notes": video_result.notes or raw.get("notes") or "",
                        "source_backend": "vision_worker + screening_analyzer",
                    },
                )
            )
            return

        await self.bus.publish(
            Event(
                topic=Topics.ANALYSIS_RESULT,
                source=self.name,
                payload={
                    "analysis_type": "screening",
                    "attention_score": 0.0,
                    "gaze_stability": 0.0,
                    "micro_expression_flags": [],
                    "face_detected": False,
                    "face_count": 0,
                    "notes": f"Vision worker error: {response.error_message}",
                    "source_backend": "vision_worker",
                },
            )
        )
        await self._publish_error_status(response.error_message)

    async def _publish_video_failure(self, mode: str, message: str) -> None:
        analysis_type = "appearance" if mode == "appearance_check" else "screening"
        payload: dict[str, Any]
        if analysis_type == "appearance":
            payload = {
                "analysis_type": "appearance",
                "face_detected": False,
                "face_count": 0,
                "emotiefflib_available": False,
                "confidence": 0.0,
                "emotion": "",
                "appearance_description": "",
                "observed": "",
                "notes": message,
                "source_backend": "camera",
            }
        else:
            payload = {
                "analysis_type": "screening",
                "attention_score": 0.25,
                "face_detected": False,
                "face_count": 0,
                "notes": message,
                "source_backend": "camera",
            }
        await self.bus.publish(Event(topic=Topics.ANALYSIS_RESULT, source=self.name, payload=payload))
        await self._publish_error_status(message)

    @staticmethod
    def _write_frame_to_temp_file(frame_base64: str) -> str:
        data = base64.b64decode(frame_base64)
        fd, temp_path = tempfile.mkstemp(prefix="neuro_mirror_sensor_frame_", suffix=".png")
        os.close(fd)
        with open(temp_path, "wb") as output_file:
            output_file.write(data)
        return temp_path

    async def _ensure_worker_started(self) -> None:
        try:
            await self.worker.start()
            response = await self.worker.request("health")
            if response.ok:
                await self._publish_status_snapshot(response.result)
                return
            await self._publish_error_status(response.error_message)
        except Exception as exc:
            await self._publish_error_status(str(exc))

    async def _publish_error_status(self, error_message: str) -> None:
        status = {
            "vision_worker": {
                "available": False,
                "detail": error_message,
            },
            "emotiefflib": {
                "available": False,
                "detail": f"EmotiEffLib недоступен: {error_message}" if error_message else "EmotiEffLib недоступен",
            },
        }
        self._last_status = status
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "worker_statuses": status,
                    "message": f"Vision worker недоступен: {error_message}",
                },
            )
        )

    async def _publish_status_snapshot(self, raw_result: dict[str, Any]) -> None:
        status = {
            "vision_worker": {
                "available": bool(raw_result.get("worker_available", True)),
                "detail": "Vision worker активен",
            },
            "emotiefflib": {
                "available": bool(raw_result.get("emotiefflib_available", False)),
                "detail": (
                    (
                        f"EmotiEffLib доступен ({raw_result.get('emotion_model_name') or 'emotion-model'}, "
                        f"{raw_result.get('emotion_engine') or 'engine'})"
                    )
                    if raw_result.get("emotiefflib_available", False)
                    else (
                        f"EmotiEffLib недоступен: {raw_result.get('emotiefflib_error')}"
                        if raw_result.get("emotiefflib_error")
                        else "EmotiEffLib недоступен"
                    )
                ),
                "error": str(raw_result.get("emotiefflib_error") or ""),
            },
        }
        self._last_status = status
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={"worker_statuses": status},
            )
        )

    def _call_ollama_vision_sync(self, image_base64: str) -> str:
        """Send frame to Ollama Vision model, return text description."""
        ollama_url = self.settings.ollama_base_url.rstrip("/")
        model = self.settings.ollama_vision_model or self.settings.ollama_model
        payload = {
            "model": model,
            "prompt": (
                "Опиши внешность человека на фото на русском, 4-6 предложений.\n"
                "Обязательно отметь (если видно):\n"
                "- Общее впечатление и атмосферу (уверенность, лёгкость, спокойствие)\n"
                "- Лицо и взгляд\n"
                "- Волосы — стиль, как уложены, как дополняют образ\n"
                "- Одежда — стиль, цвета, что подчёркивает\n"
                "- Аксессуары — очки, украшения, часы и т.д.\n"
                "Тон: тёплый и доброжелательный, как комплимент от подруги.\n"
                "Не ставь диагнозов. Не упоминай качество фото или камеру."
            ),
            "images": [image_base64],
            "stream": False,
            "options": {"temperature": 0.35, "num_predict": 300},
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{ollama_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with exclusive_gpu_task_sync("ollama"):
                with request.urlopen(req, timeout=self.settings.ollama_timeout_seconds) as resp:
                    raw_body = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {error_body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Ollama недоступен: {exc.reason}") from exc

        parsed = json.loads(raw_body)
        if "error" in parsed:
            raise RuntimeError(f"Ollama: {parsed['error']}")
        return str(parsed.get("response", "")).strip()

    # _sanitize_vision_description and _is_safe_russian_text
    # are now in neuro_mirror.utils.text (shared module)
