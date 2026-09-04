from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from neuro_mirror.interfaces.storage import StoragePluginBase
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.version import APP_VERSION, SCENARIO_VERSIONS


class StoragePlugin(StoragePluginBase):
    plugin_name = "storage"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self.storage_path = Path("runtime") / "screenings.jsonl"
        self._items: list[dict] = self._load_items()
        self._active_user: dict = {}

    def subscribed_topics(self) -> tuple[str, ...]:
        return (
            Topics.STORAGE_WRITE,
            Topics.STORAGE_READ,
            Topics.REQ_STORAGE_QUERY,
            Topics.USER_SELECTED,
        )

    async def handle_event(self, event: Event) -> None:
        if event.topic == Topics.USER_SELECTED:
            self._active_user = {
                "user_id": event.payload.get("user_id", ""),
                "user_name": event.payload.get("user_name", ""),
            }
            return

        if event.topic == Topics.STORAGE_WRITE:
            report_type = str(event.payload.get("report_type") or "")
            item = {
                **self._active_user,
                **event.payload,
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "app_version": APP_VERSION,
                "scenario_version": SCENARIO_VERSIONS.get(report_type, ""),
            }
            self._items.append(item)
            self._append_item(item)
            return

        if event.topic == Topics.REQ_STORAGE_QUERY:
            user_id = str(event.payload.get("user_id") or "")
            items = [
                item for item in self._items
                if not user_id or item.get("user_id") == user_id
            ]
            await self.bus.publish(
                Event(
                    topic=Topics.RESP_STORAGE_QUERY,
                    source=self.name,
                    payload={
                        "_reply_to": event.payload.get("_request_id"),
                        "items": items,
                    },
                )
            )
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
            # utf-8-sig: tolerate a BOM left by external editors
            for line in self.storage_path.read_text(encoding="utf-8-sig").splitlines():
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
