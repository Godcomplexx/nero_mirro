from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm01_pair_cards.stimuli import STIMULI
from neuro_mirror.screening.gm01_scoring import score_gm01


@dataclass(slots=True)
class PairSession:
    session_id: str
    boards: list[list[str]]
    board_index: int = 0
    first_index: int | None = None
    matched: set[int] = field(default_factory=set)
    round_events: list[dict[str, Any]] = field(default_factory=list)
    started_ms: float = field(default_factory=lambda: time.time() * 1000)


class Gm01PairCardsPlugin(BrowserGamePlugin):
    plugin_name = "gm01_pair_cards"
    game_code = "GM-01"
    start_handler = "_start"
    answer_handler = "_answer"

    def __init__(self, bus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, PairSession] = {}
        self._random = secrets.SystemRandom()

    def _start(self) -> dict[str, Any]:
        set_name = self.definition.stimulus_sets[0]
        source = list(STIMULI.get(set_name, next(iter(STIMULI.values()))))
        boards = []
        for _ in range(2):
            chosen = self._random.sample(source, 5)
            cards = chosen + chosen
            self._random.shuffle(cards)
            boards.append(cards)
        session = PairSession(uuid.uuid4().hex, boards)
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        index = int(payload.get("selected_index", -1))
        cards = session.boards[session.board_index]
        if index < 0 or index >= len(cards) or index in session.matched or index == session.first_index:
            return {"ok": False, "message": "Недопустимая карточка."}
        if session.first_index is None:
            session.first_index = index
            result = self._payload(session)
            result.update({"first_pick": True, "revealed": [index]})
            return result
        first = session.first_index
        session.first_index = None
        correct = cards[first] == cards[index]
        if correct:
            session.matched.update((first, index))
        session.round_events.append({
            "board": session.board_index + 1,
            "selected_indices": [first, index],
            "correct": correct,
            "reaction_ms": payload.get("reaction_ms"),
        })
        if len(session.matched) == len(cards):
            session.board_index += 1
            session.matched.clear()
            if session.board_index == len(session.boards):
                events = list(session.round_events)
                self._sessions.pop(session.session_id, None)
                return {
                    "ok": True,
                    "finished": True,
                    "correct": correct,
                    "events": events,
                    "metrics": score_gm01(events, pair_count=10, completed=True),
                }
        result = self._payload(session)
        result.update({"correct": correct, "revealed": [first, index]})
        return result

    def _payload(self, session: PairSession) -> dict[str, Any]:
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "board": session.board_index + 1,
            "board_count": len(session.boards),
            "cards": session.boards[session.board_index],
            "matched": sorted(session.matched),
        }
