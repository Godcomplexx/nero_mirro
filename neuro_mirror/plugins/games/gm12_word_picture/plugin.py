from __future__ import annotations
import secrets, time, uuid
from dataclasses import dataclass, field
from typing import Any
from neuro_mirror.plugins.games.base import BrowserGamePlugin
from neuro_mirror.plugins.games.gm12_word_picture.stimuli import DISTRACTORS, ITEMS, SESSION_DURATION_MS
from neuro_mirror.screening.gm12_scoring import score_gm12_trials

@dataclass(slots=True)
class PictureSession:
    session_id: str; order: list[tuple[str, str, str]]; stimulus_set: str; index: int = 0
    shown_at_ms: float = 0.0; started_at_ms: float = field(default_factory=lambda: time.time() * 1000)
    choices: list[str] = field(default_factory=list); trials: list[dict[str, Any]] = field(default_factory=list)

class Gm12WordPicturePlugin(BrowserGamePlugin):
    plugin_name = "gm12_word_picture"
    game_code = "GM-12"
    def __init__(self, bus) -> None:
        super().__init__(bus); self._sessions = {}; self._random = secrets.SystemRandom()
    def start_game(self, payload):
        return self._start(stimulus_set=str(payload.get("stimulus_set") or ""))
    def _start(self, *, stimulus_set=""):
        categories = tuple(dict.fromkeys(category for category, _, _ in ITEMS))
        available = tuple(name for name in self.definition.stimulus_sets if name in categories) or categories
        selected = stimulus_set if stimulus_set in available else available[0]
        order = [item for item in ITEMS if item[0] == selected]; self._random.shuffle(order)
        session_id = uuid.uuid4().hex
        session = PictureSession(session_id, order, selected)
        self._sessions[session.session_id] = session
        return self._payload(session)
    def _payload(self, session):
        category, word, picture = session.order[session.index]
        pool = [item for item in DISTRACTORS[category] if item != word]; self._random.shuffle(pool)
        session.choices = [word] + pool[:3]; self._random.shuffle(session.choices); session.shown_at_ms = time.time() * 1000
        return {"ok": True, "finished": False, "session_id": session.session_id, "trial": session.index + 1,
                "trial_count": len(session.order), "duration_ms": SESSION_DURATION_MS,
                "stimulus_set": session.stimulus_set,
                "category": category, "picture": picture, "choices": session.choices}
    def _answer(self, payload):
        session = self._sessions.get(str(payload.get("session_id") or ""))
        if session is None: return {"ok": False, "message": "Игровая сессия не найдена."}
        if payload.get("time_up") is True:
            return self._finish(session)
        selected = str(payload.get("selected_word") or ""); category, word, picture = session.order[session.index]
        elapsed_ms = max(0.0, time.time() * 1000 - session.shown_at_ms)
        valid = selected in session.choices
        if not valid: return {"ok": False, "message": "Некорректный ответ."}
        correct = selected == word
        session.trials.append({"trial": session.index + 1, "category": category, "target_word": word, "picture": picture,
                               "choices": session.choices, "selected_word": selected, "correct": correct,
                               "reaction_ms": elapsed_ms, "client_timestamp_ms": payload.get("timestamp_ms")})
        session.index += 1
        all_done = session.index == len(session.order)
        time_up = time.time() * 1000 - session.started_at_ms >= SESSION_DURATION_MS
        if all_done or time_up:
            # Причина завершения нужна интерфейсу: досрочно выполненное задание
            # и истёкшее время — разные события, и сообщать о них одинаково
            # нельзя.
            result = self._finish(session, reason="all_items" if all_done else "time_up")
            result["correct"] = correct
            return result
        result = self._payload(session)
        result["previous_correct"] = correct
        return result

    def _finish(self, session, *, reason="time_up"):
        self._sessions.pop(session.session_id, None)
        metrics = score_gm12_trials(session.trials, expected_trials=len(session.trials))
        return {"ok": True, "finished": True, "completion_reason": reason,
                "metrics": metrics, "events": session.trials}
