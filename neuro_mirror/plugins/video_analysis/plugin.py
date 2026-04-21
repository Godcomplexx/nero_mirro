from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any
from urllib import error, request

from neuro_mirror.core.gpu_scheduler import exclusive_gpu_task_sync
from neuro_mirror.core.settings import Settings
from neuro_mirror.core.worker_client import WorkerClient
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics


class VisionWorkerPlugin(ProcessorPlugin):
    plugin_name = "video_analysis"

    def __init__(self, bus, *, settings: Settings) -> None:
        super().__init__(bus)
        self.settings = settings
        self.worker = WorkerClient(
            name="vision_worker",
            python_executable=settings.vision_worker_python,
            script_path=settings.vision_worker_script,
            request_timeout_seconds=settings.worker_request_timeout_seconds,
        )
        self._preview_task: asyncio.Task[None] | None = None
        self._preview_enabled = False
        self._last_status: dict[str, Any] = {}
        self._last_preview_status: dict[str, Any] = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.UI_ACTION, Topics.START_CAPTURE)

    async def on_start(self) -> None:
        self._preview_enabled = False
        self._preview_task = asyncio.create_task(self._preview_loop(), name="vision-preview-loop")

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
            await self._handle_capture(event.payload)

    async def _handle_ui_action(self, payload: dict[str, Any]) -> None:
        action = str(payload.get("action") or "")
        if action == "start_preview":
            await self._ensure_worker_started()
            self._preview_enabled = True
            await self._publish_status_message("Предпросмотр камеры включён.")
            return

        if action == "stop_preview":
            self._preview_enabled = False
            try:
                await self.worker.request("release_camera")
            except Exception:
                pass
            await self.worker.stop()
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
            try:
                await self.worker.request("release_camera")
            except Exception:
                pass
            await self.worker.stop()
            await self._publish_status_snapshot({"worker_available": False, "camera_available": False})
            await self._publish_status_message("Backend-камера освобождена и worker остановлен.")
            return

    async def _handle_capture(self, payload: dict[str, Any]) -> None:
        mode = str(payload.get("mode") or "")
        await self._ensure_worker_started()

        if mode == "appearance_check":
            response = await self.worker.request("analyze_appearance")
            if response.ok:
                result = dict(response.result, source_backend="vision_worker")
                # Call Ollama Vision outside worker lock so preview keeps running
                frame_b64 = result.pop("frame_base64", "")
                if frame_b64:
                    try:
                        desc = await asyncio.to_thread(
                            self._call_ollama_vision_sync, frame_b64
                        )
                        desc = self._sanitize_vision_description(desc)
                        result["appearance_description"] = desc
                        observed = result.get("observed", "")
                        if desc:
                            result["observed"] = f"{observed} {desc}".strip()
                    except Exception as exc:
                        notes = result.get("notes", "")
                        result["notes"] = f"{notes} Ollama Vision: {exc}".strip()
                        result["appearance_description"] = ""
                else:
                    result["appearance_description"] = ""

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

        response = await self.worker.request("analyze_screening")
        if response.ok:
            await self.bus.publish(
                Event(
                    topic=Topics.ANALYSIS_RESULT,
                    source=self.name,
                    payload=dict(response.result, source_backend="vision_worker"),
                )
            )
            await self._publish_status_snapshot(response.result)
            return

        await self.bus.publish(
            Event(
                topic=Topics.ANALYSIS_RESULT,
                source=self.name,
                payload={
                    "analysis_type": "screening",
                    "attention_score": 0.25,
                    "face_detected": False,
                    "face_count": 0,
                    "notes": f"Vision worker error: {response.error_message}",
                    "source_backend": "vision_worker",
                },
            )
        )
        await self._publish_error_status(response.error_message)

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
            emotion_status = self._last_status.get("emotiefflib")
            if isinstance(emotion_status, dict):
                status_result["emotiefflib_available"] = bool(emotion_status.get("available", False))
                status_result["emotiefflib_error"] = str(emotion_status.get("error") or "")
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
            "vision_worker": {
                "available": False,
                "detail": error_message,
            },
            "camera": {
                "available": False,
                "detail": "Камера недоступна",
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
        camera_detail = "Камера активна"
        camera_available = bool(raw_result.get("camera_available", raw_result.get("face_detected", False)))
        if not camera_available:
            attempts = raw_result.get("camera_attempts") or []
            if attempts:
                camera_detail = f"Камера не найдена. Проверено: {', '.join(map(str, attempts[:6]))}"
            else:
                camera_detail = "Камера недоступна"
        else:
            used_backend = raw_result.get("camera_backend")
            used_index = raw_result.get("camera_index")
            capture_ms = raw_result.get("capture_ms")
            encode_ms = raw_result.get("encode_ms")
            total_ms = raw_result.get("total_ms")
            roundtrip_ms = raw_result.get("roundtrip_ms")
            if used_backend not in {None, ''} and used_index is not None:
                camera_detail = f"Камера активна ({used_backend}:{used_index})"
                metrics: list[str] = []
                if capture_ms is not None:
                    metrics.append(f"capture {capture_ms} мс")
                if encode_ms is not None:
                    metrics.append(f"encode {encode_ms} мс")
                if total_ms is not None:
                    metrics.append(f"worker {total_ms} мс")
                if roundtrip_ms is not None:
                    metrics.append(f"roundtrip {roundtrip_ms} мс")
                if metrics:
                    camera_detail = f"{camera_detail}; {'; '.join(metrics)}"

        status = {
            "vision_worker": {
                "available": bool(raw_result.get("worker_available", True)),
                "detail": "Vision worker активен",
            },
            "camera": {
                "available": camera_available,
                "detail": camera_detail,
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
                "Опиши внешность человека на фото кратко, 2-3 предложения на русском. "
                "Укажи примерный возраст, пол, общее впечатление. "
                "Не ставь диагнозов. Будь дружелюбным и тактичным."
            ),
            "images": [image_base64],
            "stream": False,
            "options": {"temperature": 0.3},
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

    @staticmethod
    def _sanitize_vision_description(text: str) -> str:
        cleaned = " ".join(str(text or "").strip().split())
        if not cleaned:
            return ""

        lowered = cleaned.lower()
        blocked_markers = (
            "i am a large language model",
            "cannot generate images",
            "не могу генерировать изображения",
            "disclaimer:",
        )
        if any(marker in lowered for marker in blocked_markers):
            return ""

        if len(cleaned) < 18:
            return ""

        if not VisionWorkerPlugin._is_safe_russian_text(cleaned):
            return ""

        return cleaned

    @staticmethod
    def _is_safe_russian_text(
        text: str,
        *,
        min_cyrillic_ratio: float = 0.82,
        max_foreign_tokens: int = 2,
    ) -> bool:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return False

        letters = [ch for ch in cleaned if ch.isalpha()]
        if not letters:
            return False

        cyrillic_letters = sum(1 for ch in letters if "\u0400" <= ch <= "\u04ff")
        if cyrillic_letters / len(letters) < min_cyrillic_ratio:
            return False

        foreign_tokens = 0
        for token in re.findall(r"[\w'-]+", cleaned, flags=re.UNICODE):
            token_letters = [ch for ch in token if ch.isalpha()]
            if len(token_letters) < 2:
                continue

            has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in token_letters)
            has_foreign = any(not ("\u0400" <= ch <= "\u04ff") for ch in token_letters)
            if has_cyrillic and has_foreign:
                return False
            if has_foreign:
                foreign_tokens += 1
                if foreign_tokens > max_foreign_tokens:
                    return False

        return True
