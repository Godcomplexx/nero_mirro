from __future__ import annotations

import asyncio
from typing import Any

from neuro_mirror.core.settings import Settings
from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.backends import (
    AssistantBackend,
    AssistantDecision,
    OllamaAssistantBackend,
    RuleBasedAssistantBackend,
    detect_camera_vision_request,
    normalize_user_utterance,
    source_label_for_backend,
)
from neuro_mirror.utils.text import is_mostly_cyrillic


class AIAssistantPlugin(ProcessorPlugin):
    plugin_name = "ai_assistant"

    def __init__(
        self,
        bus,
        *,
        enabled: bool,
        backend: AssistantBackend | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(bus)
        self.enabled = enabled
        self.backend = backend or RuleBasedAssistantBackend()
        self.settings = settings

    def subscribed_topics(self) -> tuple[str, ...]:
        if not self.enabled:
            return ()
        return (
            Topics.VOICE_INTENT,
            Topics.REQ_ASSISTANT_MESSAGE,
            Topics.REQ_CAMERA_VISION,
        )

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.REQ_ASSISTANT_MESSAGE:
            await self._handle_req_assistant_message(event)
            return

        if event.topic == Topics.REQ_CAMERA_VISION:
            await self._handle_req_camera_vision(event)
            return

        # Original VOICE_INTENT handling
        intent = event.payload.get("intent")
        if intent is not None:
            command = self._intent_to_command(intent)
            if command is None:
                return

            await self._publish_command(
                command=command,
                raw_intent=intent,
                reply=self._intent_reply(command),
                backend=self._intent_source(command),
            )
            return

        utterance = str(event.payload.get("utterance") or event.payload.get("text") or "").strip()
        if not utterance:
            return

        decision = await self._decide_with_ui_feedback(utterance)
        if decision is None:
            return

        if decision.command is not None:
            await self._publish_command(
                command=decision.command,
                raw_intent=utterance,
                reply=decision.reply,
                backend=decision.backend_name,
            )
            return

        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "assistant",
                    "message": f"{decision.reply} [{decision.backend_name}]",
                    "assistant_source": source_label_for_backend(decision.backend_name),
                },
            )
        )

    # ---- request-reply: assistant message ----

    async def _handle_req_assistant_message(self, event: Event) -> None:
        request_id = event.payload.get("_request_id", "")
        text = str(event.payload.get("text") or "").strip()
        source = str(event.payload.get("source") or "web.assistant")

        if not text:
            await self._reply(
                Topics.RESP_ASSISTANT_MESSAGE,
                request_id,
                {"accepted": False, "error": "text is empty"},
            )
            return

        text = normalize_user_utterance(text)

        # Appearance shortcuts
        lowered = " ".join(text.strip().lower().split())
        appearance_markers = (
            "как я выгляжу",
            "как я сегодня выгляжу",
            "оцени мой внешний вид",
            "оцени мою внешность",
            "посмотри на меня",
        )
        if any(m in lowered for m in appearance_markers):
            decision = AssistantDecision(
                command="analyze_appearance",
                reply="Сейчас посмотрю на кадр и дам короткий комментарий.",
                backend_name="визуальный анализ",
            )
            await self._publish_ui_assistant(decision.reply, "визуальный анализ")
            await self._reply(
                Topics.RESP_ASSISTANT_MESSAGE,
                request_id,
                {
                    "accepted": True,
                    "command": decision.command,
                    "reply": decision.reply,
                    "backend": decision.backend_name,
                },
            )
            return

        if detect_camera_vision_request(text):
            decision = AssistantDecision(
                command="camera_vision_query",
                reply="Сейчас посмотрю на камеру и расскажу что вижу.",
                backend_name="vision:камера",
            )
            await self._publish_ui_assistant(decision.reply, "vision:камера")
            await self._reply(
                Topics.RESP_ASSISTANT_MESSAGE,
                request_id,
                {
                    "accepted": True,
                    "command": decision.command,
                    "reply": decision.reply,
                    "backend": decision.backend_name,
                },
            )
            return

        # Screening shortcut
        if any(m in lowered for m in ("начать скрининг", "запусти скрининг", "start screening")):
            decision = AssistantDecision(
                command="start_screening",
                reply="Запускаю скрининг.",
                backend_name="скрининг",
            )
            await self.bus.publish(
                Event(
                    topic=Topics.AI_COMMAND,
                    source=source,
                    payload={
                        "command": "start_screening",
                        "raw_intent": text,
                        "reply": decision.reply,
                        "backend": decision.backend_name,
                    },
                )
            )
            await self._reply(
                Topics.RESP_ASSISTANT_MESSAGE,
                request_id,
                {
                    "accepted": True,
                    "command": decision.command,
                    "reply": decision.reply,
                    "backend": decision.backend_name,
                },
            )
            return

        # General LLM / rule-based decision
        decision = await self.backend.decide(text)

        if decision.command == "start_screening":
            await self.bus.publish(
                Event(
                    topic=Topics.AI_COMMAND,
                    source=source,
                    payload={
                        "command": "start_screening",
                        "raw_intent": text,
                        "reply": decision.reply,
                        "backend": decision.backend_name,
                    },
                )
            )
        elif decision.command in ("analyze_appearance", "camera_vision_query"):
            assistant_source = (
                "визуальный анализ"
                if decision.command == "analyze_appearance"
                else "vision:камера"
            )
            await self._publish_ui_assistant(decision.reply, assistant_source)
        else:
            await self._publish_ui_assistant(
                f"{decision.reply} [{decision.backend_name}]",
                source_label_for_backend(decision.backend_name),
            )

        await self._reply(
            Topics.RESP_ASSISTANT_MESSAGE,
            request_id,
            {
                "accepted": True,
                "command": decision.command,
                "reply": decision.reply,
                "backend": decision.backend_name,
            },
        )

    # ---- request-reply: camera vision ----

    async def _handle_req_camera_vision(self, event: Event) -> None:
        request_id = event.payload.get("_request_id", "")
        utterance = str(event.payload.get("text") or "").strip()
        image_base64 = str(event.payload.get("image_base64") or "").strip()

        if not utterance or not image_base64:
            await self._reply(
                Topics.RESP_CAMERA_VISION,
                request_id,
                {"error": "text and image_base64 are required"},
            )
            return

        await self._publish_ui_assistant("Анализирую кадр с камеры...", "vision:камера")

        if not isinstance(self.backend, OllamaAssistantBackend):
            await self._reply(
                Topics.RESP_CAMERA_VISION,
                request_id,
                {
                    "reply": "Vision-запросы доступны только с Ollama бэкендом.",
                    "backend": "unavailable",
                },
            )
            return

        vision_model = ""
        if self.settings:
            vision_model = self.settings.ollama_vision_model or self.settings.ollama_model

        try:
            decision = await self.backend.answer_vision_question(
                utterance,
                image_base64,
                vision_model=vision_model,
            )
        except Exception as exc:
            message = f"Ошибка vision-запроса: {exc}"
            await self._publish_ui_assistant(message, "vision:камера")
            await self._reply(
                Topics.RESP_CAMERA_VISION,
                request_id,
                {"error": message},
            )
            return

        # Translate non-Cyrillic replies
        if decision.reply and not is_mostly_cyrillic(decision.reply):
            text_model = (
                self.backend._resolved_model_cache
                or await asyncio.to_thread(self.backend._resolve_model_name_sync)
            )
            translated = await asyncio.to_thread(
                self.backend._translate_vision_response_to_russian_sync,
                text_model,
                utterance,
                decision.reply,
            )
            if translated:
                decision = AssistantDecision(
                    command=decision.command,
                    reply=translated,
                    backend_name=decision.backend_name,
                    raw_response=decision.raw_response,
                )

        await self._publish_ui_assistant(decision.reply, "vision:камера")
        await self._reply(
            Topics.RESP_CAMERA_VISION,
            request_id,
            {"reply": decision.reply, "backend": decision.backend_name},
        )

    # ---- helpers ----

    async def _decide_with_ui_feedback(self, utterance: str) -> AssistantDecision | None:
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "assistant",
                    "message": f"Обрабатываю запрос через {self.backend.name}: {utterance}",
                    "assistant_source": "обработка запроса",
                },
            )
        )
        try:
            return await self.backend.decide(utterance)
        except Exception as exc:
            await self.bus.publish(
                Event(
                    topic=Topics.UI_UPDATE,
                    source=self.name,
                    payload={
                        "screen": "assistant",
                        "message": f"Ошибка ассистента: {exc}",
                        "assistant_source": "ошибка ассистента",
                    },
                )
            )
            return None

    async def _publish_ui_assistant(self, message: str, assistant_source: str) -> None:
        await self.bus.publish(
            Event(
                topic=Topics.UI_UPDATE,
                source=self.name,
                payload={
                    "screen": "assistant",
                    "message": message,
                    "assistant_source": assistant_source,
                },
            )
        )

    async def _reply(
        self,
        topic: str,
        request_id: str,
        payload: dict[str, Any],
    ) -> None:
        payload["_reply_to"] = request_id
        await self.bus.publish(Event(topic=topic, source=self.name, payload=payload))

    def _intent_to_command(self, intent: str | None) -> str | None:
        if intent == "start_screening":
            return "start_screening"
        if intent == "analyze_appearance":
            return "analyze_appearance"
        return None

    @staticmethod
    def _intent_reply(command: str) -> str:
        if command == "analyze_appearance":
            return "Сейчас посмотрю в камеру и дам короткий комментарий."
        return "Запускаю скрининг."

    @staticmethod
    def _intent_source(command: str) -> str:
        if command == "analyze_appearance":
            return "визуальный анализ"
        return "скрининг"

    async def _publish_command(
        self,
        *,
        command: str,
        raw_intent: str,
        reply: str,
        backend: str,
    ) -> None:
        await self.bus.publish(
            Event(
                topic=Topics.AI_COMMAND,
                source=self.name,
                payload={
                    "command": command,
                    "raw_intent": raw_intent,
                    "reply": reply,
                    "backend": backend,
                },
            )
        )
