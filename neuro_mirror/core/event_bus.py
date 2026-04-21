from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict

from neuro_mirror.models.events import Event


@dataclass(slots=True)
class EventSubscription:
    topics: tuple[str, ...]
    queue: asyncio.Queue[Event]
    _subscribers: DefaultDict[str, list[asyncio.Queue[Event]]]

    def close(self) -> None:
        for topic in self.topics:
            queues = self._subscribers.get(topic, [])
            if self.queue in queues:
                queues.remove(self.queue)
            if not queues and topic in self._subscribers:
                del self._subscribers[topic]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, list[asyncio.Queue[Event]]] = defaultdict(list)

    def subscribe(self, *topics: str) -> EventSubscription:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        for topic in topics:
            self._subscribers[topic].append(queue)
        return EventSubscription(topics=tuple(topics), queue=queue, _subscribers=self._subscribers)

    async def publish(self, event: Event) -> None:
        queues = list(self._subscribers.get(event.topic, []))
        queues.extend(self._subscribers.get("*", []))

        for queue in queues:
            await queue.put(event)

