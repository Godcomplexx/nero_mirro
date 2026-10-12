"""Persistent presentation history used by the game selection policy."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neuro_mirror.plugins.games.catalog import get_game_definition
from neuro_mirror.plugins.games.selector import Presentation


class GameHistoryStore:
    def __init__(self, path: str | Path = "runtime/deidentified/game_history.json") -> None:
        self.path = Path(path)
        self._items = self._load()

    def record(
        self,
        *,
        user_id: str,
        session_id: str,
        game_code: str,
        stimulus_set: str,
        difficulty_level: int | None,
        presented_at: datetime | None = None,
    ) -> None:
        definition = get_game_definition(game_code)
        timestamp = (presented_at or datetime.now(UTC)).astimezone(UTC).isoformat()
        self._items.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "game_code": definition.code,
                "stimulus_set": stimulus_set,
                "difficulty_level": difficulty_level,
                "presented_at": timestamp,
            }
        )
        self._save()

    def for_user(self, user_id: str) -> tuple[Presentation, ...]:
        result: list[Presentation] = []
        for item in self._items:
            if item.get("user_id") != user_id:
                continue
            try:
                definition = get_game_definition(str(item.get("game_code") or ""))
                presented_at = datetime.fromisoformat(str(item.get("presented_at") or ""))
            except (KeyError, ValueError):
                continue
            result.append(
                Presentation(
                    game_code=definition.code,
                    mechanics=definition.mechanics,
                    modalities=definition.modalities,
                    stimulus_set=str(item.get("stimulus_set") or ""),
                    presented_at=presented_at,
                )
            )
        return tuple(sorted(result, key=lambda item: item.presented_at))

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [dict(item) for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(self._items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
