from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.difficulty_config import level_config
from neuro_mirror.plugins.games.gm11_serial_count.stimuli import RULES
from neuro_mirror.screening.gm11_scoring import score_gm11

WORDS = {
    "ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
    "девять": 9, "десять": 10, "одиннадцать": 11, "двенадцать": 12,
    "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40,
    "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70,
    "восемьдесят": 80, "девяносто": 90, "сто": 100,
}


def parse_number(text: str) -> int | None:
    match = re.search(r"-?\d+", text)
    if match:
        return int(match.group())
    values = [
        WORDS[word]
        for word in re.findall(r"[а-яё]+", text.lower())
        if word in WORDS
    ]
    return sum(values) if values else None

@dataclass(slots=True)
class CountSession:
    session_id: str
    rules: list[dict[str, Any]]
    block_correct_counts: list[int]
    stimulus_set: str
    difficulty_level: int
    difficulty_parameters: dict[str, Any]
    rule_index: int = 0
    current: int = 0
    correct_in_rule: int = 0
    last_answer_ms: float = field(default_factory=lambda: time.time() * 1000)
    round_events: list[dict[str, Any]] = field(default_factory=list)

class Gm11SerialCountPlugin(BrowserGamePlugin):
    plugin_name = "gm11_serial_count"
    game_code = "GM-11"
    start_handler = "_start"
    answer_handler = "_answer"

    def __init__(self, bus):
        super().__init__(bus)
        self._sessions = {}

    def start_game(self, payload):
        return self._start(
            stimulus_set=str(payload.get("stimulus_set") or ""),
            difficulty_level=payload.get("difficulty_level"),
        )

    def _start(self, *, stimulus_set="", difficulty_level=None):
        config = level_config(self.game_code)
        try:
            level = int(difficulty_level or config["default_level"])
        except (TypeError, ValueError):
            level = int(config["default_level"])
        available_levels = {int(item["level"]): item for item in config["levels"]}
        if level not in available_levels:
            level = int(config["default_level"])
        parameters = dict(available_levels[level]["parameters"])
        block_correct_counts = [int(value) for value in parameters["block_correct_counts"]]
        rules_by_name = {str(rule["stimulus_set"]): rule for rule in RULES}
        available = tuple(name for name in self.definition.stimulus_sets if name in rules_by_name) or tuple(rules_by_name)
        selected = stimulus_set if stimulus_set in available else available[0]
        ordered_names = [selected] + [name for name in available if name != selected]
        rules = [rules_by_name[ordered_names[index % len(ordered_names)]] for index in range(len(block_correct_counts))]
        session = CountSession(
            uuid.uuid4().hex,
            rules,
            block_correct_counts,
            selected,
            level,
            parameters,
            current=rules[0]["start"],
        )
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload):
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        now = time.time() * 1000
        value = parse_number(str(payload.get("transcript") or ""))
        rule = session.rules[session.rule_index]
        expected = session.current + rule["step"]
        correct = value == expected
        session.round_events.append(
            {
                "rule": rule["label"],
                "rule_index": session.rule_index,
                "stimulus_set": rule["stimulus_set"],
                "expected": expected,
                "transcript": payload.get("transcript"),
                "answer": value,
                "correct": correct,
                "interval_ms": max(0, now - session.last_answer_ms),
            }
        )
        session.last_answer_ms = now
        if correct:
            session.current = expected
            session.correct_in_rule += 1
            if session.correct_in_rule >= session.block_correct_counts[session.rule_index]:
                session.rule_index += 1
                session.correct_in_rule = 0
                if session.rule_index >= len(session.rules):
                    events = list(session.round_events)
                    self._sessions.pop(session.session_id, None)
                    return {
                        "ok": True,
                        "finished": True,
                        "correct": True,
                        "events": events,
                        "metrics": score_gm11(events, expected_rules=len(session.rules)),
                    }
                session.current = session.rules[session.rule_index]["start"]
        result = self._payload(session)
        result.update({"correct": correct, "recognized": value, "expected": expected})
        return result

    def _resume(self, session, paused_ms):
        """Прерванный шаг счёта повторяется с того же числа (4.5, п. 5)."""
        session.last_answer_ms = time.time() * 1000
        return self._payload(session)

    def _trial_number(self, session):
        return len(session.round_events) + 1

    def _payload(self, session):
        rule = session.rules[session.rule_index]
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "stimulus_set": session.stimulus_set,
            "difficulty_level": session.difficulty_level,
            "difficulty_parameters": dict(session.difficulty_parameters),
            "rule_number": session.rule_index + 1,
            "rule_count": len(session.rules),
            "instruction": rule["label"],
            "current": session.current,
            "correct_in_rule": session.correct_in_rule,
            "required_correct": session.block_correct_counts[session.rule_index],
        }
