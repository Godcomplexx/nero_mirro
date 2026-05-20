from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.appearance_response import AppearanceResponseComposer


logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    IDLE = "idle"
    SCREENING = "screening"
    MOCA = "moca"
    APPEARANCE = "appearance"
    REPORTING = "reporting"


IGNORED_UI_ACTIONS = {
    "start_preview",
    "stop_preview",
    "release_camera",
    "start_voice_capture",
    "stop_voice_capture",
    "moca_tts_finished",
    "analyze_appearance",  # handled entirely by the browser via /api/appearance/analyze
    "camera_vision_query",  # handled entirely by the browser via /api/assistant/camera-vision
}


class AggregatorPlugin(ProcessorPlugin):
    plugin_name = "aggregator"

    def __init__(self, bus, *, appearance_composer: AppearanceResponseComposer) -> None:
        super().__init__(bus)
        self.appearance_composer = appearance_composer
        self.state = SessionState.IDLE
        self.history_count = 0
        self._latest_results: dict[str, dict[str, Any]] = {}
        self._pending_capture_mode = ""

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            Topics.SYSTEM_BOOTSTRAP,
            Topics.UI_ACTION,
            Topics.AI_COMMAND,
            Topics.DEVICE_SELECTION_RESOLVED,
            Topics.DEVICE_VALIDATION_FAILED,
            Topics.ANALYSIS_RESULT,
            Topics.RPPG_RESULT,
            Topics.VOICE_TEST_RESULT,
            Topics.MOCA_TEST_RESULT,
            Topics.STORAGE_READ_RESULT,
        )

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.SYSTEM_BOOTSTRAP:
            await self._handle_bootstrap()
            return

        if event.topic == Topics.STORAGE_READ_RESULT:
            self.history_count = len(event.payload.get("items", []))
            return

        if event.topic in {Topics.UI_ACTION, Topics.AI_COMMAND}:
            await self._handle_action(event.payload)
            return

        if event.topic == Topics.DEVICE_SELECTION_RESOLVED:
            await self._handle_devices_resolved(event.payload)
            return

        if event.topic == Topics.DEVICE_VALIDATION_FAILED:
            await self._handle_device_validation_failed(event.payload)
            return

        if event.topic == Topics.RPPG_RESULT:
            if self.state == SessionState.SCREENING:
                self._latest_results["video"] = event.payload
                await self._maybe_finish_screening()
            return

        if event.topic == Topics.ANALYSIS_RESULT:
            if self.state == SessionState.APPEARANCE:
                await self._finish_appearance_analysis(event.payload)
            return

        if event.topic == Topics.VOICE_TEST_RESULT:
            self._latest_results["voice"] = event.payload
            await self._maybe_finish_screening()
            return

        if event.topic == Topics.MOCA_TEST_RESULT:
            self._latest_results["moca"] = event.payload
            await self._finish_moca()

    async def _handle_bootstrap(self) -> None:
        await self.bus.publish(
            Event(
                topic=Topics.STORAGE_READ,
                source=self.name,
                payload={"collection": "screenings"},
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "idle",
                    "message": "Система готова. Ожидаю запуск скрининга или вопрос к ассистенту.",
                },
            )
        )

    async def _handle_action(self, payload: dict[str, Any]) -> None:
        action = str(payload.get("action") or payload.get("command") or "")
        if not action:
            return

        if action in IGNORED_UI_ACTIONS:
            return

        if action == "start_screening":
            await self._start_screening()
            return

        if action == "stop_moca":
            await self.bus.publish(Event(topic=Topics.MOCA_STOP, source=self.name, payload={}))
            self.state = SessionState.IDLE
            await self.bus.publish(Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={"screen": "idle", "message": "Тест MoCA прерван."},
            ))
            return

        if action == "measure_pulse":
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "screen": "idle",
                        "message": "Запускаю мониторинг пульса (~5 мин). Держите лицо перед камерой.",
                        "assistant_source": "пульс",
                        "pulse_monitor_start": True,
                        "pulse_monitor_duration": 300,
                    },
                )
            )
            return

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "idle",
                    "message": f"Неподдерживаемая команда: {action!r}",
                },
            )
        )

    async def _start_screening(self) -> None:
        self.state = SessionState.SCREENING
        self._latest_results.clear()
        self._pending_capture_mode = ""

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "screening",
                    "message": "Скрининг запущен. Держите лицо перед камерой (~20 сек).",
                    "history_count": self.history_count,
                    "assistant_source": "скрининг",
                },
            )
        )
        # Screening now uses browser-side frame capture via /ws/rppg WebSocket.
        # No camera worker capture is triggered here.

    async def _start_appearance_analysis(self) -> None:
        self.state = SessionState.APPEARANCE
        self._latest_results.clear()
        self._pending_capture_mode = "appearance_check"

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "assistant",
                    "message": "Смотрю в камеру и оцениваю внешний вид.",
                    "assistant_source": "визуальный анализ",
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.PREPARE_SESSION,
                source=self.name,
                payload={"mode": "appearance_check", "require_microphone": False},
            )
        )

    async def _handle_devices_resolved(self, payload: dict[str, Any]) -> None:
        mode = str(payload.get("mode") or self._pending_capture_mode)
        if not mode:
            return

        await self.bus.publish(
            Event(
                topic=Topics.START_CAPTURE,
                source=self.name,
                payload={
                    "mode": mode,
                    "selected_devices": payload.get("selected_devices") or {},
                },
            )
        )

        # Voice baseline test is no longer launched here —
        # MoCA is started after face scan completes (see _maybe_finish_screening)

        self._pending_capture_mode = ""

    async def _handle_device_validation_failed(self, payload: dict[str, Any]) -> None:
        errors = payload.get("errors") or []
        logger.warning(
            "Device validation failed during %s: %s",
            self._pending_capture_mode or self.state,
            "; ".join(map(str, errors)) or "unknown error",
        )
        if not self._pending_capture_mode:
            self.state = SessionState.IDLE

    async def _finish_appearance_analysis(self, payload: dict[str, Any]) -> None:
        self.state = SessionState.REPORTING
        response_text = await self.appearance_composer.compose(payload)
        report_payload = {
            "report_type": "appearance",
            "state": "completed",
            "compliment": response_text,
            "observed": payload.get("observed") or "",
            "appearance_description": payload.get("appearance_description") or "",
            "appearance_checklist": payload.get("appearance_checklist") or {},
            "appearance_memory_notes": payload.get("appearance_memory_notes") or "",
            "wellness_suggestion": payload.get("wellness_suggestion") or "",
            "suggestion": "Можно повторить анализ после изменения света или положения камеры.",
            "face_detected": payload.get("face_detected"),
            "face_count": payload.get("face_count"),
            "confidence": payload.get("confidence"),
            "emotion": payload.get("emotion") or "",
            "estimated_age": payload.get("estimated_age"),
            "estimated_gender": payload.get("estimated_gender") or "",
            "emotiefflib_available": payload.get("emotiefflib_available"),
            "notes": payload.get("notes") or "",
            "source_backend": payload.get("source_backend") or "vision_worker",
        }

        await self.bus.publish(Event(topic=Topics.REPORT_DATA, source=self.name, payload=report_payload))
        await self.bus.publish(Event(topic=Topics.STORAGE_WRITE, source=self.name, payload=report_payload))
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "summary",
                    "message": response_text,
                    "report": report_payload,
                    "assistant_source": "визуальный анализ",
                },
            )
        )

        self.state = SessionState.IDLE

    async def _maybe_finish_screening(self) -> None:
        """Called when face scan result arrives — show heart rate, then launch MoCA."""
        import asyncio
        if self.state != SessionState.SCREENING:
            logger.info("[aggregator] _maybe_finish_screening skipped: state=%s", self.state)
            return
        if "video" not in self._latest_results:
            logger.info("[aggregator] _maybe_finish_screening skipped: no video result yet")
            return

        # Guard against double-entry (e.g. second ANALYSIS_RESULT arriving during sleep)
        self.state = SessionState.MOCA

        video = self._latest_results["video"]
        hr_bpm = video.get("heart_rate_bpm")
        hr_status = video.get("heart_rate_status", "unavailable")
        hr_algo = video.get("heart_rate_algorithm", "")
        logger.info(
            "[aggregator] screening done: heart_rate_bpm=%s status=%s algo=%s video_keys=%s",
            hr_bpm, hr_status, hr_algo, list(video.keys()),
        )

        if hr_bpm is not None:
            hr_line = f"Пульс: {hr_bpm} уд/мин ({hr_algo})."
        elif hr_status == "disabled":
            hr_line = "Измерение пульса отключено."
        else:
            hr_line = "Пульс не удалось измерить."

        # Show heart rate result on screening screen before switching to MoCA
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "screening",
                    "message": (
                        f"Видео-скрининг завершён. {hr_line} "
                        "Через несколько секунд начнётся голосовой тест MoCA."
                    ),
                    "heart_rate_bpm": hr_bpm,
                    "heart_rate_status": hr_status,
                    "heart_rate_algorithm": hr_algo,
                    "assistant_source": "скрининг",
                },
            )
        )

        # Give the patient 4 seconds to see the heart rate result
        await asyncio.sleep(4.0)

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "moca",
                    "message": (
                        "Скрининг лица завершён. "
                        "Сейчас начнётся голосовой тест — следуйте инструкциям."
                    ),
                    "moca_task_index": 0,
                    "moca_task_total": 11,
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.MOCA_START,
                source=self.name,
                payload={},
            )
        )

    async def _finish_moca(self) -> None:
        """Called when MoCA test result arrives — compile and publish final report."""
        if self.state != SessionState.MOCA:
            return

        self.state = SessionState.REPORTING

        video = self._latest_results.get("video", {})
        moca = self._latest_results.get("moca", {})

        report_payload = {
            "report_type": "screening",
            "state": "needs_review",
            "domains": {
                "attention": video.get("attention_score"),
                "gaze": video.get("gaze_stability"),
                "heart_rate_bpm": video.get("heart_rate_bpm"),
                "heart_rate_status": video.get("heart_rate_status"),
                "heart_rate_algorithm": video.get("heart_rate_algorithm"),
                "moca_score": moca.get("score"),
                "moca_max_score": moca.get("max_score"),
                "moca_percent": moca.get("percent"),
                "moca_tasks": moca.get("tasks", []),
                "moca_task_count": moca.get("task_count", 0),
            },
            "summary": {
                "moca_interpretation": moca.get("interpretation", ""),
                "moca_notes": moca.get("notes", ""),
            },
            "sources": {
                "video": video,
                "moca": moca,
            },
        }

        await self.bus.publish(Event(topic=Topics.REPORT_DATA, source=self.name, payload=report_payload))
        await self.bus.publish(Event(topic=Topics.STORAGE_WRITE, source=self.name, payload=report_payload))
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "summary",
                    "message": "Скрининг завершён. Все задания выполнены.",
                    "report": report_payload,
                    "assistant_source": "скрининг MoCA",
                },
            )
        )

        self.state = SessionState.IDLE
