from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, DefaultDict

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
        self._pending_replies: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def subscribe(self, *topics: str) -> EventSubscription:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        for topic in topics:
            self._subscribers[topic].append(queue)
        return EventSubscription(topics=tuple(topics), queue=queue, _subscribers=self._subscribers)

    async def publish(self, event: Event) -> None:
        # If this event is a reply, resolve the pending future
        reply_to = event.payload.get("_reply_to")
        if reply_to and reply_to in self._pending_replies:
            future = self._pending_replies.pop(reply_to)
            if not future.done():
                future.set_result(event.payload)

        queues = list(self._subscribers.get(event.topic, []))
        queues.extend(self._subscribers.get("*", []))

        for queue in queues:
            await queue.put(event)

    async def request(
        self,
        event: Event,
        *,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Publish *event* and wait for a reply.

        The event payload is augmented with a unique ``_request_id``.
        Any responder should include ``_reply_to`` set to the same id
        in its reply event payload so the bus can match it.
        """
        request_id = uuid.uuid4().hex
        event.payload["_request_id"] = request_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending_replies[request_id] = future
        try:
            await self.publish(event)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_replies.pop(request_id, None)
            raise
        except BaseException:
            self._pending_replies.pop(request_id, None)
            raise

