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

        items = self._read_items()
        items.append(safe_snapshot)
        items = items[-max(1, self.limit):]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"items": items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_items(self) -> list[dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError):
            return []

        raw_items = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(raw_items, list):
            return []

        items: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                items.append(self._sanitize_snapshot(item))
        return items[-max(1, self.limit):]

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

    notes: list[str] = []
    hair_note = _changed_note(
        current.get("hair"),
        previous.get("hair"),
        "Волосы сегодня выглядят иначе, чем раньше, и это хорошо освежает образ.",
    )
    if hair_note:
        notes.append(hair_note)

    clothing_note = _changed_note(
        current.get("clothing"),
        previous.get("clothing"),
        "Одежда сегодня отличается от прошлого образа и смотрится аккуратно.",
    )
    if clothing_note:
        notes.append(clothing_note)

    accessories_note = _changed_note(
        current.get("accessories"),
        previous.get("accessories"),
        "Аксессуары сегодня заметно меняют впечатление от образа.",
    )
    if accessories_note:
        notes.append(accessories_note)

    return " ".join(notes[:2])


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
