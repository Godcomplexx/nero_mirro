from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from neuro_mirror.interfaces.ui import IOutputPlugin
from neuro_mirror.models.events import Event, Topics


@dataclass(slots=True)
class WebUIStateStore:
    snapshot: dict[str, Any] = field(
        default_factory=lambda: {
            "screen": "idle",
            "message": "Веб-интерфейс готов.",
            "assistant_source": "",
            "transcript_text": "",
            "report": None,
            "worker_statuses": {},
            "recording_active": False,
            "device_catalog": {"cameras": [], "microphones": []},
            "selected_devices": {},
            "device_errors": [],
            "event_log": [],
        }
    )
    sockets: set[WebSocket] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.sockets.add(websocket)
            snapshot = json.loads(json.dumps(self.snapshot, ensure_ascii=False))
        await websocket.send_json({"type": "snapshot", "payload": snapshot})

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self.lock:
            self.sockets.discard(websocket)

    async def apply_update(self, payload: dict[str, Any], *, source: str) -> None:
        async with self.lock:
            worker_statuses = payload.get("worker_statuses")
            if isinstance(worker_statuses, dict):
                current = self.snapshot.setdefault("worker_statuses", {})
                current.update(worker_statuses)

            for key, value in payload.items():
                if key == "worker_statuses":
                    continue
                self.snapshot[key] = value

            message = payload.get("message")
            if message:
                event_log = self.snapshot.setdefault("event_log", [])
                event_log.append(f"[{source}] {message}")
                self.snapshot["event_log"] = event_log[-80:]

            snapshot = json.loads(json.dumps(self.snapshot, ensure_ascii=False))
            sockets = list(self.sockets)

        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json({"type": "state", "payload": snapshot})
            except Exception:
                stale.append(websocket)

        if stale:
            async with self.lock:
                for websocket in stale:
                    self.sockets.discard(websocket)

    async def get_snapshot(self) -> dict[str, Any]:
        async with self.lock:
            return json.loads(json.dumps(self.snapshot, ensure_ascii=False))


class WebUIPlugin(IOutputPlugin):
    plugin_name = "web_ui"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self.state_store = WebUIStateStore()

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            Topics.UI_UPDATE,
            Topics.UI_DEVICE_WIZARD_OPEN,
            Topics.DEVICE_VALIDATION_FAILED,
            Topics.DEVICE_SELECTION_RESOLVED,
        )

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.UI_UPDATE:
            await self.apply_update(event.payload, source=event.source)
            return

        if event.topic == Topics.UI_DEVICE_WIZARD_OPEN:
            await self.apply_update(
                {
                    "screen": "device_setup",
                    "message": "Выберите доступные устройства перед стартом.",
                    "device_wizard": event.payload,
                    "device_errors": event.payload.get("errors") or [],
                    "assistant_source": "устройства",
                },
                source=event.source,
            )
            return

        if event.topic == Topics.DEVICE_VALIDATION_FAILED:
            await self.apply_update(
                {
                    "screen": "device_setup",
                    "message": "Выбор устройств требует внимания.",
                    "device_errors": event.payload.get("errors") or [],
                    "assistant_source": "устройства",
                },
                source=event.source,
            )
            return

        if event.topic == Topics.DEVICE_SELECTION_RESOLVED:
            selected_devices = event.payload.get("selected_devices") or {}
            await self.apply_update(
                {
                    "selected_devices": selected_devices,
                    "device_errors": [],
                },
                source=event.source,
            )

    async def apply_update(self, payload: dict[str, Any], *, source: str) -> None:
        await self.state_store.apply_update(payload, source=source)

    async def get_snapshot(self) -> dict[str, Any]:
        return await self.state_store.get_snapshot()
