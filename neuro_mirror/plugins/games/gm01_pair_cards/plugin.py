from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm01_pair_cards.stimuli import STIMULI
from neuro_mirror.screening.gm01_scoring import score_gm01


@dataclass(slots=True)
class PairSession:
    session_id: str
    boards: list[list[str]]
    stimulus_set: str
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    board_index: int = 0
    first_index: int | None = None
    matched: set[int] = field(default_factory=set)
    seen: set[int] = field(default_factory=set)
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

    def start_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._start(
            stimulus_set=str(payload.get("stimulus_set") or ""),
            difficulty_level=payload.get("difficulty_level"),
        )

    def _start(self, *, stimulus_set: str = "", difficulty_level: object = None) -> dict[str, Any]:
        config = level_config(self.game_code)
        try:
            level = int(difficulty_level or config["default_level"])
        except (TypeError, ValueError):
            level = int(config["default_level"])
        available_levels = {int(item["level"]): item for item in config["levels"]}
        if level not in available_levels:
            level = int(config["default_level"])
        parameters = dict(available_levels[level]["parameters"])
        level_boards = tuple(int(value) for value in parameters["pair_counts"])
        boards = []
        available_sets = tuple(
            set_name for set_name in self.definition.stimulus_sets if set_name in STIMULI
        ) or tuple(STIMULI)
        selected_set = stimulus_set if stimulus_set in available_sets else available_sets[0]
        source = list(STIMULI[selected_set])
        for pair_count in level_boards:
            chosen = self._random.sample(source, pair_count)
            cards = chosen + chosen
            self._random.shuffle(cards)
            boards.append(cards)
        session = PairSession(uuid.uuid4().hex, boards, selected_set, level, parameters)
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        index = int(payload.get("selected_index", -1))
        cards = session.boards[session.board_index]
        supplied_first = payload.get("first_index")
        first = int(supplied_first) if supplied_first is not None else session.first_index
        invalid_first = supplied_first is not None and (
            first is None
            or first < 0
            or first >= len(cards)
            or first in session.matched
            or first == index
        )
        if (
            index < 0
            or index >= len(cards)
            or index in session.matched
            or index == session.first_index
            or invalid_first
        ):
            return {"ok": False, "message": "Недопустимая карточка."}
        # The browser can send the two selected cards together. This avoids a
        # network round trip after opening the first card and keeps the game
        # responsive even when checkpoint persistence takes noticeable time.
        # Single-card requests remain supported for older clients.
        if first is None:
            session.first_index = index
            result = self._payload(session)
            result.update({"first_pick": True, "revealed": [index]})
            return result
        session.first_index = None
        correct = cards[first] == cards[index]
        known_pairs = {
            value
            for value in set(cards)
            if all(
                position in session.seen or position in session.matched
                for position, card in enumerate(cards)
                if card == value
            )
            and not all(
                position in session.matched
                for position, card in enumerate(cards)
                if card == value
            )
        }
        used_known_pair = correct and cards[first] in known_pairs
        if correct:
            session.matched.update((first, index))
        session.seen.update((first, index))
        session.round_events.append({
            "board": session.board_index + 1,
            "selected_indices": [first, index],
            "correct": correct,
            "known_pair_opportunities": len(known_pairs),
            "used_known_pair": used_known_pair,
            "reaction_ms": payload.get("reaction_ms"),
        })
        if len(session.matched) == len(cards):
            session.board_index += 1
            session.matched.clear()
            session.seen.clear()
            if session.board_index == len(session.boards):
                events = list(session.round_events)
                self._sessions.pop(session.session_id, None)
                return {
                    "ok": True,
                    "finished": True,
                    "correct": correct,
                    "events": events,
                    "metrics": score_gm01(
                        events,
                        pair_count=sum(len(board) // 2 for board in session.boards),
                        completed=True,
                        elapsed_ms=time.time() * 1000 - session.started_ms,
                    ),
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
            "stimulus_set": session.stimulus_set,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": session.difficulty_parameters,
            "cards": session.boards[session.board_index],
            "pair_count": len(session.boards[session.board_index]) // 2,
            "grid_columns": self._grid_columns(len(session.boards[session.board_index])),
            "matched": sorted(session.matched),
        }

    @staticmethod
    def _grid_columns(card_count: int) -> int:
        return {6: 3, 8: 4, 10: 5, 12: 4, 16: 4, 20: 5}.get(card_count, 5)
