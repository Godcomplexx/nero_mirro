from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from neuro_mirror.interfaces.storage import StoragePluginBase
from neuro_mirror.models.events import Event, Topics


class StoragePlugin(StoragePluginBase):
    plugin_name = "storage"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self.storage_path = Path("runtime") / "screenings.jsonl"
        self._items: list[dict] = self._load_items()

    def subscribed_topics(self) -> tuple[str, ...]:
        return (Topics.STORAGE_WRITE, Topics.STORAGE_READ)

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.STORAGE_WRITE:
            item = {
                **event.payload,
                "stored_at": datetime.now(UTC).isoformat(),
            }
            self._items.append(item)
            self._append_item(item)
            return

        if event.topic == Topics.STORAGE_READ:
            await self.bus.publish(
                Event(
                    topic=Topics.STORAGE_READ_RESULT,
                    source=self.name,
                    payload={"items": list(self._items)},
                )
            )

    def _load_items(self) -> list[dict]:
        if not self.storage_path.exists():
            return []

        items: list[dict] = []
        try:
            for line in self.storage_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    items.append(parsed)
        except (OSError, json.JSONDecodeError):
            return items
        return items

    def _append_item(self, item: dict) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with self.storage_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError:
            return
