from __future__ import annotations

from neuro_mirror.interfaces.processor import ProcessorPlugin
from neuro_mirror.models.events import Event, Topics


class DemoVoiceTestPlugin(ProcessorPlugin):
    plugin_name = "voice_test"

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.START_TEST,)

    async def handle_event(self, event: Event) -> None:
        await self.bus.publish(
            Event(
                topic=Topics.VOICE_TEST_RESULT,
                source=self.name,
                payload={
                    "speech_score": 0.74,
                    "reaction_ms": 820,
                    "notes": "Заменить на реальный микрофонный тест, ASR, скоринг и биомаркеры речи.",
                },
            )
        )
