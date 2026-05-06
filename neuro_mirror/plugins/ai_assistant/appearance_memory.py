from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


MEMORY_FIELDS = (
    "created_at",
    "hair",
    "clothing",
    "accessories",
    "style",
    "mood",
    "wellness",
    "summary",
)


@dataclass(slots=True)
class AppearanceMemoryStore:
    path: Path
    limit: int = 20

    def recent(self, count: int = 5) -> list[dict[str, Any]]:
        items = self._read_items()
        return items[-max(0, count):]

    def append(self, snapshot: dict[str, Any]) -> None:
        safe_snapshot = self._sanitize_snapshot(snapshot)
        if not any(safe_snapshot.get(field) for field in MEMORY_FIELDS if field != "created_at"):
            return

        items, request_count = self._read_state()
        request_count += 1
        if request_count % 10 == 0 and items:
            items.pop(0)
        items.append(safe_snapshot)
        items = items[-max(1, self.limit):]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"request_count": request_count, "items": items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_items(self) -> list[dict[str, Any]]:
        items, _ = self._read_state()
        return items

    def _read_state(self) -> tuple[list[dict[str, Any]], int]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return [], 0
        except (OSError, json.JSONDecodeError):
            return [], 0

        if isinstance(raw, dict):
            raw_items = raw.get("items")
            request_count = int(raw.get("request_count") or 0)
        else:
            raw_items = raw
            request_count = 0

        if not isinstance(raw_items, list):
            return [], request_count

        items: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                items.append(self._sanitize_snapshot(item))
        return items[-max(1, self.limit):], request_count

    @staticmethod
    def _sanitize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {
            "created_at": str(snapshot.get("created_at") or datetime.now(UTC).isoformat()),
        }
        for field in MEMORY_FIELDS:
            if field == "created_at":
                continue
            value = " ".join(str(snapshot.get(field) or "").split()).strip()
            if value:
                clean[field] = value[:500]
        return clean


def build_memory_note(current: dict[str, Any], recent: list[dict[str, Any]]) -> str:
    previous = next((item for item in reversed(recent) if item), None)
    if not previous:
        return ""

    changes: list[str] = []

    if _is_changed(current.get("hair"), previous.get("hair")):
        prev_hair = str(previous.get("hair") or "").strip()
        curr_hair = str(current.get("hair") or "").strip()
        changes.append(
            f"причёска изменилась (было: {prev_hair}; сейчас: {curr_hair})"
            if prev_hair and curr_hair else "причёска изменилась"
        )

    if _is_changed(current.get("clothing"), previous.get("clothing")):
        prev_cl = str(previous.get("clothing") or "").strip()
        curr_cl = str(current.get("clothing") or "").strip()
        changes.append(
            f"одежда другая (было: {prev_cl}; сейчас: {curr_cl})"
            if prev_cl and curr_cl else "одежда другая"
        )

    if _is_changed(current.get("accessories"), previous.get("accessories")):
        changes.append("аксессуары изменились")

    return "; ".join(changes[:2])


def _is_changed(current: Any, previous: Any) -> bool:
    c = _normalize_compare_text(current)
    p = _normalize_compare_text(previous)
    if not c or not p:
        return False
    if c == p:
        return False
    if c in p or p in c:
        return False
    return True


def _changed_note(current: Any, previous: Any, note: str) -> str:
    current_text = _normalize_compare_text(current)
    previous_text = _normalize_compare_text(previous)
    if not current_text or not previous_text:
        return ""
    if current_text == previous_text:
        return ""
    if current_text in previous_text or previous_text in current_text:
        return ""
    return note


def _normalize_compare_text(value: Any) -> str:
    text = " ".join(str(value or "").lower().split())
    stop_words = ("видно", "заметно", "сегодня", "в кадре", "выглядит", "выглядят")
    for word in stop_words:
        text = text.replace(word, "")
    return " ".join(text.split())
