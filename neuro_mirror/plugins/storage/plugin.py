from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from neuro_mirror.core.data_redaction import redact_test_data
from neuro_mirror.interfaces.storage import StoragePluginBase
from neuro_mirror.models.events import Event, Topics
from neuro_mirror.version import APP_VERSION, SCENARIO_VERSIONS


class StoragePlugin(StoragePluginBase):
    plugin_name = "storage"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self.storage_path = Path("runtime") / "deidentified" / "screenings.jsonl"
        self.legacy_storage_path = Path("runtime") / "screenings.jsonl"
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
            }
            return

        if event.topic == Topics.STORAGE_WRITE:
            report_type = str(event.payload.get("report_type") or "")
            item = self._sanitize_item({
                **self._active_user,
                **event.payload,
                "stored_at": datetime.now(UTC).isoformat(),
                "app_version": APP_VERSION,
                "scenario_version": SCENARIO_VERSIONS.get(report_type, ""),
            })
            self._append_item(item)
            self._items.append(item)
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
        source_path = self.storage_path
        legacy_migration = False
        if not source_path.exists() and self.legacy_storage_path.exists():
            source_path = self.legacy_storage_path
            legacy_migration = True
        if not source_path.exists():
            return []

        items: list[dict] = []
        changed = legacy_migration
        # A failed read or malformed report must not turn into an empty history
        # that a later write could overwrite. Leave the source intact and fail.
        for line in source_path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError(f"Invalid report in {source_path}")
            sanitized = self._sanitize_item(parsed)
            changed = changed or sanitized != parsed
            items.append(sanitized)
        if changed:
            self._rewrite_items(items)
            if legacy_migration:
                try:
                    source_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return items

    def _append_item(self, item: dict) -> None:
        # Replace atomically so a partial append cannot corrupt existing rows.
        self._rewrite_items([*self._items, item])

    def _rewrite_items(self, items: list[dict]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        try:
            payload = "".join(
                json.dumps(self._sanitize_item(item), ensure_ascii=False) + "\n"
                for item in items
            )
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self.storage_path)
        finally:
            temp_path.unlink(missing_ok=True)

    _sanitize_item = staticmethod(redact_test_data)
