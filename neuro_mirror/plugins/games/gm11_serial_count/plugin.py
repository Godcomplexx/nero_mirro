from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm11_serial_count.stimuli import CORRECT_PER_RULE, RULES
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

    def _start(self):
        session = CountSession(uuid.uuid4().hex, current=RULES[0]["start"])
        self._sessions[session.session_id] = session
        return self._payload(session)

    def _answer(self, payload):
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None:
            return {"ok": False, "message": "Игровая сессия не найдена."}
        now = time.time() * 1000
        value = parse_number(str(payload.get("transcript") or ""))
        rule = RULES[session.rule_index]
        expected = session.current + rule["step"]
        correct = value == expected
        session.round_events.append(
            {
                "rule": rule["label"],
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
            if session.correct_in_rule >= CORRECT_PER_RULE:
                session.rule_index += 1
                session.correct_in_rule = 0
                if session.rule_index >= len(RULES):
                    events = list(session.round_events)
                    self._sessions.pop(session.session_id, None)
                    return {
                        "ok": True,
                        "finished": True,
                        "correct": True,
                        "events": events,
                        "metrics": score_gm11(events),
                    }
                session.current = RULES[session.rule_index]["start"]
        result = self._payload(session)
        result.update({"correct": correct, "recognized": value, "expected": expected})
        return result

    def _payload(self, session):
        rule = RULES[session.rule_index]
        return {
            "ok": True,
            "finished": False,
            "session_id": session.session_id,
            "rule_number": session.rule_index + 1,
            "rule_count": len(RULES),
            "instruction": rule["label"],
            "current": session.current,
            "correct_in_rule": session.correct_in_rule,
            "required_correct": CORRECT_PER_RULE,
        }
