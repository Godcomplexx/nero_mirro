from __future__ import annotations

from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.plugins.ai_assistant.backends import (
    AssistantBackend,
    RuleBasedAssistantBackend,
    source_label_for_backend,
)


class AIAssistantPlugin(ProcessorPlugin):
    plugin_name = "ai_assistant"

    def __init__(self, bus, *, enabled: bool, backend: AssistantBackend | None = None) -> None:
        super().__init__(bus)
        self.enabled = enabled
        self.backend = backend or RuleBasedAssistantBackend()

    def subscribed_topics(self) -> tuple[str, ...]:
        if not self.enabled:
            return ()
        return (Topics.VOICE_INTENT,)

    async def handle_event(self, event: Event) -> None:
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
            decision = await self.backend.decide(utterance)
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
