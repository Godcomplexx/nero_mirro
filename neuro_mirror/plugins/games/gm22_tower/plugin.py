from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm22_tower.stimuli import (
    BONUS_DISKS,
    DISK_LEVELS,
    MINIMUM_SESSION_MS,
)
from neuro_mirror.screening.gm22_scoring import score_gm22


@dataclass(slots=True)
class TowerSession:
    session_id: str
    started_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    level_started_at_ms: float = 0.0
    level_index: int = 0
    rods: list[list[int]] = field(default_factory=list)
    level_valid_moves: int = 0
    level_invalid_moves: int = 0
    round_events: list[dict[str, Any]] = field(default_factory=list)


class Gm22TowerPlugin(BrowserGamePlugin):
    plugin_name = "gm22_tower"
    game_code = "GM-22"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, TowerSession] = {}

    def _disk_count(self, session: TowerSession) -> int:
        return DISK_LEVELS[session.level_index] if session.level_index < len(DISK_LEVELS) else BONUS_DISKS

    def _start(self) -> dict[str, Any]:
        session = TowerSession(uuid.uuid4().hex)
        self._sessions[session.session_id] = session
        return self._prepare_level(session)

    def _prepare_level(self, session: TowerSession) -> dict[str, Any]:
        disk_count = self._disk_count(session)
        session.rods = [list(range(disk_count, 0, -1)), [], []]
        session.level_valid_moves = 0
        session.level_invalid_moves = 0
        session.level_started_at_ms = time.time() * 1000
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        try:
            source = int(payload.get("source_rod"))
            target = int(payload.get("target_rod"))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Некорректный ход."}
        if source not in range(3) or target not in range(3) or source == target:
            return {"ok": False, "message": "Некорректный ход."}

        source_rod = session.rods[source]
        target_rod = session.rods[target]
        disk = source_rod[-1] if source_rod else None
        valid = disk is not None and (not target_rod or disk < target_rod[-1])
        if valid:
            target_rod.append(source_rod.pop())
            session.level_valid_moves += 1
        else:
            session.level_invalid_moves += 1

        disk_count = self._disk_count(session)
        solved = session.rods[2] == list(range(disk_count, 0, -1))
        event = {
            "level": session.level_index + 1,
            "disk_count": disk_count,
            "selected_source": source,
            "selected_target": target,
            "disk": disk,
            "valid": valid,
            "correct": valid,
            "level_complete": solved,
            "elapsed_ms": max(0.0, time.time() * 1000 - session.level_started_at_ms),
        }
        if solved:
            event.update(
                {
                    "level_moves": session.level_valid_moves,
                    "level_invalid_moves": session.level_invalid_moves,
                    "minimum_moves": 2**disk_count - 1,
                }
            )
        session.round_events.append(event)

        if not solved:
            result = self._payload(session)
            result["move_valid"] = valid
            return result

        session.level_index += 1
        elapsed_ms = time.time() * 1000 - session.started_at_ms
        if session.level_index >= len(DISK_LEVELS) and elapsed_ms >= MINIMUM_SESSION_MS:
            events = list(session.round_events)
            self._sessions.pop(session.session_id, None)
            return {
                "ok": True,
                "finished": True,
                "events": events,
                "metrics": score_gm22(events, elapsed_ms),
            }
        result = self._prepare_level(session)
        result["level_complete"] = True
        return result

    def _payload(self, session: TowerSession) -> dict[str, Any]:
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "level_number": session.level_index + 1,
            "required_levels": len(DISK_LEVELS),
            "bonus": session.level_index >= len(DISK_LEVELS),
            "disk_count": self._disk_count(session),
            "rods": [list(rod) for rod in session.rods],
            "move_count": session.level_valid_moves,
            "invalid_move_count": session.level_invalid_moves,
        }
