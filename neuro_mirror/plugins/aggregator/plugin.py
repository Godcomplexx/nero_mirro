from __future__ import annotations

from enum import Enum
from typing import Any

from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.appearance_response import AppearanceResponseComposer


class SessionState(str, Enum):
    IDLE = "idle"
    SCREENING = "screening"
    APPEARANCE = "appearance"
    REPORTING = "reporting"


IGNORED_UI_ACTIONS = {
    "start_preview",
    "stop_preview",
    "release_camera",
    "start_voice_capture",
    "stop_voice_capture",
}


class AggregatorPlugin(ProcessorPlugin):
    plugin_name = "aggregator"

    def __init__(self, bus, *, appearance_composer: AppearanceResponseComposer) -> None:
        super().__init__(bus)
        self.appearance_composer = appearance_composer
        self.state = SessionState.IDLE
        self.history_count = 0
        self._latest_results: dict[str, dict[str, Any]] = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            Topics.SYSTEM_BOOTSTRAP,
            Topics.UI_ACTION,
            Topics.AI_COMMAND,
            Topics.ANALYSIS_RESULT,
            Topics.VOICE_TEST_RESULT,
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

        if event.topic == Topics.ANALYSIS_RESULT:
            if self.state == SessionState.APPEARANCE:
                await self._finish_appearance_analysis(event.payload)
                return

            self._latest_results["video"] = event.payload
            await self._maybe_finish_screening()
            return

        if event.topic == Topics.VOICE_TEST_RESULT:
            self._latest_results["voice"] = event.payload
            await self._maybe_finish_screening()

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

        if action == "analyze_appearance":
            await self._start_appearance_analysis()
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

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "screening",
                    "message": "Скрининг запущен.",
                    "history_count": self.history_count,
                    "assistant_source": "скрининг",
                },
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.START_CAPTURE,
                source=self.name,
                payload={"mode": "daily_fast"},
            )
        )
        await self.bus.publish(
            Event(
                topic=Topics.START_TEST,
                source=self.name,
                payload={"test_id": "speech_baseline"},
            )
        )

    async def _start_appearance_analysis(self) -> None:
        self.state = SessionState.APPEARANCE
        self._latest_results.clear()

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
                topic=Topics.START_CAPTURE,
                source=self.name,
                payload={"mode": "appearance_check"},
            )
        )

    async def _finish_appearance_analysis(self, payload: dict[str, Any]) -> None:
        self.state = SessionState.REPORTING
        response_text = await self.appearance_composer.compose(payload)
        report_payload = {
            "report_type": "appearance",
            "state": "completed",
            "compliment": response_text,
            "observed": payload.get("observed") or "",
            "appearance_description": payload.get("appearance_description") or "",
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
        if self.state != SessionState.SCREENING:
            return

        if "video" not in self._latest_results or "voice" not in self._latest_results:
            return

        self.state = SessionState.REPORTING

        report_payload = {
            "report_type": "screening",
            "state": "needs_review",
            "domains": {
                "attention": self._latest_results["video"].get("attention_score"),
                "speech": self._latest_results["voice"].get("speech_score"),
                "reaction": self._latest_results["voice"].get("reaction_ms"),
            },
            "sources": self._latest_results,
        }

        await self.bus.publish(Event(topic=Topics.REPORT_DATA, source=self.name, payload=report_payload))
        await self.bus.publish(Event(topic=Topics.STORAGE_WRITE, source=self.name, payload=report_payload))
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "summary",
                    "message": "Скрининг завершён.",
                    "report": report_payload,
                    "assistant_source": "скрининг",
                },
            )
        )

        self.state = SessionState.IDLE
