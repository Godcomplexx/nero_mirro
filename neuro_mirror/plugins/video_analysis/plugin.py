from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Any

import asyncio
import logging

from neuro_mirror.core.settings import Settings
from neuro_mirror.core.worker_client import WorkerClient
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.screening.video_analyzer import analyze_frames

logger = logging.getLogger(__name__)


class VisionWorkerPlugin(ProcessorPlugin):
    plugin_name = "video_analysis"

    def __init__(
        self,
        bus,
        *,
        settings: Settings,
    ) -> None:
        super().__init__(bus)
        self.settings = settings
        self.worker = WorkerClient(
            name="vision_worker",
            python_executable=settings.vision_worker_python,
            script_path=settings.vision_worker_script,
            request_timeout_seconds=settings.worker_request_timeout_seconds,
        )
        self._last_status: dict[str, Any] = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.SENSOR_VIDEO_FRAME,)

    async def on_start(self) -> None:
        return None

    async def on_stop(self) -> None:
        await self.worker.stop()

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.SENSOR_VIDEO_FRAME:
            await self._handle_capture(event.payload)

    # ---- original internal logic (SENSOR_VIDEO_FRAME) ----

    async def _handle_capture(self, payload: dict[str, Any]) -> None:
        mode = str(payload.get("mode") or "")
        analysis_result = payload.get("analysis_result")
        if isinstance(analysis_result, dict) and analysis_result:
            result = {
                "analysis_type": "screening",
                "source_backend": "vision_worker + rppg",
                **analysis_result,
            }
            await self._publish_status_snapshot(result)
            await self.bus.publish(
                Event(
                    topic=Topics.ANALYSIS_RESULT,
                    source=self.name,
                    payload=result,
                )
            )
            return

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


        if response.ok:
            raw = dict(response.result)
            await self._publish_status_snapshot(raw)

            # Run real screening analysis on the frame
            try:
                frame_data = base64.b64decode(frame_base64) if frame_base64 else b""
                video_result = await asyncio.to_thread(analyze_frames, [frame_data] if frame_data else [])
                logger.info(
                    "screening video analysis: face=%s ratio=%.3f issues=%s",
                    video_result.face_detected,
                    video_result.face_ratio,
                    ",".join(video_result.quality_issues) or "-",
                )
            except Exception as exc:
                logger.exception("screening video analysis failed, using fallback")
                from neuro_mirror.screening.video_analyzer import VideoAnalysisResult
                video_result = VideoAnalysisResult(
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
                        "face_detected": video_result.face_detected,
                        "face_count": video_result.face_count,
                        "face_ratio": video_result.face_ratio,
                        # События низкого качества учитываются при оценке
                        # достоверности результата — так требует задание.
                        "video_quality_issues": list(video_result.quality_issues),
                        "video_usable": video_result.usable,
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
                    "face_detected": False,
                    "face_count": 0,
                    "face_ratio": 0.0,
                    "video_quality_issues": ["worker_error"],
                    "video_usable": False,
                    "notes": f"Vision worker error: {response.error_message}",
                    "source_backend": "vision_worker",
                },
            )
        )
        await self._publish_error_status(response.error_message)

    async def _publish_video_failure(self, mode: str, message: str) -> None:
        payload: dict[str, Any] = {
            "analysis_type": "screening",
            "face_detected": False,
            "face_count": 0,
            "face_ratio": 0.0,
            "video_quality_issues": ["camera_error"],
            "video_usable": False,
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

