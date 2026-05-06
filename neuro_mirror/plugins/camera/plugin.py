from __future__ import annotations

import asyncio
import time
from typing import Any

from neuro_mirror.core.settings import Settings
from neuro_mirror.core.worker_client import WorkerClient
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics


class CameraPlugin(ProcessorPlugin):
    plugin_name = "camera"

    def __init__(self, bus, *, settings: Settings) -> None:
        super().__init__(bus)
        self.settings = settings
        self.worker = WorkerClient(
            name="camera_worker",
            python_executable=settings.vision_worker_python,
            script_path=settings.vision_worker_script,
            request_timeout_seconds=settings.worker_request_timeout_seconds,
        )
        self._preview_task: asyncio.Task[None] | None = None
        self._preview_enabled = False
        self._last_preview_status: dict[str, Any] = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.UI_ACTION, Topics.START_CAPTURE)

    async def on_start(self) -> None:
        self._preview_enabled = False
        self._preview_task = asyncio.create_task(self._preview_loop(), name="camera-preview-loop")

    async def on_stop(self) -> None:
        self._preview_enabled = False
        if self._preview_task is not None:
            self._preview_task.cancel()
            try:
                await self._preview_task
            except asyncio.CancelledError:
                pass
            self._preview_task = None
        await self.worker.stop()

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.UI_ACTION:
            await self._handle_ui_action(event.payload)
            return

        if event.topic == Topics.START_CAPTURE:
            await self._capture_for_session(event.payload)

    async def _handle_ui_action(self, payload: dict[str, Any]) -> None:
        action = str(payload.get("action") or "")
        if action == "start_preview":
            await self._ensure_worker_started()
            self._preview_enabled = True
            await self._publish_status_message("Предпросмотр камеры включён.")
            return

        if action == "stop_preview":
            self._preview_enabled = False
            await self._release_worker_camera()
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "preview_image_base64": "",
                        "message": "Предпросмотр камеры остановлен.",
                        "assistant_source": "",
                        "screen": "idle",
                    },
                )
            )
            await self._publish_status_snapshot({"worker_available": True, "camera_available": False})
            return

        if action == "release_camera":
            self._preview_enabled = False
            await self._release_worker_camera()
            await self.worker.stop()
            await self._publish_status_snapshot({"worker_available": False, "camera_available": False})
            await self._publish_status_message("Backend-камера освобождена и worker остановлен.")

    async def _capture_for_session(self, payload: dict[str, Any]) -> None:
        mode = str(payload.get("mode") or "")
        await self._ensure_worker_started()
        try:
            response = await self.worker.request("capture_preview_frame")
        except Exception as exc:
            await self._publish_error_status(str(exc))
            await self.bus.publish(
                Event(
                    topic=Topics.SENSOR_VIDEO_FRAME,
                    source=self.name,
                    payload={**payload, "mode": mode, "image_base64": "", "error": str(exc)},
                )
            )
            return

        if not response.ok:
            await self._publish_error_status(response.error_message)
            await self.bus.publish(
                Event(
                    topic=Topics.SENSOR_VIDEO_FRAME,
                    source=self.name,
                    payload={
                        **payload,
                        "mode": mode,
                        "image_base64": "",
                        "error": response.error_message,
                    },
                )
            )
            return

        result = dict(response.result)
        await self._publish_status_snapshot(result)
        await self.bus.publish(
            Event(
                topic=Topics.SENSOR_VIDEO_FRAME,
                source=self.name,
                payload={
                    **payload,
                    "mode": mode,
                    "image_base64": result.get("image_base64", ""),
                    "camera_available": result.get("camera_available", False),
                    "camera_index": result.get("camera_index"),
                    "camera_backend": result.get("camera_backend"),
                    "camera_attempts": result.get("camera_attempts") or [],
                    "capture_ms": result.get("capture_ms"),
                    "encode_ms": result.get("encode_ms"),
                    "total_ms": result.get("total_ms"),
                },
            )
        )

        if not self._preview_enabled:
            await self._release_worker_camera()

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

    async def _release_worker_camera(self) -> None:
        try:
            await self.worker.request("release_camera")
        except Exception:
            pass

    async def _preview_loop(self) -> None:
        while True:
            if not self._preview_enabled:
                await asyncio.sleep(self.settings.preview_interval_seconds)
                continue

            try:
                request_started_at = time.perf_counter()
                response = await self.worker.request("capture_preview_frame")
                roundtrip_ms = round((time.perf_counter() - request_started_at) * 1000, 1)
            except Exception as exc:
                await self._publish_error_status(str(exc))
                await asyncio.sleep(self.settings.preview_interval_seconds)
                continue

            if not response.ok:
                await self._publish_error_status(response.error_message)
                await asyncio.sleep(self.settings.preview_interval_seconds)
                continue

            status_result = {
                "camera_available": response.result.get("camera_available", False),
                "worker_available": True,
                "camera_index": response.result.get("camera_index"),
                "camera_backend": response.result.get("camera_backend"),
                "capture_ms": response.result.get("capture_ms"),
                "encode_ms": response.result.get("encode_ms"),
                "total_ms": response.result.get("total_ms"),
                "roundtrip_ms": roundtrip_ms,
            }
            if status_result != self._last_preview_status:
                self._last_preview_status = dict(status_result)
                await self._publish_status_snapshot(status_result)
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "preview_image_base64": response.result.get("image_base64", ""),
                    },
                )
            )
            await asyncio.sleep(self.settings.preview_interval_seconds)

    async def _publish_status_message(self, message: str) -> None:
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={"message": message, "assistant_source": "", "screen": "idle"},
            )
        )

    async def _publish_error_status(self, error_message: str) -> None:
        status = {
            "camera": {
                "available": False,
                "detail": f"Камера недоступна: {error_message}" if error_message else "Камера недоступна",
            },
        }
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "worker_statuses": status,
                    "message": f"Камера недоступна: {error_message}",
                },
            )
        )

    async def _publish_status_snapshot(self, raw_result: dict[str, Any]) -> None:
        camera_available = bool(raw_result.get("camera_available", False))
        camera_detail = "Камера активна"
        if not camera_available:
            attempts = raw_result.get("camera_attempts") or []
            camera_detail = (
                f"Камера не найдена. Проверено: {', '.join(map(str, attempts[:6]))}"
                if attempts
                else "Камера недоступна"
            )
        else:
            used_backend = raw_result.get("camera_backend")
            used_index = raw_result.get("camera_index")
            metrics: list[str] = []
            for key, label in (
                ("capture_ms", "capture"),
                ("encode_ms", "encode"),
                ("total_ms", "worker"),
                ("roundtrip_ms", "roundtrip"),
            ):
                if raw_result.get(key) is not None:
                    metrics.append(f"{label} {raw_result.get(key)} мс")
            if used_backend not in {None, ""} and used_index is not None:
                camera_detail = f"Камера активна ({used_backend}:{used_index})"
            if metrics:
                camera_detail = f"{camera_detail}; {'; '.join(metrics)}"

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "worker_statuses": {
                        "camera": {
                            "available": camera_available,
                            "detail": camera_detail,
                        }
                    }
                },
            )
        )
