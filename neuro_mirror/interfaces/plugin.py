from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from neuro_mirror.core.event_bus import EventBus, EventSubscription
from neuro_mirror.models.events import Event


class Plugin(ABC):
    plugin_name = "plugin"

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._task: asyncio.Task[None] | None = None
        self._subscription: EventSubscription | None = None

    @property
    def name(self) -> str:
        return self.plugin_name

    def subscribed_topics(self) -> tuple[str, ...]:
        return ()

    async def start(self) -> None:
        topics = self.subscribed_topics()
        if topics:
            self._subscription = self.bus.subscribe(*topics)
            self._task = asyncio.create_task(self._consume_loop(), name=f"{self.name}-loop")
        await self.on_start()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._subscription is not None:
            self._subscription.close()
            self._subscription = None

        await self.on_stop()

    async def on_start(self) -> None:
        return None

    async def on_stop(self) -> None:
        return None

    async def _consume_loop(self) -> None:
        assert self._subscription is not None

        while True:
            event = await self._subscription.queue.get()
            await self.handle_event(event)

    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        raise NotImplementedError

