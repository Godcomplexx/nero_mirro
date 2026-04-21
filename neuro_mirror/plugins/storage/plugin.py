from __future__ import annotations

from neuro_mirror.interfaces.storage import StoragePluginBase
from neuro_mirror.models.events import Event, Topics


class StoragePlugin(StoragePluginBase):
    plugin_name = "storage"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._items: list[dict] = []

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.STORAGE_WRITE, Topics.STORAGE_READ)

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.STORAGE_WRITE:
            self._items.append(event.payload)
            return

        if event.topic == Topics.STORAGE_READ:
            await self.bus.publish(
                Event(
                    topic=Topics.STORAGE_READ_RESULT,
                    source=self.name,
                    payload={"items": list(self._items)},
                )
            )

